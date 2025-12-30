# tests\storage_unit_tests\conftest.py
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import types
import duckdb
import pytest
import importlib

@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    paths = importlib.import_module("paths")
    storage_dir = tmp_path / "storage"
    data_dir = storage_dir / "data"
    objects_dir = storage_dir / "objects"

    monkeypatch.setattr(paths, "STORAGE_DIR", storage_dir, raising=False)
    monkeypatch.setattr(paths, "DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr(paths, "OBJECTS_DIR", objects_dir, raising=False)
    monkeypatch.setattr(paths, "CURRENT_OBJECTS_DIR", objects_dir / "current", raising=False)
    monkeypatch.setattr(paths, "TIMELINE_OBJECTS_DIR", objects_dir / "timeline", raising=False)
    monkeypatch.setattr(paths, "CURRENT_OBJECTS_PATH",
                        objects_dir / "current" / "objects.parquet", raising=False)

    data_dir.mkdir(parents=True, exist_ok=True)
    (objects_dir / "current").mkdir(parents=True, exist_ok=True)
    (objects_dir / "timeline").mkdir(parents=True, exist_ok=True)

    # reload so imports pick up patched paths
    importlib.reload(importlib.import_module("storage.objects.io"))
    importlib.reload(importlib.import_module("storage.viewport"))
    importlib.reload(importlib.import_module("tools.candles_io"))
    importlib.reload(importlib.import_module("tools.compact_parquet"))

    yield types.SimpleNamespace(DATA_DIR=data_dir, OBJECTS_DIR=objects_dir)

@pytest.fixture
def duck():
    return duckdb.connect(":memory:")
