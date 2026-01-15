# Discord Integration

This folder contains the Discord integration for StratForge. The goal is to keep all Discord-specific logic here so the rest of the codebase can stay decoupled.

## Files

- `client.py` - thin wrappers for send/edit/file + bot setup
- `templates.py` - message formatting and parsing helpers

## Usage

```python
from integrations.discord.client import bot, print_discord, send_file_discord

await print_discord("Hello from StratForge")
await send_file_discord("storage/images/spy_chart.png")
```

## Templates

Message formatting helpers live in `templates.py`. If you want to change how a
message looks, update the template there instead of editing call sites.
