# tests/conftest.py
import sys
from pathlib import Path
from types import ModuleType

# Ensure project root is importable for all tests (CI runners may omit it).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Lightweight fake-cred stub so imports succeed in CI where secrets file is absent.
if "cred" not in sys.modules:
    fake_cred = ModuleType("cred")
    fake_cred.DISCORD_TOKEN = "test-token"
    fake_cred.DISCORD_LIVE_TRADES_CHANNEL_ID = 0
    fake_cred.DISCORD_TEST_CHANNEL_ID = 0
    fake_cred.DISCORD_STRATEGY_REPORTING_CHANNEL_ID = 0
    fake_cred.DISCORD_CLIENT_SECRET = ""
    fake_cred.DISCORD_APPLICATION_ID = 0
    fake_cred.DISCORD_PUBLIC_KEY = ""
    fake_cred.TRADIER_BROKERAGE_ACCOUNT_ACCESS_TOKEN = ""
    fake_cred.TRADIER_BROKERAGE_BASE_URL = "https://api.tradier.com/v1/"
    fake_cred.TRADIER_BROKERAGE_STREAMING_URL = "https://stream.tradier.com/v1/"
    fake_cred.TRADIER_WEBSOCKET_URL = "wss://ws.tradier.com/v1/"
    fake_cred.TRADIER_BROKERAGE_ACCOUNT_NUMBER = ""
    fake_cred.TRADIER_SANDBOX_ACCOUNT_NUMBER = ""
    fake_cred.TRADIER_SANDBOX_ACCESS_TOKEN = ""
    fake_cred.TRADIER_SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1/"
    fake_cred.RM_TRADIER_ACCESS_TOKEN = ""
    fake_cred.PT_TRADIER_ACCOUNT_NUM = ""
    fake_cred.PT_TRADIER_ACCESS_TOKEN = ""
    fake_cred.TRADING_ECONOMICS_API_KEY = ""
    fake_cred.POLYGON_API_KEY = ""
    fake_cred.POLYGON_AUTHORIZATION = ""
    fake_cred.POLYGON_ACCESS_KEY_ID = ""
    fake_cred.POLYGON_SECRET_ACCESS_KEY = ""
    fake_cred.POLYGON_S3_ENPOINT = "https://files.polygon.io"
    fake_cred.POLYGON_BUCKET = "flatfiles"
    fake_cred.EODHD_API_TOKEN = ""
    sys.modules["cred"] = fake_cred
