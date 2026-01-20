import re
from datetime import datetime, time
from typing import Iterable, Optional


def extract_trade_results(message, message_id):
    clean_message = _strip_markdown(message)

    investment_match = re.search(r"Total Investment:\s*\$([0-9,]+(?:\.\d+)?)", clean_message)
    total_investment = (
        float(investment_match.group(1).replace(",", "")) if investment_match else 0.0
    )

    results_match = re.search(
        r"AVG BID:\s*\$([0-9,]+(?:\.\d+)?)\s*TOTAL:\s*\$?(-?[0-9,]+(?:\.\d+)?)\s*([✅❌])?\s*"
        r"PERCENT:\s*(-?\d+(?:\.\d+)?)%",
        clean_message,
        re.DOTALL,
    )
    if results_match:
        avg_bid = float(results_match.group(1).replace(",", ""))
        total_str = results_match.group(2).replace(",", "").replace("$", "")
        total = float(total_str) if total_str else 0.0
        profit_indicator = results_match.group(3)
        if not profit_indicator:
            profit_indicator = "✅" if total >= 0 else "❌"
        percent = float(results_match.group(4))
        return {
            "avg_bid": avg_bid,
            "total": total,
            "profit_indicator": profit_indicator,
            "percent": percent,
            "total_investment": total_investment,
        }
    return f"Invalid Results Details for message ID {message_id}"


def extract_trade_totals(message: str) -> dict:
    clean_message = _strip_markdown(message)
    entry_total = _parse_labeled_money(clean_message, "Total Investment") or 0.0

    added_total = 0.0
    sold_total = 0.0
    sold_qty = 0

    for qty, total in re.findall(
        r"^Added\s+(\d+)\s+for\s+\$([0-9,]+(?:\.\d+)?)",
        clean_message,
        re.MULTILINE,
    ):
        try:
            added_total += float(total.replace(",", ""))
        except ValueError:
            continue

    for qty, total in re.findall(
        r"^Sold\s+(\d+)\s+for\s+\$([0-9,]+(?:\.\d+)?)",
        clean_message,
        re.MULTILINE,
    ):
        try:
            sold_qty += int(qty)
            sold_total += float(total.replace(",", ""))
        except ValueError:
            continue

    return {
        "total_entry_cost": entry_total + added_total,
        "total_exit_value": sold_total,
        "total_exit_qty": sold_qty,
    }


def format_trade_open(
    strategy_name: str,
    ticker_symbol: str,
    strike: float,
    option_type: str,
    quantity: int,
    order_price: Optional[float],
    total_investment: Optional[float],
    reason: Optional[str] = None,
) -> str:
    lines = [
        f"**{strategy_name}**",
        "-----",
        f"**Ticker Symbol:** {ticker_symbol}",
        f"**Strike Price:** {strike}",
        f"**Option Type:** {option_type}",
        f"**Quantity:** {quantity} contracts",
        f"**Price:** {_format_money(order_price)}",
        f"**Total Investment:** {_format_money(total_investment)}",
    ]
    if reason:
        lines.append(f"**Reason:** {reason}")
    lines.append("-----")
    return "\n".join(lines)


def format_trade_add(
    quantity: int,
    total_value: Optional[float],
    fill_price: Optional[float],
    reason: Optional[str] = None,
) -> str:
    line = f"Added {quantity} for {_format_money(total_value)}, Fill: {_format_price(fill_price)}"
    if reason:
        line = f"{line} | {reason}"
    return line


def format_trade_trim(
    quantity: int,
    total_value: Optional[float],
    fill_price: Optional[float],
    reason: Optional[str] = None,
) -> str:
    line = f"Sold {quantity} for {_format_money(total_value)}, Fill: {_format_price(fill_price)}"
    if reason:
        line = f"{line} | {reason}"
    return line


def format_trade_close(
    avg_exit: Optional[float],
    total_pnl: Optional[float],
    percent: Optional[float],
    profit_indicator: Optional[str],
) -> str:
    total_str = _format_signed_money(total_pnl)
    indicator = profit_indicator or ("✅" if (total_pnl or 0) >= 0 else "❌")
    percent_str = "n/a" if percent is None else f"{percent:.2f}%"
    avg_str = _format_price(avg_exit, precision=3)
    avg_label = f"${avg_str}" if avg_str != "n/a" else avg_str
    return (
        "\n-----\n"
        f"**AVG BID:**    {avg_label}\n"
        f"**TOTAL:**    {total_str}{indicator}\n"
        f"**PERCENT:**    {percent_str}"
    )


def append_trade_update(message: str, update_line: str) -> str:
    if not message:
        return update_line
    separator = "" if message.endswith("\n") else "\n"
    return f"{message}{separator}{update_line}"


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


def format_economic_news_message(
    events: Iterable,
    header: str = "TODAYS MAJOR ECONOMIC NEWS",
    empty_message: str = "NO MAJOR NEWS EVENTS TODAY",
) -> str:
    grouped = _group_economic_events(events)
    if not grouped:
        return f"**{empty_message}**"

    lines = [f"**{header}**", "-----"]
    for time_label in _sorted_time_labels(grouped.keys()):
        lines.append(f"**{time_label}**")
        for title in grouped[time_label]:
            lines.append(f"- {title}")
        lines.append("")
    return "\n".join(lines).strip()


def _strip_markdown(message: str) -> str:
    return message.replace("**", "").replace("__", "").replace("`", "")


def _parse_labeled_money(message: str, label: str) -> Optional[float]:
    match = re.search(rf"{re.escape(label)}:\s*\$([0-9,]+(?:\.\d+)?)", message)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _format_price(value: Optional[float], precision: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{precision}f}"


def _format_money(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"${value:.2f}"


def _format_signed_money(value: Optional[float]) -> str:
    if value is None:
        return "$0.00"
    return f"${value:.2f}"


def _group_economic_events(events: Iterable) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for event in events or []:
        time_label = getattr(event, "time_label", None)
        title = getattr(event, "title", None)
        if not time_label or not title:
            continue
        time_label = str(time_label).strip()
        title = str(title).strip()
        if not time_label or not title:
            continue
        if time_label not in grouped:
            grouped[time_label] = []
            seen[time_label] = set()
        if title in seen[time_label]:
            continue
        seen[time_label].add(title)
        grouped[time_label].append(title)
    return grouped


def _sorted_time_labels(labels: Iterable[str]) -> list[str]:
    return sorted(labels, key=_time_sort_key)


def _time_sort_key(label: str) -> time:
    try:
        return datetime.strptime(label.strip(), "%I:%M %p").time()
    except ValueError:
        return time.max
