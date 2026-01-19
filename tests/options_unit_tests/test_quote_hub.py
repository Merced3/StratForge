from options.quote_hub import resolve_expiration


def test_resolve_expiration_date_formats():
    assert resolve_expiration("2026-01-06") == "20260106"
    assert resolve_expiration("20260106") == "20260106"


def test_resolve_expiration_invalid():
    try:
        resolve_expiration("bad-format")
    except ValueError as exc:
        assert "Unrecognized expiration format" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid expiration")


def test_resolve_expiration_0dte_returns_date():
    value = resolve_expiration("0dte")
    assert value.isdigit()
    assert len(value) == 8
