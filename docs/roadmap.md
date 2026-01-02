# Roadmap

---

## Now

### Documentation Alignment

- **Goal**: Make most recent changes align with documentation folder `docs/`.
- **Status**: Pending
- **Description**: Refer to `todo.txt` for more detials.

---

## Next

### Multi-Buy-In

- **Goal**: Multi-buy into the same order.
- **Status**: Not Started
- **Description**: Implement multi-entry order handling; add sim/tests to validate behavior.

---

## Later

### Refactor Discord Message IDs

- **Goal**: Store and access Discord Message IDs dynamically from a JSON file instead of global variables.
- **Status**: Not Started
- **Description**: Read IDs from JSON on demand to reduce globals/memory and improve modularity.

### Change End Of Day Calculations

- **Goal**: Base EOD calculations entirely on `message_ids.json`.
- **Status**: Not Started
- **Description**: Replace short-term variables with reads from `message_ids.json`; revisit `todays_profit_loss` / `get_profit_loss_orders_list()` flow to remove the mutable variable.

---

## Notes

- Tasks marked **Blocked** require external resolution (e.g., new provider, API access).
- Tasks are arranged by priority: Pending tasks are at the top, completed tasks are at the bottom.
- Update this file regularly as tasks progress or new ones are added.
