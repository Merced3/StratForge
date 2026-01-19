# main.py
from data_acquisition import get_account_balance, start_feed, stop_feed
from utils.json_utils import get_correct_message_ids, read_config, update_config_value
from utils.log_utils import clear_temp_logs_and_order_files
from utils.order_utils import initialize_csv_order_log
from indicators.ema_manager import hard_reset_ema_state, migrate_ema_state_schema
from tools.compact_parquet import end_of_day_compaction
from tools.audit_candles import audit_dayfile
from economic_calender_scraper import ensure_economic_calendar_data, setup_economic_news_message
from integrations.discord import bot, calculate_day_performance, print_discord, send_file_discord
from error_handler import error_log_and_discord_message
from options.execution_paper import PaperOrderExecutor
from options.order_manager import OptionsOrderManager
from options.position_watcher import PositionWatcher
from options.quote_hub import resolve_expiration
from options.quote_service import OptionQuoteService, TradierOptionsProvider
from runtime.market_bus import MarketEventBus
from runtime.options_trade_notifier import OptionsTradeNotifier
from runtime.options_strategy_runner import OptionsStrategyRunner, discover_strategies
from shared_state import print_log
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple
from objects import process_end_of_day_15m_candles_for_objects, pull_and_replace_15m
import cred
from utils.timezone import NY_TZ
from paths import TERMINAL_LOG, SPY_15M_ZONE_CHART_PATH, SPY_2M_CHART_PATH, SPY_5M_CHART_PATH, SPY_15M_CHART_PATH, DATA_DIR, get_ema_path
import subprocess
from pipeline.data_pipeline import run_pipeline
from pipeline.config import PipelineConfig, PipelineDeps, PipelineSinks
from session import get_session_bounds, normalize_session_times, is_market_open, wait_until_market_open
from runtime.pipeline_config_loader import load_pipeline_config
from storage.parquet_writer import append_candle
from indicators.ema_manager import update_ema
from shared_state import price_lock
import shared_state
from web_dash.refresh_client import refresh_chart
import aiohttp
import os
from contextlib import suppress


@dataclass
class OptionsRuntime:
    session: aiohttp.ClientSession
    quote_service: OptionQuoteService
    runner: OptionsStrategyRunner
    order_manager: OptionsOrderManager
    position_watcher: Optional[PositionWatcher] = None
    on_position_closed: Optional[Callable] = None

    async def stop(self) -> None:
        self.runner.stop()
        if self.position_watcher:
            await self.position_watcher.stop()
        await self.quote_service.stop()
        await self.session.close()




def _resolve_options_expiration(raw: Optional[str]) -> str:
    if not raw or str(raw).lower() == "not specified":
        raw = "0dte"
    return resolve_expiration(str(raw))


def _load_tradier_config() -> Tuple[str, str]:
    base_url = getattr(cred, "TRADIER_BROKERAGE_BASE_URL", None)
    token = getattr(cred, "TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN", None)
    if not base_url or not token:
        raise RuntimeError("Tradier config missing; set base URL and access token in cred.py")
    return base_url, token


async def start_options_runtime(
    *,
    symbol: str,
    market_bus: MarketEventBus,
    poll_interval: float = 1.0,
) -> Optional[OptionsRuntime]:
    if os.getenv("PYTEST_CURRENT_TEST"):
        print_log("[OPTIONS] Skipping options runtime under pytest.")
        return None

    strategies = discover_strategies()
    if not strategies:
        print_log("[OPTIONS] No strategies found; skipping options runtime.")
        return None

    try:
        expiration = _resolve_options_expiration(read_config("OPTION_EXPIRATION_DTE"))
        max_otm = read_config("NUM_OUT_OF_MONEY")
    except Exception as e:
        print_log(f"[OPTIONS] Config missing for options runtime: {e}")
        return None
    order_quantity = 1
    try:
        base_url, token = _load_tradier_config()
    except Exception as e:
        print_log(f"[OPTIONS] Tradier config unavailable: {e}")
        return None

    session = aiohttp.ClientSession()
    try:
        provider = TradierOptionsProvider(
            session=session,
            base_url=base_url,
            access_token=token,
            logger=print_log,
        )
        quote_service = OptionQuoteService(
            provider,
            symbol=symbol,
            expiration=expiration,
            poll_interval=poll_interval,
            logger=print_log,
        )
        await quote_service.start()

        executor = PaperOrderExecutor(quote_service.get_quote, logger=print_log)
        order_manager = OptionsOrderManager(quote_service, executor, logger=print_log)
        notifier = OptionsTradeNotifier(order_manager, logger=print_log)
        position_watcher = PositionWatcher(
            quote_service,
            lambda: order_manager.list_positions().values(),
            refresh_interval=1.0,
            logger=print_log,
        )
        await position_watcher.start()

        runner = OptionsStrategyRunner(
            market_bus,
            order_manager,
            strategies,
            expiration=expiration,
            selector_name="price-range-otm",
            max_otm=max_otm,
            order_quantity=order_quantity,
            position_watcher=position_watcher,
            on_position_opened=notifier.on_position_opened,
            on_position_closed=notifier.on_position_closed,
            on_position_added=notifier.on_position_added,
            on_position_trimmed=notifier.on_position_trimmed,
            logger=print_log,
        )
        runner.start()
        print_log(f"[OPTIONS] Started {len(strategies)} strategy(ies) with expiration={expiration}.")
        return OptionsRuntime(
            session=session,
            quote_service=quote_service,
            runner=runner,
            order_manager=order_manager,
            position_watcher=position_watcher,
            on_position_closed=notifier.on_position_closed,
        )
    except Exception:
        await session.close()
        raise


async def schedule_options_eod_close(
    order_manager: OptionsOrderManager,
    market_close: datetime,
    buffer_minutes: int = 1,
    on_position_closed=None,
) -> None:
    target = market_close - timedelta(minutes=buffer_minutes)
    now = datetime.now(NY_TZ)
    if now >= target:
        print_log("[OPTIONS] EOD close target already reached; closing positions now.")
        results = await order_manager.close_all_positions()
        if on_position_closed:
            for result in results:
                position = order_manager.get_position(result.position_id)
                if position:
                    try:
                        maybe = on_position_closed(position, result.order_result, "EOD close")
                        if asyncio.iscoroutine(maybe):
                            await maybe
                    except Exception as exc:
                        print_log(f"[OPTIONS] EOD close notify failed: {exc}")
        return
    print_log(f"[OPTIONS] EOD close scheduled for {target.strftime('%Y-%m-%d %H:%M:%S')}.")
    await asyncio.sleep((target - now).total_seconds())
    results = await order_manager.close_all_positions()
    if on_position_closed:
        for result in results:
            position = order_manager.get_position(result.position_id)
            if position:
                try:
                    maybe = on_position_closed(position, result.order_result, "EOD close")
                    if asyncio.iscoroutine(maybe):
                        await maybe
                except Exception as exc:
                    print_log(f"[OPTIONS] EOD close notify failed: {exc}")

async def bot_start():
    await bot.start(cred.DISCORD_TOKEN)
    print_log("Discord bot started.")

_auto_heal_task = None

async def initial_setup():
    await bot.wait_until_ready()
    print_log(f"We have logged in as {bot.user}")
    await print_discord(f"Starting Bot, Real Money Activated" if read_config('REAL_MONEY_ACTIVATED') else f"Starting Bot, Paper Trading Activated")

async def main():
    last_run_date = None  # To track the last date the functions ran
    last_weekend_message_date = None  # To track the last weekend message date

    while True:
        try:
            pipeline_cfg = load_pipeline_config()
            # Get the current time in New York timezone
            current_time = datetime.now(NY_TZ)
            current_date = current_time.date()  # Extract the date (e.g., 2024-06-12)

            session_open, session_close = get_session_bounds(current_date.strftime("%Y-%m-%d"))
            if not session_open or not session_close:
                if last_weekend_message_date != current_date:
                    print_log(f"[INFO] No NYSE session on {current_time.strftime('%Y-%m-%d (%A)')}. Waiting for the next trading day...")
                    last_weekend_message_date = current_date
                await asyncio.sleep(10)
                continue

            # Set target time to 10 minutes before market open
            target_time = session_open - timedelta(minutes=10)

            # Check if it's time to run and hasn't already run today
            if current_time >= target_time and last_run_date != current_date:
                print_log(f"[INFO] Running initial_setup and main_loop at {current_time.strftime('%Y-%m-%d %H:%M:%S')} (session {session_open.strftime('%H:%M')} - {session_close.strftime('%H:%M')})")

                # 10 min before open: enforce clean EMA state for the day
                migrate_ema_state_schema()             # drop legacy keys like 'seen_ts'
                hard_reset_ema_state(pipeline_cfg["timeframes"])       # clear per-TF candle_list + has_calculated
                
                # Pre-open setup
                await ensure_economic_calendar_data()
                await refresh_chart("15M", chart_type="zones")

                # Run the initial setup
                await initial_setup()
                
                # Run the main loop if markets are open
                if await is_market_open():
                    await main_loop(session_open, session_close) 
                else:
                    print_log(f"Markets are closed today: {current_time.strftime('%m/%d/%Y - %A')}") # "Markets are closed today: 1/1/2025 - Wednesday"
                    await print_discord("**MARKETS ARE CLOSED TODAY**")
                    
                last_run_date = current_date  # Update the last run date

                print_log("[INFO] initial_setup and main_loop completed successfully.")
                print_log("Waiting until the next session's pre-open window...")

            # Sleep for 10 seconds before checking again
            await asyncio.sleep(10)

        except Exception as e:
            print_log(f"[ERROR] Exception in main loop: {e}")
            await asyncio.sleep(10)  # Avoid tight loops in case of errors

async def main_loop(session_open, session_close):
    queue = asyncio.Queue()
    session_open, session_close = normalize_session_times(session_open, session_close)
    market_bus = MarketEventBus(logger=print_log)
    options_runtime: Optional[OptionsRuntime] = None
    options_eod_task: Optional[asyncio.Task] = None

    current_time = datetime.now(NY_TZ)
    market_open_time = session_open
    market_close_time = session_close
    trading_day_str = market_close_time.astimezone(NY_TZ).strftime("%Y-%m-%d")
    config = PipelineConfig(**load_pipeline_config())

    if not market_open_time or not market_close_time:
        print_log("[INFO] No NYSE session for today. Skipping `main_loop()`.")
        return

    if current_time >= market_close_time:
        print_log("[INFO] Market already closed. Skipping `main_loop()` and `EOD`.")
        return

    if current_time < market_open_time:
        await wait_until_market_open(market_open_time, NY_TZ)

    initialize_csv_order_log()

    did_run_intraday = False
    feed_handle = None
    try:
        feed_handle = await start_feed(config.symbol, queue)
        try:
            options_runtime = await start_options_runtime(
                symbol=config.symbol,
                market_bus=market_bus,
            )
            if options_runtime:
                options_eod_task = asyncio.create_task(
                    schedule_options_eod_close(
                        options_runtime.order_manager,
                        session_close,
                        on_position_closed=options_runtime.on_position_closed,
                    ),
                    name="OptionsEODClose",
                )
        except Exception as e:
            print_log(f"[OPTIONS] Failed to start options runtime: {e}")

        start_of_day_account_balance = await get_account_balance(read_config('REAL_MONEY_ACTIVATED')) if read_config('REAL_MONEY_ACTIVATED') else read_config('START_OF_DAY_BALANCE')
        f_s_account_balance = "{:,.2f}".format(start_of_day_account_balance)
        await print_discord(f"Market is Open! Account BP: ${f_s_account_balance}")
        await send_file_discord(SPY_15M_ZONE_CHART_PATH)
        await print_discord(setup_economic_news_message())

        did_run_intraday = True
        
        deps = PipelineDeps(get_session_bounds=get_session_bounds, latest_price_lock=price_lock, shared_state=shared_state)
        sinks = PipelineSinks(
            append_candle=append_candle,
            update_ema=update_ema,
            refresh_chart=refresh_chart,
            on_error=error_log_and_discord_message,
            on_candle_close=market_bus.publish_candle_close,
        )

        task = asyncio.create_task(run_pipeline(queue, config, deps, sinks), name="DataPipeline")
        await task

    except Exception as e:
        await error_log_and_discord_message(e, "main", "main_loop")

    finally:
        if options_eod_task:
            options_eod_task.cancel()
            with suppress(asyncio.CancelledError):
                await options_eod_task
        if options_runtime:
            await options_runtime.stop()
        if feed_handle:
            await stop_feed(feed_handle)
        await asyncio.sleep(10)
        if did_run_intraday:
            await process_end_of_day(trading_day_str)
        else:
            print_log("[INFO] Session ended without intraday work; skipping EOD.")

async def process_end_of_day(trading_day_str: Optional[str] = None):
    # 1. Get balances and calculate P/L
    rma = read_config('REAL_MONEY_ACTIVATED')
    start_of_day_account_balance = await get_account_balance(rma) if rma else read_config('START_OF_DAY_BALANCE')
    todays_profit_loss = 0 #sum(get_profit_loss_orders_list())
    end_of_day_account_balance = start_of_day_account_balance + todays_profit_loss
    
    # 2. Announce/report to Discord
    f_e_account_balance = "{:,.2f}".format(end_of_day_account_balance)
    await print_discord(f"Market is closed. Today's closing balance: ${f_e_account_balance}")
    message_ids_dict = get_correct_message_ids()
    output_message = await calculate_day_performance(message_ids_dict, start_of_day_account_balance, end_of_day_account_balance)
    await print_discord(output_message)

    # 3. Send relevant images + files to Discord
    today_chart_info = {
        "2M": SPY_2M_CHART_PATH,
        "5M": SPY_5M_CHART_PATH,
        "15M": SPY_15M_CHART_PATH
    }
    for tf, chart_path in today_chart_info.items():
        files = [chart_path, get_ema_path(tf)] # CANDLE_LOGS.get(tf), don't send log file anymore, we have parquet files now.
        for f in files:
            if not f:
                continue
            try:
                await send_file_discord(f)
            except Exception as e:
                print_log(f"[WARN] Failed to send {tf} file {f}: {e}")

    #await send_file_discord(MARKERS_PATH)
    await send_file_discord(TERMINAL_LOG)

    # 4. Administrative/config updates (do this last so nothing breaks mid-report)
    update_config_value('START_OF_DAY_BALANCE', end_of_day_account_balance)

    # 5. Reset all data for next session
    #clear_all_states() # from flag manager script
    clear_temp_logs_and_order_files()
    #reset_profit_loss_orders_list()

    # 6. Storage compaction (safe to call daily; no-op if nothing to do)
    day = trading_day_str or datetime.now(NY_TZ).strftime("%Y-%m-%d")
    end_of_day_compaction(day, TFs=["2m","5m","15m"])
    process_end_of_day_15m_candles_for_objects()
    schedule_auto_heal(day) # Just incase of any data issues, websocket drops, missing candles, ect.

def schedule_auto_heal(day_str: str, delay_minutes: int = 20):
    """Fire-and-forget healer run for a given trading day after a delay."""
    global _auto_heal_task
    if _auto_heal_task and not _auto_heal_task.done():
        _auto_heal_task.cancel()

    async def _runner():
        print_log(f"[AUTO-HEAL] Scheduled for {day_str} in {delay_minutes}m")
        await asyncio.sleep(delay_minutes * 60)

        day_path = DATA_DIR / "15m" / f"{day_str}.parquet"
        audit = None
        try:
            if day_path.exists():
                audit = audit_dayfile(day_path, tf_minutes=15, tz=NY_TZ)
                if audit.get("missing_count") == 0 and audit.get("extras_count") == 0 and audit.get("gx_ok"):
                    print_log(f"[AUTO-HEAL] Audit clean for {day_str}; skipping heal.")
                    return
                print_log(f"[AUTO-HEAL] Audit issues for {day_str}: missing={audit.get('missing_count')}, extras={audit.get('extras_count')}, gx_ok={audit.get('gx_ok')}")
            else:
                print_log(f"[AUTO-HEAL] No dayfile for {day_str}; treating as missing and healing.")
        except Exception as e:
            print_log(f"[AUTO-HEAL] Audit failed for {day_str}, proceeding to heal: {e}")
            
        try:    
            print_log(f"[AUTO-HEAL] Starting heal for {day_str}")
            await pull_and_replace_15m(day_override=day_str)
            print_log(f"[AUTO-HEAL] Completed heal for {day_str}")
        except Exception as e:
            print_log(f"[AUTO-HEAL] failed for {day_str}: {e}")

    _auto_heal_task = asyncio.create_task(_runner(), name=f"AUTO-HEAL-{day_str}")

async def shutdown(loop):
    """Shutdown tasks and the Discord bot."""
    # Gracefully shutdown the Discord bot
    await bot.close()  # Make sure this is the correct way to close your bot instance
    # Cancel all remaining tasks
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()

if __name__ == "__main__":
    print_log("Starting the main trading bot...")
    loop = asyncio.get_event_loop()

    #subprocess.Popen(["python", "web_dash/dash_app.py"])
    subprocess.Popen(["uvicorn", "web_dash.ws_server:app"])
    
    # Start bot and main loop
    loop.create_task(bot_start(), name="DiscordBotStart")
    loop.create_task(main(), name="MainLoop")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print_log("Manually interrupted, cleaning up...")
        loop.run_until_complete(shutdown(loop))
    finally:
        loop.close()
        
