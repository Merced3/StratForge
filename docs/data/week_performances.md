# Week Performances — Schema & Usage

**Path:** `storage/week_performances.json` (array of weekly performance objects).

## Schema per entry

- `week_number` (int): sequential week index.
- `week_start_end_date` (str): date range string (e.g., `"04/22/2024-04/26/2024"`).
- `start_ammount` (float): starting balance for the week.
- `end_ammount` (float): ending balance for the week.
- `total_made` (float): P&L for the week.
- `num_of_trades` (int): total trades.
- `num_of_profitable_trades` (int): winning trades.
- `num_of_negitive_trades` (int): losing trades.
- `description` (str): free-form notes about the week.
- `important_message_ids` (list[int]): IDs (e.g., Discord messages) worth bookmarking for that week.

## Usage

- Append a new object at end-of-week with updated balances/trade counts and notes.
- Consumers can read this file to show week-over-week equity and trade stats or to fetch linked messages via `important_message_ids`.
- Keep the array ordered by `week_number` (or chronological), and avoid deleting past entries for history.
