# utils/ema_utils.py, EMA calculations and JSON handling
import json
import pandas as pd
from utils.json_utils import read_config, load_json_df
from shared_state import indent, print_log, safe_write_json, safe_read_json
from paths import get_ema_path, get_merged_ema_csv_path, pretty_path, CANDLE_LOGS
from error_handler import error_log_and_discord_message

async def read_ema_json(position, timeframe):
    path = get_ema_path(timeframe)
    try:
        with open(path, "r") as file:
            emas = json.load(file)
            latest_ema = emas[position]
            return latest_ema
    except FileNotFoundError:
        print_log(f"`{pretty_path(path)}` file not found.")
        return None
    except KeyError:
        print_log(f"EMA type [{position}] not found in `{pretty_path(path)}`.")
        return None
    except Exception as e:
        await error_log_and_discord_message(e, "ema_utils", "read_ema_json")
        return None

async def calculate_save_EMAs(candle, X_value, timeframe):
    """
    Process a single candle: Adds it to CSV, Recalculate EMAs, Saves EMAs to JSON file.
    """
    path = get_ema_path(timeframe)
    required_columns = ['timestamp', 'open', 'high', 'low', 'close']
    csv_path = get_merged_ema_csv_path(timeframe)

    # Load or init
    try:
        df = pd.read_csv(csv_path)
        df = df[required_columns] if not df.empty else pd.DataFrame(columns=required_columns)
    except FileNotFoundError:
        df = pd.DataFrame(columns=required_columns)

    # Fix candle
    candle_df = pd.DataFrame([candle])
    for col in required_columns:
        if col not in candle_df.columns:
            candle_df[col] = pd.Timestamp.now().isoformat() if col == 'timestamp' else 0.0

    candle_df = candle_df[required_columns]  # Ensure correct column order
    df = pd.concat([df, candle_df], ignore_index=True) #if not candle_df.empty: # Concat only if valid
    df.to_csv(csv_path, mode='w', header=True, index=False)

    # EMAs
    current_ema_values = {}
    for window, _ in read_config('EMAS'):  # window, color
        ema_col = f"EMA_{window}"
        df[ema_col] = df['close'].ewm(span=window, adjust=False).mean()
        #ts_val = candle.get("timestamp")
        current_ema_values[str(window)] = df[ema_col].iloc[-1]

    current_ema_values['x'] = X_value
    #current_ema_values["ts"] = ts_val
    update_ema_json(path, current_ema_values)

def get_latest_ema_values(ema_type, timeframe):
    path = get_ema_path(timeframe)

    # Check if the file is empty before reading
    if not path.exists() or path.stat().st_size == 0:
        print_log(f"    [GLEV] `{pretty_path(path)}` is empty or missing.")
        return None, None

    try:
        emas = safe_read_json(path)

        if not emas:  # Check if the file is empty or contains no data
            print_log(f"    [GLEV] `{pretty_path(path)}` is empty or contains no data.")
            return None, None
        
        return emas[-1].get(ema_type), emas[-1].get("x")
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print_log(f"    [GLEV] EMA error: {e}")
        return None, None

def is_ema_broke(ema_type, timeframe, cp, indent_lvl=1):
    # Get EMA Data
    latest_ema, index_ema = get_latest_ema_values(ema_type, timeframe)
    if latest_ema is None or index_ema is None:
        return False
    
    # Get Candle Data
    filepath = CANDLE_LOGS.get(timeframe)
    try:
        with open(filepath, "r") as file:
            lines = file.readlines()
            latest_candle = json.loads(lines[-1])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print_log(f"Log file error: {e}")
        return False

    index_candle = len(lines) - 1
    if index_candle == index_ema:
        open_price = latest_candle["open"]
        close_price = latest_candle["close"]

        # Check conditions based on option type
        if open_price and close_price:
            if cp == 'call' and latest_ema > close_price:
                print_log(f"{indent(indent_lvl)}[EMA BROKE] {ema_type}EMA Hit, SELL CALL at {close_price} < EMA {latest_ema}")
                return True
            elif cp == 'put' and latest_ema < close_price:
                print_log(f"{indent(indent_lvl)}[EMA BROKE] {ema_type}EMA Hit, SELL PUT at {close_price} > EMA {latest_ema}")
                return True
        else:
            print_log(f"{indent(indent_lvl)}[IEB {ema_type} EMA] unable to get open and close price... Candle OC: {open_price}, {close_price}")
    else:
        # Print the indices to show they don't match and wait before trying again
        print_log(f"{indent(indent_lvl)}[IEB {ema_type} EMA]\n{indent(indent_lvl)}index_candle: {index_candle}; Length Lines: {len(lines)}\n{indent(indent_lvl)}index_ema: {index_ema}; latest ema: {latest_ema}; Indices do not match...")

    return False

def update_ema_json(json_path, new_ema_values):
    """Update the EMA JSON file with new EMA values by appending."""
    ema_data = safe_read_json(json_path)

    # Append new EMA values
    ema_data.append(new_ema_values)

    # Write the updated list back to the file
    safe_write_json(json_path, ema_data)

def get_last_emas(timeframe, indent_lvl=1, print_statements=True):
    path= get_ema_path(timeframe)
    EMAs = load_json_df(path)
    if EMAs.empty:
        if print_statements:
            print_log(f"{indent(indent_lvl)}[GET-EMAs] ERROR: data `{pretty_path(path)}` is unavailable.")
        return None
    last_EMA = EMAs.iloc[-1]
    emas = last_EMA.to_dict()
    if print_statements:
        print_log(f"{indent(indent_lvl)}[GET-EMAs] x: {emas['x']}, 13: {emas['13']:.2f}, 48: {emas['48']:.2f}, 200: {emas['200']:.2f}")
    return emas

def load_ema_json(path):
    try:
        data = safe_read_json(path, default=[])
        return data if isinstance(data, list) and data else None
    except:
        return None
    