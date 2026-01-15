import asyncio
import os

import discord
from discord.ext import commands
from discord.ui import Button, View

import cred
from error_handler import error_log_and_discord_message, print_log
from utils.order_utils import to_float

from .templates import extract_trade_results, format_day_performance


intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


class MyView(View):
    def __init__(self, button_data):
        super().__init__(timeout=None)
        for data in button_data:
            self.add_item(Button(style=data["style"], label=data["label"], custom_id=data["custom_id"]))


async def create_view(button_data):
    return MyView(button_data)


async def edit_discord_message(message_id, new_content, delete_last_message=None, file_path=None):
    channel = bot.get_channel(cred.DISCORD_CHANNEL_ID)
    if channel:
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(content=new_content)
            if file_path:
                await send_file_discord(file_path)
        except Exception as e:
            await error_log_and_discord_message(
                e,
                "integrations.discord.client",
                "edit_discord_message",
                "An error occurred when trying to edit the message",
            )
        if delete_last_message:
            async for old_message in channel.history(limit=1):
                await old_message.delete()
    else:
        print_log("Channel not found.")


async def get_message_content(message_id, line=None):
    channel = bot.get_channel(cred.DISCORD_CHANNEL_ID)
    if channel:
        try:
            message = await channel.fetch_message(message_id)
            return message.content
        except Exception:
            print_log("Message Does Not Exist!")
            return None
    else:
        print_log("Channel not found.")
        return None


async def print_discord(
    message1,
    message2=None,
    button_data=None,
    delete_last_message=None,
    show_print_statement=None,
    retries=3,
    backoff_factor=1,
):
    message_channel = bot.get_channel(cred.DISCORD_CHANNEL_ID)
    if message_channel is None:
        print_log(f"Error: Could not find a channel with ID {cred.DISCORD_CHANNEL_ID}.")
        return

    if delete_last_message:
        async for old_message in message_channel.history(limit=1):
            try:
                await old_message.delete()
            except discord.NotFound:
                print_log("Previous message not found for deletion.")
            except discord.HTTPException as e:
                print_log(f"Failed to delete previous message due to an HTTP error: {str(e)}")

    view = await create_view(button_data) if button_data else None

    for attempt in range(retries):
        try:
            if message2:
                sent_message = (
                    await message_channel.send(content=message2, view=view)
                    if button_data
                    else await message_channel.send(message2)
                )
            else:
                sent_message = (
                    await message_channel.send(content=message1, view=view)
                    if button_data
                    else await message_channel.send(message1)
                )
            return sent_message
        except (discord.HTTPException, discord.NotFound) as e:
            print_log(f"Discord API error on attempt {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(backoff_factor * (2**attempt))
    print_log("Failed to send message after retries.")
    return None


async def send_file_discord(file_path, retries=3, backoff_factor=1):
    channel = bot.get_channel(cred.DISCORD_CHANNEL_ID)
    if channel is None:
        print_log(f"Could not find channel with ID {cred.DISCORD_CHANNEL_ID}")
        return

    for attempt in range(retries):
        try:
            with open(file_path, "rb") as f:
                file_name = os.path.basename(file_path)
                image_file = discord.File(f, filename=file_name)
                await channel.send(file=image_file)
                return
        except (discord.HTTPException, discord.NotFound) as e:
            print_log(f"Discord API error on attempt {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(backoff_factor * (2**attempt))
    print_log("Failed to send file after retries.")


async def calculate_day_performance(_message_ids_dict, start_balance_str, end_balance_str):
    trades_str_list = []
    bp_float_list = []
    for message_id in _message_ids_dict.values():
        message_content = await get_message_content(message_id)
        if message_content:
            trade_info_dict = extract_trade_results(message_content, message_id)
            if isinstance(trade_info_dict, str) and "Invalid" in trade_info_dict:
                continue

            trade_info_str = (
                f"${trade_info_dict['total']:.2f}, "
                f"{trade_info_dict['percent']:.2f}%{trade_info_dict['profit_indicator']}"
            )
            trades_str_list.append(trade_info_str)
            bp_float_list.append(trade_info_dict["total_investment"])

    total_bp_used_today = sum(bp_float_list)
    start_balance = to_float(start_balance_str)
    end_balance = to_float(end_balance_str)
    profit_loss = end_balance - start_balance
    percent_gl = (profit_loss / start_balance) * 100

    return format_day_performance(
        trades_str_list=trades_str_list,
        total_bp_used_today=total_bp_used_today,
        start_balance=start_balance,
        end_balance=end_balance,
        profit_loss=profit_loss,
        percent_gl=percent_gl,
    )
