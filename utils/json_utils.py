# utils/json_utils.py, Load/save/validate JSON, config helpers
from pathlib import Path
import json
from shared_state import indent, print_log, safe_write_json
from utils.file_utils import get_current_candle_index
import pandas as pd
import os
from paths import pretty_path, get_ema_path, CONFIG_PATH, MARKERS_PATH, MESSAGE_IDS_PATH, ORDER_CANDLE_TYPE_PATH, PRIORITY_CANDLES_PATH, LINE_DATA_PATH

def read_config(key=None):
    """Reads the configuration file and optionally returns a specific key."""
    with CONFIG_PATH.open("r") as f:
        config = json.load(f)
    if key is None:
        return config  # Return the whole config if no key is provided
    return config.get(key)  # Return the specific key's value or None if key doesn't exist

def load_message_ids():
    if os.path.exists(MESSAGE_IDS_PATH):
        with open(MESSAGE_IDS_PATH, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    else:
        return {}

def update_config_value(key, value):
    """Update a single key in the config file with a new value."""
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    config[key] = value
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

def load_json_df(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return pd.DataFrame(data)

def initialize_json(json_path, default_value=[]):
    """Ensure the JSON file exists and is valid; initialize if not."""
    if not os.path.exists(json_path) or os.stat(json_path).st_size == 0:
        with open(json_path, 'w') as file:
            json.dump(default_value, file)  # Initialize with the default value
    try:
        with open(json_path, 'r') as file:
            return json.load(file) if isinstance(json.load(file), list) else []
    except json.JSONDecodeError:
        return []
    
def reset_json(file_path, contents):
    with open(file_path, 'w') as f:
        json.dump(contents, f, indent=4)
        print_log(f"[RESET] Cleared file: `{pretty_path(file_path)}`")

def get_correct_message_ids():
    if os.path.exists(MESSAGE_IDS_PATH):
        with open(MESSAGE_IDS_PATH, 'r') as file:
            json_message_ids_dict = json.load(file)
            #print (f"{json_message_ids_dict}")
    else:
        json_message_ids_dict = {}
    
    return json_message_ids_dict

def add_candle_type_to_json(candle_type):
    # Read the current contents of the file, or initialize an empty list if file does not exist
    try:
        with open(ORDER_CANDLE_TYPE_PATH, 'r') as file:
            candle_types = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        print_log(f"File `{pretty_path(ORDER_CANDLE_TYPE_PATH)}` not found or is empty. Starting a new list.")
        candle_types = []

    # Append the new candle_type to the list
    candle_types.append(candle_type)

    # Write the updated list back to the file
    with open(ORDER_CANDLE_TYPE_PATH, 'w') as file:
        json.dump(candle_types, file, indent=4)  # Using indent for better readability of the JSON file

def check_order_type_json(candle_type):
    try:
        with open(ORDER_CANDLE_TYPE_PATH, 'r') as file:
            candle_types = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        print_log(f"Error reading file: `{pretty_path(ORDER_CANDLE_TYPE_PATH)}` or file not found. Assuming no orders have been placed.")
        candle_types = []

    # Count how many times the given candle_type appears in the list
    num_of_matches = candle_types.count(candle_type)
    #print(num_of_matches)
    # Compare the count with the threshold
    if num_of_matches >= read_config('ORDERS_ZONE_THRESHOLD'):
        return False, num_of_matches # More or equal matches than the threshold, do not allow more orders

    return True, num_of_matches  # Fewer matches than the threshold, allow more orders

def clear_priority_candles(indent_level):
    with open(PRIORITY_CANDLES_PATH, 'w') as file:
        json.dump([], file, indent=4)
    print_log(f"{indent(indent_level)}[RESET] `{pretty_path(PRIORITY_CANDLES_PATH)}` = [];")

async def record_priority_candle(candle, zone_type_candle, timeframe):
    # Load existing data or initialize an empty list
    try:
        with open(PRIORITY_CANDLES_PATH, 'r') as file:
            candles_data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        candles_data = []

    current_candle_index = get_current_candle_index(timeframe)

    # Append the new candle data along with its type
    candle_with_type = candle.copy()
    candle_with_type['zone_type'] = zone_type_candle
    #candle_with_type['dir_type'] = bull_or_bear_candle
    candle_with_type['candle_index'] = current_candle_index
    candles_data.append(candle_with_type)

    # Save updated data back to the file
    with open(PRIORITY_CANDLES_PATH, 'w') as file:
        json.dump(candles_data, file, indent=4)

def restart_state_json(indent_level, state_file_path):
    initial_state = {
        'flag_names': [],
        'flag_type': None,
        'start_point': None,
        'slope': None,
        'intercept': None,
        'candle_points': []
        
    }
    
    with open(state_file_path, 'w') as file:
        json.dump(initial_state, file, indent=4)
    print_log(f"{indent(indent_level)}[RESET] State JSON file: `{pretty_path(state_file_path)}` has been reset to initial state.")

def resolve_flags(indent_level):
    
    if LINE_DATA_PATH.exists():
        with open(LINE_DATA_PATH, 'r') as file:
            line_data = json.load(file)
    else:
        print_log(f"{indent(indent_level)}[FLAG ERROR] File `{pretty_path(LINE_DATA_PATH)}` not found.")
        return

    # Iterate through the flags and resolve opposite flags
    updated_line_data = []
    for flag in line_data:
        #edit this part to take into account null values
        if flag['type'] and flag['status'] == 'active':
            # Mark as complete or remove the flag based on your strategy
            is_point_1_valid = flag['point_1']['x'] is not None and flag['point_1']['y'] is not None
            is_point_2_valid = flag['point_2']['x'] is not None and flag['point_2']['y'] is not None
                
            if is_point_1_valid and is_point_2_valid:
                flag['status'] = 'complete' #mark complete so its no longer edited
                updated_line_data.append(flag)
                print_log(f"{indent(indent_level)}[FLAG] Active flags resolved.")
            # Skip adding the flag to updated_line_data if it's active and has invalid points
        else:
            updated_line_data.append(flag)

    # Save the updated data back to the JSON file
    with open(LINE_DATA_PATH, 'w') as file:
        json.dump(updated_line_data, file, indent=4)

def save_message_ids(order_id, message_id):
    # Load existing data
    if MESSAGE_IDS_PATH.exists():
        with open(MESSAGE_IDS_PATH, 'r') as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = {}
    else:
        existing_data = {}

    # Update existing data with new data
    existing_data[order_id] = message_id

    # Write updated data back to file
    with open(MESSAGE_IDS_PATH, 'w') as f:
        json.dump(existing_data, f, indent=4)

def EOD_reset_all_jsons():
    """
    Reset all JSON state at EOD, including EMA files for configured timeframes.
    Uses explicit schemas for each file and logs per-file success/failure.
    """

    # Timeframes that actually have EMAs in your UI; filter from config to avoid hardcoding
    tf_with_emas = [tf for tf in read_config("TIMEFRAMES") if tf in {"2M", "5M", "15M"}]

    resets: dict[Path, object] = {
        #MARKERS_PATH: [],                                         # list of marker dicts
        MESSAGE_IDS_PATH: {},                                     # message id mapping
        #LINE_DATA_PATH: {"active_flags": [], "completed_flags": []},  # <-- keep schema
        #ORDER_CANDLE_TYPE_PATH: [],                               # list/queue
        #PRIORITY_CANDLES_PATH: [],                                # list
        **{Path(get_ema_path(tf)): [] for tf in tf_with_emas},    # all EMA files → empty list
    }

    failures = []

    # Do deterministic order (nice for logs)
    for path in sorted(resets.keys(), key=lambda x: str(x)):
        default_value = resets[path]
        try:
            ok = safe_write_json(path, default_value, indent_lvl=1)
            if ok:
                print_log(f" [EOD] Reset: {pretty_path(path)} → {type(default_value).__name__} ({len(default_value) if hasattr(default_value,'__len__') else 'n/a'})")
            else:
                failures.append((path, "`safe_write_json()` returned False"))
        except Exception as e:
            failures.append((path, str(e)))

    if failures:
        print_log(" [EOD] ⚠️ Some resets failed:")
        for path, err in failures:
            print_log(f"   - {path}: {err}")
    else:
        print_log(" [EOD] ✅ All JSON state reset successfully.")
