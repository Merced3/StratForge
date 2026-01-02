#data_aquisition.py
import requests
import pandas as pd
import shared_state
import websockets
import asyncio
import cred
import aiohttp
import json
import pandas_market_calendars as mcal
import pytz
import time
from datetime import datetime
from error_handler import error_log_and_discord_message
from shared_state import price_lock, indent, print_log
from utils.json_utils import read_config
from utils.data_utils import get_dates
from utils.file_utils import get_current_candle_index
from paths import pretty_path, get_merged_ema_csv_path, get_markers_path

RETRY_INTERVAL = 1  # Seconds between reconnection attempts
should_close = False  # Global variable to signal if the WebSocket should close
active_provider = None  # Currently active data provider

PROVIDERS = {
    "tradier": {
        "enabled": True,
        "url": "wss://ws.tradier.com/v1/markets/events",
        "headers": lambda: {
            "Authorization": f"Bearer {cred.TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN}",
            "Accept": "application/json",
        },
        "build_payloads": lambda symbol, session_id: {
            "auth": None,
            "sub": json.dumps({"symbols": [symbol], "sessionid": session_id, "linebreak": True}),
        },
    },
    "polygon": {
        # Plan/real-time WS not active; keep as placeholder for future backup.
        "enabled": False,
        "url": "wss://delayed.polygon.io/stocks",
        "headers": lambda: None,
        "build_payloads": lambda symbol, _: {
            "auth": json.dumps({"action": "auth", "params": cred.POLYGON_API_KEY}),
            "sub": json.dumps({"action": "subscribe", "params": f"AM.{symbol}"}),
        },
    },
}

def get_enabled_providers():
    enabled = [name for name, cfg in PROVIDERS.items() if cfg.get("enabled", True)]
    if not enabled:
        raise ValueError("No enabled providers configured")
    return enabled

async def ws_auto_connect(queue, symbol):
    """
    providers: list like ["tradier", "polygon"] or ["tradier"].
    Cycles through providers on failure; keeps retrying even with a single entry.
    """
    global should_close, active_provider
    providers = get_enabled_providers()
    idx = 0

    while True:
        provider = providers[idx % len(providers)]
        active_provider = provider
        cfg = PROVIDERS[provider]
        if not cfg:
            print_log(f"[WARN] Unknown provider '{provider}', skipping.")
            idx += 1
            continue

        url = cfg["url"]
        headers = cfg["headers"]() if cfg.get("headers") else None

        # Provider-specific session/payload prep
        session_id = get_session_id() if provider == "tradier" else None
        if provider == "tradier" and not session_id:
            print_log("[TRADIER] Unable to get session ID. Retrying same provider...")
            await asyncio.sleep(RETRY_INTERVAL)
            continue

        payloads = cfg["build_payloads"](symbol, session_id)
        auth_msg = payloads.get("auth")
        sub_msg = payloads.get("sub")

        try:
            async with websockets.connect(
                url,
                ssl=True,
                compression=None,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=30,
            ) as websocket:
                if auth_msg:
                    await websocket.send(auth_msg)
                    try:
                        await asyncio.wait_for(websocket.recv(), timeout=3)
                    except asyncio.TimeoutError:
                        print_log(f"[{provider.upper()}] No auth ack within 3s; continuing.")
                if sub_msg:
                    await websocket.send(sub_msg)
                print_log(f"[{provider.upper()}] WebSocket established.")
                async for message in websocket:
                    if should_close:
                        await websocket.close()
                        return
                    await queue.put(message)
        except Exception as e:
            print_log(f"[{provider.upper()}] WebSocket failed: {e}; rotating provider.")
            idx += 1
            await asyncio.sleep(RETRY_INTERVAL)
            continue

def get_session_id(retry_attempts=3, backoff_factor=1):
    """Retrieve a session ID from Tradier API."""
    url = "https://api.tradier.com/v1/markets/events/session"
    headers = {
        "Authorization": f"Bearer {cred.TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN}",
        "Accept": "application/json"
    }
    for attempt in range(retry_attempts):
        try:
            response = requests.post(url, data={}, headers=headers, timeout=10)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx, 5xx)
            session_data = response.json()
            session_id = session_data.get("stream", {}).get("sessionid")
            if session_id:
                return session_id
            else:
                print_log(f"[TRADIER] Invalid session response: {session_data}")
        except requests.exceptions.RequestException as e:
            print_log(f"[TRADIER] Error fetching session ID: {e}. Attempt {attempt + 1}/{retry_attempts}")
            time.sleep(backoff_factor * (2 ** attempt))  # Exponential backoff

    print_log("[TRADIER] Failed to get session ID after retries.")
    return None

def _nyse_session(day_str: str):
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=day_str, end_date=day_str)
    if sched.empty:
        return None, None
    row = sched.iloc[0]
    # keep tz-aware NY times
    return (
        row["market_open"].tz_convert("America/New_York"),
        row["market_close"].tz_convert("America/New_York"),
    )

async def is_market_open():
    """Check if the stock market is open today using Polygon.io API."""
    url = "https://api.polygon.io/v1/marketstatus/now"
    params = {"apiKey": cred.POLYGON_API_KEY}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    print_log(f"\n[DATA_AQUISITION] 'is_market_open()' DATA: \n{data}\n")
                    market_status = data.get("market", "closed")
                    return market_status in ["open", "extended-hours"]
                else:
                    print_log(f"[ERROR] Polygon API request failed with status {response.status}: {await response.text()}")
                    return False
    except Exception as e:
        print_log(f"[ERROR] Exception in is_market_open: {e}")
        return False

async def get_account_balance(is_real_money, bp=None):
    if is_real_money:
        endpoint = f'{cred.TRADIER_BROKERAGE_BASE_URL}accounts/{cred.TRADIER_BROKERAGE_ACCOUNT_NUMBER}/balances'
        headers = {'Authorization': f"Bearer {cred.TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN}",'Accept': 'application/json'}
    else:
        endpoint = f'{cred.TRADIER_SANDBOX_BASE_URL}accounts/{cred.TRADIER_SANDBOX_ACCOUNT_NUMBER}/balances'
        headers = {'Authorization': f"Bearer {cred.TRADIER_SANDBOX_ACCESS_TOKEN}",'Accept': 'application/json'}

    response = requests.get(endpoint, headers=headers)
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()  # Raises a HTTPError if the HTTP request returned an unsuccessful status code

        try:
            json_response = response.json()
            # Assuming 'balances' is a top-level key in the JSON response:
            balances = json_response.get('balances', {})
            #print(f"balances:\n{balances}\n")

            if is_real_money and bp is None:
                return balances['total_cash']
            elif is_real_money==False:
                return balances['margin']['option_buying_power']
            elif bp is not None and True:
                return balances['cash']['cash_available']
        
        except json.decoder.JSONDecodeError as json_err:
            # Print response text to inspect what was returned
            await error_log_and_discord_message(json_err, "data_acquisition", "get_account_balance", f"JSON decode error occurred: {json_err}\nResponse text that failed to decode: {response.text}")
            return None
    except requests.exceptions.HTTPError as http_err:
        # Log additional details for the HTTP error
        await error_log_and_discord_message(http_err, "data_acquisition", "get_account_balance", f"Status code: {response.status_code}\nResponse headers: {response.headers}")
        return None
    except Exception as err:
        await error_log_and_discord_message(err, "data_acquisition","get_account_balance")
        return None

async def get_current_price() -> float:
    try:
        async with price_lock:
            if shared_state.latest_price is not None:
                return shared_state.latest_price
            else:
                print_log("[WARNING] No price data available yet.")
                return 0.0
    except Exception as e:
        print_log(f"[ERROR] Error fetching current price: {e}")
        return 0.0

async def add_markers(event_type, x=None, y=None, percentage=None, live_tf="2M"):
    
    x_coord = get_current_candle_index(live_tf) if x is None else x
    y_coord = y if y else await get_current_price()
    print_log(f"    [MARKER-{live_tf}] {x_coord}, {y_coord}, {event_type}")

    marker_styles = {
        'buy': {'marker': '^', 'color': 'blue'},
        'trim': {'marker': 'o', 'color': 'red'},
        'sell': {'marker': 'v', 'color': 'red'},
        'sim_trim_lwst': {'marker': 'o', 'color': 'orange'},
        'sim_trim_avg': {'marker': 'o', 'color': 'yellow'},
        'sim_trim_win': {'marker': 'o', 'color': 'green'}
    }
    
    marker = {
        'event_type': event_type,
        'x': x_coord,
        'y': y_coord,
        'style': marker_styles[event_type],
        'percentage': percentage
    }

    marker_path = get_markers_path(live_tf)
    marker_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if not marker_path.exists():
            with open(marker_path, 'w') as f:
                json.dump([], f)

        with open(marker_path, 'r') as f:
            markers = json.load(f)
        # Ensure markers is a list
        if not isinstance(markers, list):
            markers = []
    except (json.decoder.JSONDecodeError, FileNotFoundError):
        markers = []

    markers.append(marker)
    with open(marker_path, 'w') as f:
        json.dump(markers, f, indent=4)

async def get_candle_data_and_merge(candle_interval, candle_timescale, am_label, pm_label, indent_lvl, timeframe):
    max_ema_window = max([window for window, _ in read_config("EMAS")])
    combined_df = pd.DataFrame()
    day_offset = 1
    indent_pad = indent(indent_lvl)

    print_log(f"{indent_pad}[GCDAM] Trying to gather at least {max_ema_window} candles for {timeframe}...")

    # Fetch premarket of current day first
    start_date, end_date = get_dates(1, True)
    pre_df = await get_certain_candle_data(
        cred.POLYGON_API_KEY,
        read_config('SYMBOL'),
        candle_interval,
        candle_timescale,
        start_date,
        end_date,
        None,
        "PREMARKET",
        indent_lvl+1
    )
    if pre_df is not None:
        combined_df = pd.concat([combined_df, pre_df], ignore_index=True)

    # If that's not enough, keep pulling full day candles
    while len(combined_df) < max_ema_window:
        day_offset += 1
        start_date, end_date = get_dates(day_offset, True)

        full_df = await get_certain_candle_data(
            cred.POLYGON_API_KEY,
            read_config('SYMBOL'),
            candle_interval,
            candle_timescale,
            start_date,
            end_date,
            None,
            "ALL",
            indent_lvl+1
        )
        if full_df is not None:
            combined_df = pd.concat([full_df, combined_df], ignore_index=True)  # prepend older candles

        print_log(f"{indent_pad}→ Total gathered: {len(combined_df)} candles after offset {day_offset}")

        if day_offset > 10:
            print_log(f"{indent_pad}[WARN] Reached 10-day limit. Still short of {max_ema_window} candles.")
            break

    # Final check
    if len(combined_df) < max_ema_window:
        print_log(f"{indent_pad}[ERROR] Only collected {len(combined_df)} candles. EMA calculation skipped.")
        return None

    # Calculate EMAs
    for window, _ in read_config('EMAS'):
        col = f"EMA_{window}"
        combined_df[col] = combined_df['close'].ewm(span=window, adjust=False).mean()

    # Save
    output_path = get_merged_ema_csv_path(timeframe)
    combined_df.to_csv(output_path, index=False)
    print_log(f"{indent_pad}[GCDAM] ✅ Data saved with EMAs: `{pretty_path(output_path)}`")

    return combined_df

async def get_certain_candle_data(api_key, symbol, interval, timescale, start_date, end_date, output_path, market_type='ALL', indent_lvl=1):
    """
    Fetches interval-timescale candle data for a given symbol on a specific date, filtered by market type.

    Parameters:
    api_key (str): The API key for Polygon.io.
    symbol (str): The symbol for the financial instrument (e.g., 'AAPL', 'SPY').
    interval (int): The interval of the candles in minutes.
    timescale (str): The timescale of the candles (e.g., 'minute').
    start_date (str): The start date for the data in 'YYYY-MM-DD' format.
    end_date (str): The end date for the data in 'YYYY-MM-DD' format.
    market_type (str): The market type for filtering ('ALL', 'PREMARKET', 'MARKET', 'AFTERMARKET').

    Returns:
    None: Saves the data to a CSV file.
    """

    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{interval}/{timescale}/{start_date}/{end_date}?adjusted=true&sort=asc&apiKey={api_key}"

    try:
        response = requests.get(url)
        response.raise_for_status()

        data = response.json()
        if 'results' in data:
            df = pd.DataFrame(data['results'])
            df['timestamp'] = pd.to_datetime(df['t'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(pytz.timezone('America/New_York'))

            # session bounds per day (handles half-days)
            session_open, session_close = _nyse_session(start_date)
            if session_open is None or session_close is None:
                print_log(f"{indent(indent_lvl)}[GCCD] {start_date} not a NYSE session; isn’t a trading day, skipping.")
                return None
            
            if market_type == 'PREMARKET':
                df = df[df['timestamp'] < session_open]
            elif market_type == 'MARKET':
                df = df[(df['timestamp'] >= session_open) & (df['timestamp'] < session_close)] 
            elif market_type == 'AFTERMARKET':
                df = df[df['timestamp'] >= session_close]
            # For 'ALL', no filtering is needed

            start_time = df['timestamp'].iloc[0].strftime('%H:%M:%S')
            end_time = df['timestamp'].iloc[-1].strftime('%H:%M:%S')
            df.rename(columns={'v': 'volume', 'o': 'open', 'c': 'close', 'h': 'high', 'l': 'low'}, inplace=True)
            if output_path:
                df.to_csv(output_path, index=False)
                print_log(f"{indent(indent_lvl)}[GCCD] Data saved: `{pretty_path(output_path)}`; Candles from '{start_time}' to '{end_time}'")
            else:
                print_log(f"{indent(indent_lvl)}[GCCD] Data received; Candles from '{start_time}' to '{end_time}'.")  
            return df
        else:
            print_log(f"{indent(indent_lvl)}[GCCD] No 'results' key found in the API response.")
    except requests.exceptions.HTTPError as http_err:
        print_log(f"{indent(indent_lvl)}[GCCD] HTTP error occurred: {http_err}")
    except Exception as e:
        print_log(f"{indent(indent_lvl)}[GCCD] An unexpected error occurred: {e}")

    return None
