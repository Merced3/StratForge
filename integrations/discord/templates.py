import re
from datetime import datetime, time, timedelta
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
        format_divider(),
        f"**Ticker Symbol:** {ticker_symbol}",
        f"**Strike Price:** {strike}",
        f"**Option Type:** {option_type}",
        f"**Quantity:** {quantity} contracts",
        f"**Price:** {_format_money(order_price)}",
        f"**Total Investment:** {_format_money(total_investment)}",
    ]
    if reason:
        lines.append(f"**Reason:** {reason}")
    lines.append(format_divider())
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
        f"\n{format_divider()}\n"
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
    trades = _normalize_trade_entries(trades_str_list)
    formatted = [_format_trade_summary_line(trade) for trade in trades]
    formatted = [line for line in formatted if line]
    if not formatted:
        trades_header = "All Trades:"
        trades_str = "No trades today."
    else:
        trades_header = f"All Trades ({len(formatted)}):"
        trades_str = "\n".join(formatted)
    return f"""
{trades_header}
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

    lines = [f"**{header}**", format_divider()]
    for time_label in _sorted_time_labels(grouped.keys()):
        lines.append(f"**{time_label}**")
        for title in grouped[time_label]:
            lines.append(f"- {title}")
        lines.append("")
    return "\n".join(lines).strip()


def format_strategy_report(
    strategy_name: str,
    metrics: dict,
    description: Optional[str] = None,
    last_updated: Optional[str] = None,
    note: Optional[str] = None,
    enabled: Optional[bool] = None,
    config_summary: Optional[str] = None,
    assessment: Optional[str] = None,
) -> str:
    if description is None:
        description = note
    positions = metrics.get("positions")
    closed = metrics.get("closed")
    open_count = metrics.get("open")
    first_trade = metrics.get("first_trade_date")
    last_trade = metrics.get("last_trade_date")
    trade_days = metrics.get("trade_days")
    trades_per_day = metrics.get("trades_per_day")
    call_count = metrics.get("call_count")
    put_count = metrics.get("put_count")
    call_pct = metrics.get("call_pct")
    put_pct = metrics.get("put_pct")
    top_symbol = metrics.get("top_symbol")
    top_symbol_count = metrics.get("top_symbol_count")
    top_symbol_pct = metrics.get("top_symbol_pct")
    sample_flag = metrics.get("sample_flag")
    realized_pnl = metrics.get("pnl_total")
    entry_cost = metrics.get("entry_cost")
    pnl_per_dollar = metrics.get("pnl_per_dollar")
    expectancy = metrics.get("expectancy")
    win_rate = metrics.get("win_rate")
    avg_win = metrics.get("avg_win")
    avg_loss = metrics.get("avg_loss")
    avg_hold = metrics.get("avg_hold")

    ratio_label = _format_ratio(pnl_per_dollar)
    percent_label = _format_percent_optional(pnl_per_dollar)
    return_line = f"{ratio_label} ({percent_label})" if ratio_label != "n/a" else "n/a"

    last_updated = _format_date_label(last_updated)
    divider = format_divider(f"*LU:*`{last_updated}`")
    lines = [
        f"**Strategy Report: {strategy_name}**",
        divider,
    ]
    if enabled is not None:
        enabled_label = "✅" if enabled else "❌"
        lines.append(f"**Enabled:** {enabled_label}")
    if config_summary:
        lines.append(f"**Config:** {config_summary}")
    if assessment:
        lines.append(f"**Assessment:** {assessment}")
    date_range = _format_date_range(first_trade, last_trade)
    if date_range != "n/a":
        lines.append(f"**Trade Window:** {date_range}")
    if trade_days:
        trades_per_day_label = "n/a"
        if trades_per_day is not None:
            trades_per_day_label = f"{trades_per_day:.1f}"
        lines.append(f"**Trade Days:** {trade_days} ({trades_per_day_label} trades/day)")
    if sample_flag:
        lines.append(f"**Sample:** {sample_flag}")
    if call_count is not None and put_count is not None:
        call_pct_label = _format_percent_optional(call_pct)
        put_pct_label = _format_percent_optional(put_pct)
        lines.append(
            f"**Call/Put Split:** {call_pct_label} / {put_pct_label} ({call_count}/{put_count})"
        )
    if top_symbol:
        top_pct_label = _format_percent_optional(top_symbol_pct)
        lines.append(f"**Top Symbol:** {top_symbol} ({top_symbol_count}, {top_pct_label})")
    lines.extend([
        f"**Trades:** {closed} closed / {open_count} open ({positions} total)",
        f"**Realized P/L:** {_format_money(realized_pnl)}",
        f"**Entry Cost:** {_format_money(entry_cost)}",
        f"**Return per $1 premium:** {return_line}",
        f"**Expectancy:** {_format_money(expectancy)} per trade",
        f"**Win Rate:** {_format_percent_optional(win_rate)}",
        f"**Avg Win / Loss:** {_format_money(avg_win)} / {_format_money(avg_loss)}",
        f"**Avg Hold:** {_format_duration(avg_hold)}",
    ])
    if description:
        lines.append(f"**Description:** {description}")
    return "\n".join(lines)


def format_divider(label: Optional[str] = None, padding: int = 12) -> str:
    if label:
        return f"~~{' ' * padding}~~ {label} ~~{' ' * padding}~~"
    return f"~~{' ' * (padding * 2 + 4)}~~"


def _format_date_label(value: Optional[str]) -> str:
    if not value:
        return datetime.now().strftime("%m-%d-%Y")
    if isinstance(value, str):
        parts = value.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            try:
                month = int(parts[1])
                day = int(parts[2])
                return f"{month}-{day}-{parts[0]}"
            except ValueError:
                return value
    return str(value)


def _format_date_range(start: Optional[str], end: Optional[str]) -> str:
    if not start and not end:
        return "n/a"
    start_label = _format_date_label(start) if start else "n/a"
    end_label = _format_date_label(end) if end else "n/a"
    if start_label == end_label and start_label != "n/a":
        return start_label
    return f"{start_label} -> {end_label}"


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


def _format_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _format_percent_optional(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_duration(value: Optional[object]) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        sign = "-" if total_seconds < 0 else ""
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{sign}{hours}h{minutes:02d}m"
        if minutes:
            return f"{sign}{minutes}m{seconds:02d}s"
        return f"{sign}{seconds}s"
    return str(value)

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


def _normalize_trade_entries(trades) -> list[str]:
    if trades is None:
        return []
    if isinstance(trades, (list, tuple)):
        entries = [str(item).strip() for item in trades if str(item).strip()]
        if entries and all(entry in ("[]", "[ ]") for entry in entries):
            return []
        if len(entries) == 1:
            if entries[0] in ("[]", "[ ]"):
                return []
            split = _split_compact_trade_entries(entries[0])
            return split or entries
        return entries
    text = str(trades).strip()
    if text in ("[]", "[ ]"):
        return []
    if not text:
        return []
    split = _split_compact_trade_entries(text)
    return split or [text]


def _split_compact_trade_entries(text: str) -> list[str]:
    raw = text.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    pattern = re.compile(r"\$-?[0-9,]+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?%[+-]?[✅❌]?", re.UNICODE)
    matches = pattern.findall(raw)
    if matches:
        return [match.strip() for match in matches]
    if "$" not in raw:
        return []
    entries = []
    for part in raw.split("$"):
        part = part.strip(" ,")
        if not part:
            continue
        entries.append(f"${part}")
    return entries


def _format_trade_summary_line(line: str) -> str:
    text = str(line).strip()
    if not text:
        return ""
    text = text.strip()
    text = _strip_trailing_indicator(text)
    emoji = _infer_trade_emoji(text)
    text = _strip_leading_emoji(text)
    return f"{emoji} {text}".strip()


def _strip_trailing_indicator(text: str) -> str:
    cleaned = re.sub(r"[✅❌]\s*$", "", text).strip()
    cleaned = re.sub(r"(%)([+-])\s*$", r"\1", cleaned).strip()
    return cleaned


def _strip_leading_emoji(text: str) -> str:
    if text.startswith(("✅", "❌", "⚪")):
        return text[1:].lstrip()
    return text


def _infer_trade_emoji(text: str) -> str:
    if "✅" in text:
        return "✅"
    if "❌" in text:
        return "❌"
    money_match = re.search(r"\$(-?[0-9,]+(?:\.\d+)?)", text)
    if money_match:
        value = float(money_match.group(1).replace(",", ""))
        if value > 0:
            return "✅"
        if value < 0:
            return "❌"
        return "⚪"
    percent_match = re.search(r"(-?\d+(?:\.\d+)?)%", text)
    if percent_match:
        value = float(percent_match.group(1))
        if value > 0:
            return "✅"
        if value < 0:
            return "❌"
    return "⚪"
