#error_handler.py
import traceback
from datetime import datetime
from shared_state import print_log

async def error_log_and_discord_message(e, script_name, func_name, custom_message=None):
    error_type = type(e).__name__
    error_message = str(e)
    error_traceback = traceback.format_exc()
    current_time = datetime.now().isoformat()

    #from integrations.discord.client import print_discord

    if "()" in func_name:
        func_name = func_name.replace("()", "")
    if ".py" in script_name:
        script_name = script_name.replace(".py", "")
    

    detailed_error_info = custom_message if custom_message else f"An error occurred in {script_name}.py"

    # Summarized error message for Discord
    discord_error_message = (
        f"⚠️ A critical error has occurred in `{script_name}.py`:\n"
        f"Time: {current_time}\n"
        f"Location: {func_name}()\n"
        f"Error Type: {error_type}\n"
        f"Message: {error_message}\n"
        f"Please check the logs for more details."
    )

    location = f"{script_name}.py, {func_name}()" if custom_message else f"{func_name}()"

    # Detailed error message for the console/logs
    detailed_error_message = (
        f"\n{detailed_error_info}:\n"
        f"Time: {current_time}\n"
        f"Location: {location}\n"
        f"Type: {error_type}\n"
        f"Message: {error_message}\n"
        f"Traceback:\n{error_traceback}"
    )

    #await print_discord(discord_error_message)
    print_log(detailed_error_message)
