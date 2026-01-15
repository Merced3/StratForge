import re


def extract_trade_results(message, message_id):
    # Keep only chars we expect in the formatted Discord message.
    clean_message = "".join(
        e
        for e in message
        if (e.isalnum() or e.isspace() or e in ["$", "%", ".", ":", "-", "ƒo.", "ƒ?O"])
    )

    investment_pattern = r"Total Investment: \$(.+)"
    investment_match = re.search(investment_pattern, clean_message)
    total_investment = float(investment_match.group(1).replace(",", "")) if investment_match else 0.0

    results_pattern = (
        r"AVG BID:\s*\$([\d,]+\.\d{3})\s*TOTAL:\s*(-?\$\-?[\d,]+\.\d{2})\s*(ƒo.|ƒ?O)\s*"
        r"PERCENT:\s*(-?\d+\.\d{2})%"
    )
    results_match = re.search(results_pattern, clean_message, re.DOTALL)

    if results_match:
        avg_bid = float(results_match.group(1))
        total_str = results_match.group(2).replace(",", "").replace("$", "")
        total = float(total_str) if total_str else 0.0
        profit_indicator = results_match.group(3)
        percent = float(results_match.group(4))
        return {
            "avg_bid": avg_bid,
            "total": total,
            "profit_indicator": profit_indicator,
            "percent": percent,
            "total_investment": total_investment,
        }
    return f"Invalid Results Details for message ID {message_id}"


def format_day_performance(
    trades_str_list,
    total_bp_used_today,
    start_balance,
    end_balance,
    profit_loss,
    percent_gl,
):
    trades_str = "\n".join(trades_str_list)
    return f"""
All Trades:
{trades_str}

Total BP Used Today:
${total_bp_used_today:,.2f}

Account balance:
Start: ${"{:,.2f}".format(start_balance)}
End: ${"{:,.2f}".format(end_balance)}

Profit/Loss: ${profit_loss:,.2f}
Percent Gain/Loss: {percent_gl:.2f}%
"""
