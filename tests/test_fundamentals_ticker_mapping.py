"""Regression coverage for Yahoo Finance symbol resolution in fundamentals
enrichment.

Context: several entities recorded with correct company-level tickers
(9984=SoftBank, 7012=Kawasaki Heavy Industries, 6506=Yaskawa Electric,
0700=Tencent, 0981=SMIC, 2222=Saudi Aramco, P911=Porsche AG, TPEX=Taipei
Exchange index, BRENT=Brent crude) were all getting mis-resolved: bare
4-digit numeric tickers default to Taiwan (.TW/.TWO) even when the company
trades in Tokyo, Hong Kong, Riyadh or Frankfurt; alphabetic non-tickers
like TPEX/BRENT fell through untouched. Every one of these produced a 404
against Yahoo Finance on every build.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import build_site
from backend.earnings_fetcher import is_index


def test_yf_symbols_resolves_known_non_taiwan_numeric_tickers():
    assert build_site._yf_symbols("9984") == ["9984.T"]     # SoftBank Group (Tokyo)
    assert build_site._yf_symbols("7012") == ["7012.T"]     # Kawasaki Heavy Industries (Tokyo)
    assert build_site._yf_symbols("6506") == ["6506.T"]     # Yaskawa Electric (Tokyo)
    assert build_site._yf_symbols("0700") == ["0700.HK"]    # Tencent (Hong Kong)
    assert build_site._yf_symbols("0981") == ["0981.HK"]    # SMIC (Hong Kong)
    assert build_site._yf_symbols("2222") == ["2222.SR"]    # Saudi Aramco (Tadawul)
    assert build_site._yf_symbols("P911") == ["P911.DE"]    # Porsche AG (Frankfurt)


def test_yf_symbols_still_defaults_unmapped_4_digit_tickers_to_taiwan():
    assert build_site._yf_symbols("2330") == ["2330.TW", "2330.TWO"]  # TSMC


def test_tpex_is_recognized_as_an_index():
    assert is_index("TPEX") is True


def test_enrich_fundamentals_skips_commodity_and_index_tickers(monkeypatch):
    calls = []

    class FakeTicker:
        def __init__(self, symbol):
            calls.append(symbol)
        @property
        def info(self):
            return {}

    monkeypatch.setitem(sys.modules, "yfinance", type("_m", (), {"Ticker": FakeTicker})())

    entities = [
        {"ticker": "BRENT", "name": "布蘭特原油"},
        {"ticker": "TPEX", "name": "櫃買指數"},
    ]
    build_site._enrich_us_fundamentals(entities)

    assert calls == [], f"BRENT/TPEX must never reach Yahoo Finance, but queried: {calls}"
    assert "fundamentals" not in entities[0]
    assert "fundamentals" not in entities[1]
