"""Fetch quarterly earnings data for a stock ticker using yfinance."""
from __future__ import annotations

import re
from datetime import datetime


_INDEX_TICKERS = {
    'SPX', 'SOX', 'DJI', 'DJIA', 'RUT', 'IXIC', 'NDX', 'VIX',
    'TWII', 'KOSPI', 'NASDAQ', 'NYSE',
}


def is_index(ticker: str) -> bool:
    return ticker.upper() in _INDEX_TICKERS


def _yf_ticker(ticker: str) -> str:
    if re.match(r'^\d{4,5}$', ticker):
        return ticker + '.TW'
    return ticker


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def _get_row(df, *keys):
    for key in keys:
        if key in df.index:
            return df.loc[key]
    return None


def _fmt_quarter(dt) -> str:
    y = dt.year % 100
    q = (dt.month - 1) // 3 + 1
    return f"{y:02d}Q{q}"


def _yoy_pct(values: list) -> list:
    result = [None] * len(values)
    for i in range(len(values)):
        if i + 4 < len(values):
            curr = values[i]
            prev = values[i + 4]
            if curr is not None and prev is not None and prev != 0:
                result[i] = round((curr - prev) / abs(prev) * 100, 1)
    return result


def fetch_earnings_data(ticker: str) -> dict:
    """
    Fetch up to 8 quarters of financial data.
    Returns a dict ready to be serialised to JSON.
    Raises ValueError if no data is available.
    """
    import yfinance as yf

    yf_sym = _yf_ticker(ticker)
    stock = yf.Ticker(yf_sym)

    info = stock.info or {}
    company_name = info.get('longName') or info.get('shortName') or ticker
    currency = info.get('financialCurrency') or 'USD'

    inc = stock.quarterly_income_stmt
    cf = stock.quarterly_cashflow

    if inc is None or inc.empty:
        raise ValueError(f"No quarterly income statement data for {ticker}")

    # Columns are newest-first; take up to 8
    cols = inc.columns[:8]
    labels = [_fmt_quarter(c) for c in cols]

    def _row_vals(df, *keys):
        row = _get_row(df, *keys)
        return [_safe_float(row[c]) if row is not None and c in df.columns else None for c in cols]

    revenues = _row_vals(inc, 'Total Revenue', 'Revenue', 'TotalRevenue')
    gp = _row_vals(inc, 'Gross Profit', 'GrossProfit')
    oi = _row_vals(inc, 'Operating Income', 'OperatingIncome', 'EBIT')
    ni = _row_vals(inc, 'Net Income', 'NetIncome', 'Net Income Common Stockholders')
    eps = _row_vals(inc, 'Diluted EPS', 'Basic EPS', 'EPS', 'Diluted Eps')

    def _margin(numerator, denom):
        result = []
        for n, d in zip(numerator, denom):
            if n is not None and d is not None and d != 0:
                result.append(round(n / d * 100, 1))
            else:
                result.append(None)
        return result

    gross_margins = _margin(gp, revenues)
    operating_margins = _margin(oi, revenues)
    net_margins = _margin(ni, revenues)

    # FCF: only use quarters present in both income stmt and cash flow
    fcf_vals = []
    if cf is not None and not cf.empty:
        fcf_row = _get_row(cf, 'Free Cash Flow', 'FreeCashFlow')
        for c in cols:
            if fcf_row is not None and c in cf.columns:
                fcf_vals.append(_safe_float(fcf_row[c]))
            else:
                fcf_vals.append(None)
    else:
        fcf_vals = [None] * len(cols)

    def _to_m(vals):
        return [round(v / 1e6, 1) if v is not None else None for v in vals]

    return {
        "ticker": ticker,
        "company_name": company_name,
        "currency": currency,
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
        "analysis": "",
        "charts": {
            "revenue": {
                "labels": labels,
                "values_m": _to_m(revenues),
                "yoy_pct": _yoy_pct(revenues),
            },
            "eps": {
                "labels": labels,
                "values": [round(v, 2) if v is not None else None for v in eps],
                "yoy_pct": _yoy_pct(eps),
            },
            "margins": {
                "labels": labels,
                "gross": gross_margins,
                "operating": operating_margins,
                "net": net_margins,
            },
            "fcf": {
                "labels": labels,
                "values_m": _to_m(fcf_vals),
            },
        },
    }
