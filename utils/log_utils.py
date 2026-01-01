# utils/log_utils.py
import json
from shared_state import print_log
from paths import pretty_path, get_markers_path, LOGS_DIR, STORAGE_DIR, CSV_DIR, TERMINAL_LOG, ORDER_LOG_PATH, SPY_15_MINUTE_CANDLES_PATH
from utils.json_utils import read_config, EOD_reset_all_jsons, reset_json
import pandas as pd
import os

def read_log_to_df(log_file_path):
    """Read log data into a DataFrame."""
    return pd.read_json(log_file_path, lines=True)

def write_to_log(data, symbol, timeframe):
    filepath = LOGS_DIR / f"{symbol}_{timeframe}.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with filepath.open("a") as file:
        json_data = json.dumps(data)
        file.write(json_data + "\n")

def clear_log(symbol=None, timeframe=None, terminal_log=None):
    filepath = None
    if symbol and timeframe:
        filepath = LOGS_DIR / f"{symbol}_{timeframe}.log"
    if terminal_log:
        filepath = LOGS_DIR / terminal_log
    if filepath and filepath.exists():
        filepath.unlink()

def empty_log(filename):
    """
    Empties the contents of the specified log file.

    Args:
    filename (str): The base name of the log file without extension.
    """
    # Ensure the logs directory exists
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    # Path to the log file
    log_file_path = os.path.join(LOGS_DIR, f'{filename}.log')

    # Open the file in write mode to truncate it
    with open(log_file_path, 'w') as file:
        pass  # Opening in write mode ('w') truncates the file automatically

    print_log(f"[CLEARED]'{filename}.log' has been emptied.")

def clear_symbol_log(symbol, timeframe):
    filepath = LOGS_DIR / f"{symbol}_{timeframe}.log"
    if filepath.exists():
        filepath.unlink()

def clear_terminal_log():
    if TERMINAL_LOG.exists():
        TERMINAL_LOG.unlink()

def clear_temp_logs_and_order_files():
    # Only keep the main order archive
    protected_files = {
        ORDER_LOG_PATH,
        SPY_15_MINUTE_CANDLES_PATH
    }

    files_to_delete = set()

    # 1. Delete temp order_log* files and all CSVs in logs/ (except protected)
    for file_path in STORAGE_DIR.glob('*order_log*'):
        if file_path not in protected_files:
            files_to_delete.add(file_path)
    for file_path in CSV_DIR.glob('*.csv'):
        if file_path not in protected_files:
            files_to_delete.add(file_path)

    # 2. Clean all relevant JSON state files
    EOD_reset_all_jsons()

    # 3. Delete all files found in logs/
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            print_log(f"[RESET] Deleted file: `{pretty_path(file_path)}`")
        except Exception as e:
            print_log(f"An error occurred while deleting `{pretty_path(file_path)}`: {e}")

    # 4. Still clear symbol, terminal logs, markers, ect...
    tfs = ["2M", "5M", "15M"]
    for tf in tfs:
        clear_symbol_log(read_config('SYMBOL'), tf)
        reset_json(get_markers_path(tf), [])
    clear_terminal_log()

def read_last_n_lines(file_path, n):
    # Ensure the logs directory exists
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)

    # Check if the file exists, if not, create an empty file
    if not os.path.isfile(file_path):
        with open(file_path, 'w') as file:
            pass

    with open(file_path, 'r') as file:
        lines = file.readlines()
        last_n_lines = lines[-n:]
        return [json.loads(line.strip()) for line in last_n_lines]
