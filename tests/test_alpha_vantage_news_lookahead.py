"""Alpha Vantage news must never ask for, or serve, articles past the analysis date.

Lookahead for this vendor is enforced at the request: ``time_from``/``time_to``
bound the window server-side, and the upper bound is the end of the analysis
day, never later. These tests pin that contract, as test_news_lookahead.py
does for yfinance, and pin that the response is passed through verbatim, so a
correct request is a correct bound.
"""

import json

import pytest

import tradingagents.dataflows.net as net
from tradingagents.dataflows.vendors.alpha_vantage import common as av, news as avn


@pytest.fixture
def captured(monkeypatch):
    seen = {}
    monkeypatch.setattr(avn, "_make_api_request", lambda fn, params: seen.update(params) or "{}")
    return seen


@pytest.mark.unit
def test_ticker_news_never_asks_past_the_analysis_date(captured):
    avn.get_news("AAPL", "2026-03-10", "2026-03-14")

    assert captured["time_from"] == "20260310T0000"
    # The end of the analysis day: nothing dated the 15th or later can match.
    assert captured["time_to"] == "20260314T2359"


@pytest.mark.unit
def test_global_news_never_asks_past_the_analysis_date(monkeypatch, captured):
    monkeypatch.setattr(
        avn, "get_config", lambda: {"global_news_lookback_days": 5, "global_news_article_limit": 10}
    )

    avn.get_global_news("2026-03-14")

    assert captured["time_from"] == "20260309T0000"
    assert captured["time_to"] == "20260314T2359"


@pytest.mark.unit
def test_a_historical_window_is_requested_as_one(captured):
    """A run for a past date asks for a window that ends that same day."""
    avn.get_news("NVDA", "2025-05-01", "2025-05-09")

    assert captured["time_to"] == "20250509T2359"


class _Feed:
    """Answers with the article list it was given, however it was asked."""

    def __init__(self, feed):
        self.text = json.dumps({"feed": feed})
        self.status_code = 200

    def raise_for_status(self):
        pass


@pytest.mark.unit
def test_the_response_is_passed_through_verbatim(monkeypatch):
    """The request bound is the only guard against lookahead on this path, so
    the parse step must not re-add, re-date or reorder articles: a response is
    returned to the run exactly as the endpoint answered it."""
    articles = [
        {
            "title": "B",
            "time_published": "20260314T0900",
            "summary": "s",
            "url": "u",
            "overall_sentiment_label": "Neutral",
        },
        {
            "title": "A",
            "time_published": "20260310T0800",
            "summary": "s",
            "url": "u",
            "overall_sentiment_label": "Neutral",
        },
    ]
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: _Feed(articles))
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")

    body = av._make_api_request("NEWS_SENTIMENT", {"tickers": "AAPL"})

    assert [a["title"] for a in json.loads(body)["feed"]] == ["B", "A"]
