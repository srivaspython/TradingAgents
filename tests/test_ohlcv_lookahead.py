"""OHLCV rows dated after the analysis date must never reach a historical run.

load_ohlcv filters the cached/downloaded frame to rows on or before
as_of_date; these tests pin that filter against a poisoned cache and a live
download alike, so a backtest cannot see a future bar whichever way the data
arrived.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import ohlcv


def _frame(dates, close=100.0):
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": 1000,
        }
    )


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    return tmp_path


def _download(monkeypatch_source, frame):
    """Patch yfinance so Ticker().history() returns ``frame`` (Date-indexed)."""
    m = MagicMock()
    m.history.return_value = frame.set_index("Date")
    return m


@pytest.mark.unit
def test_rows_after_the_analysis_date_are_dropped_from_a_download(cache_dir):
    """A download covers through today; a run for last month must end there."""
    downloaded = _frame(["2026-05-28", "2026-05-29", "2026-06-01", "2026-06-02"])
    with (
        patch.object(ohlcv, "yf_retry", lambda fn: fn()),
        patch.object(ohlcv.yf, "Ticker", return_value=_download(None, downloaded)),
    ):
        data = ohlcv.load_ohlcv("NVDA", "2026-05-29", fill_gaps=False)

    assert data["Date"].max() == pd.Timestamp("2026-05-29")
    assert len(data) == 2


@pytest.mark.unit
def test_rows_after_the_analysis_date_are_dropped_from_the_cache(cache_dir):
    """A cache file written by a later live run must not leak its newer rows
    into a backtest that reuses it."""
    data_file = cache_dir / "NVDA-YFin-data.csv"
    _frame(["2026-05-28", "2026-05-29", "2026-06-01", "2026-06-02"]).to_csv(data_file, index=False)
    with patch.object(ohlcv, "_cache_is_fresh", return_value=True):
        data = ohlcv.load_ohlcv("NVDA", "2026-05-29", fill_gaps=False)

    assert data["Date"].max() == pd.Timestamp("2026-05-29")
    assert len(data) == 2


@pytest.mark.unit
def test_the_analysis_day_itself_is_kept(cache_dir):
    """The bound is inclusive: the bar of the analysis date is the one the
    run prices from."""
    downloaded = _frame(["2026-05-29", "2026-06-01"])
    with (
        patch.object(ohlcv, "yf_retry", lambda fn: fn()),
        patch.object(ohlcv.yf, "Ticker", return_value=_download(None, downloaded)),
    ):
        data = ohlcv.load_ohlcv("NVDA", "2026-05-29", fill_gaps=False)

    assert list(data["Date"].dt.strftime("%Y-%m-%d")) == ["2026-05-29"]
