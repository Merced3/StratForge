# buy_option.py
from error_handler import error_log_and_discord_message
from order_handler import get_unique_order_id_and_is_active, manage_active_order
from legacy.options_v1.submit_order import find_what_to_buy, submit_option_order, get_order_status
from utils.order_utils import get_expiration, calculate_quantity, build_active_order
from utils.json_utils import read_config
from data_acquisition import get_account_balance, add_markers
#from integrations.discord.client import print_discord
from datetime import datetime
import asyncio

message_ids_dict = {}
used_buying_power = {}

def get_papertrade_BP():
    #get every orders cost that is in USED_BUYING_POWER, calculate how much all of it added togther costs
    all_order_costs = sum(used_buying_power.values())
    current_balance = read_config("START_OF_DAY_BALANCE")
    current_bp_left = current_balance - all_order_costs
    return current_bp_left

def reset_usedBP_messageIDs():
    used_buying_power.clear()
    message_ids_dict.clear()

async def buy_option_cp(real_money_activated, ticker_symbol, cp, TP_value, session, headers, strategy_name):
    unique_order_id, current_order_active = get_unique_order_id_and_is_active()
    prev_option_type = unique_order_id.split('-')[1] if unique_order_id else None

    if current_order_active: # and prev_option_type == cp: Trying to keep it simple
        return False, None, None, None, None, "Another Order Active."
    #elif current_order_active and prev_option_type != cp:
        # IDK if we should keep this because it auto got out of a order and tried to get into another one while seniment was 0. idk if thats in accordance to this strategy.
        # Sell the current active order if it's of a different type
        #await sell_rest_of_active_order(message_ids_dict, "Switching option type.")

    try:
        bid = None
        side = "buy_to_open"
        order_type = "market"  # order_type = "limit" if bid else "market"
        expiration_date = get_expiration(read_config('OPTION_EXPIRATION_DTE'))
        
        strike_price, strike_ask_bid = await find_what_to_buy(
            ticker_symbol, cp, read_config('NUM_OUT_OF_MONEY'), expiration_date, TP_value, session, headers
        )
        
        if strike_price is None or strike_ask_bid is None:
            #await print_discord(f"**Appropriate strike was not found**\nstrike_price = None, Canceling buy.\n(Since not enough info)")
            return False, None, None, None, None, "Strike Price Not Found, Canceling Buy."
        
        quantity = calculate_quantity(strike_ask_bid, read_config('ACCOUNT_ORDER_PERCENTAGE'))    
        buying_power = await get_account_balance(real_money_activated, bp=True) if real_money_activated else get_papertrade_BP()
        
        commission_fee = 0.35
        buffer = 0.25
        strike_bid_cost = strike_ask_bid * 100 # 0.32 is actually 32$ when dealing with option contracts
        order_cost = (strike_bid_cost + commission_fee) * quantity
        order_cost_buffer = ((strike_bid_cost+buffer) + commission_fee) * quantity
        
        f_order_cost = f"{order_cost:,.2f}" # 'f_' means formatted
        f_order_cost_buffer = f"{order_cost_buffer:,.2f}" # formatted
      
#       if order_cost_buffer >= buying_power:
#            await print_discord(f"""
#**NOT ENOUGH BUYING POWER LEFT**
#-----
#Canceling Order for Strategy: 
#**{strategy_name}**
#-----
#**Buying Power:** ${buying_power}
#**Order Cost Buffer:** ${f_order_cost_buffer}
#Order Cost Buffer exceded BP
#-----
#**Strike Price:** {strike_price}
#**Option Type:** {cp}
#**Quantity:** {quantity} contracts
#**Price:** ${strike_ask_bid}
#**Total Cost:** ${f_order_cost}
#""")
#            return False, None, None, None, None, "Not Enough Buying Power."

        if real_money_activated: 
            order_result = await submit_option_order(strategy_name, ticker_symbol, strike_price, cp, bid, expiration_date, quantity, side, order_type)
            
            if not order_result:
                return False, None, None, None, None, "No return on `order_result`."
            
            await add_markers("buy", None, None, 0)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            unique_order_ID, entry_price, quantity = await get_order_status(
                strategy_name, True, order_result['order_id'], "buy", 
                ticker_symbol, cp, strike_price, expiration_date, 
                timestamp, message_ids_dict
            )
            active_order = build_active_order(
                unique_order_ID, order_result['order_id'], entry_price, quantity, TP_value=TP_value
            )
        else: # Not Real Money
            active_order = await submit_option_order(
                strategy_name, ticker_symbol, strike_price,
                cp, bid, expiration_date, 
                session=session, headers=headers, 
                message_ids_dict=message_ids_dict, 
                buying_power=buying_power,
                TP_value=TP_value
            )
            if not active_order:
                return False, None, None, None, None, "`active_order` returned as None"
            
            await add_markers("buy", None, None, 0)
            used_buying_power[active_order['order_id']] = (active_order["entry_price"] * 100) * active_order["quantity"]
        
        # Start Managing Order
        asyncio.create_task(
            manage_active_order(active_order, message_ids_dict),
            name=f"OrderManaging_{active_order['order_id']}"
        )
        
        order_cost = (active_order["entry_price"] * 100) * active_order["quantity"]
        return True, strike_price, active_order["quantity"], active_order["entry_price"], order_cost, None

    except Exception as e:
        await error_log_and_discord_message(e, "buy_option", "buy_option_cp")
        return False, None, None, None, None, f"Error: {e}"
