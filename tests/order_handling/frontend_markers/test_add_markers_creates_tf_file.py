import asyncio
import json

from data_acquisition import add_markers


def test_add_markers_writes_to_timeframe_file(tmp_path, monkeypatch):
    """
    add_markers should append to the per-timeframe marker file, creating it if missing.
    """
    marker_path = tmp_path / "2M.json"

    # Redirect marker path resolution to the temp directory to avoid touching real storage.
    monkeypatch.setattr(
        "data_acquisition.get_markers_path",
        lambda tf: marker_path,
        raising=True,
    )

    assert not marker_path.exists()

    asyncio.run(add_markers("buy", x=5, y=123.45, live_tf="2M"))

    assert marker_path.exists()
    with open(marker_path, "r") as f:
        markers = json.load(f)

    assert isinstance(markers, list)
    assert len(markers) == 1

    m = markers[0]
    assert m["event_type"] == "buy"
    assert m["x"] == 5
    assert m["y"] == 123.45
    assert m["percentage"] is None
    assert m["style"]["marker"] == "^"
    assert m["style"]["color"] == "blue"
