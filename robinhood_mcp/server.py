"""
Robinhood MCP server.

Exposes Robinhood trading and market-data capabilities as MCP tools.

Stock tools (read):
  get_quote, get_quotes, get_fundamentals, get_historicals, get_news,
  get_positions, get_holdings, get_portfolio, get_open_orders,
  get_order_history, get_account_info

Stock tools (write):
  buy_market, sell_market, buy_limit, sell_limit, cancel_order

Options tools (read):
  get_option_positions, get_option_orders, find_options,
  get_option_market_data, get_option_historicals

Options tools (write — limit orders only; market orders and spreads are
  unsupported by the underlying Robinhood API wrapper):
  buy_option_limit, sell_option_limit, close_option_limit, cancel_option_order

Session tools:
  login, logout
"""

import sys
from typing import Optional

import robin_stocks.robinhood as rh
from mcp.server.fastmcp import FastMCP

from robinhood_mcp.auth import ensure_logged_in
from robinhood_mcp.auth import logout as _do_logout
from robinhood_mcp.auth import force_relogin


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

mcp = FastMCP("robinhood")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auth(fn):
    """Decorator: ensure we're logged in before calling an rh function."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ensure_logged_in()
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Session tools
# ---------------------------------------------------------------------------

@mcp.tool()
def login() -> str:
    """Authenticate (or re-authenticate) with Robinhood."""
    force_relogin()
    return "Logged in successfully."


@mcp.tool()
def logout() -> str:
    """Log out of Robinhood and clear the cached session."""
    _do_logout()
    return "Logged out."


# ---------------------------------------------------------------------------
# Stock — read tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_quote(symbol: str) -> dict:
    """
    Get a real-time quote for a single stock symbol.

    Returns bid/ask prices, last trade price, volume, and more.
    """
    ensure_logged_in()
    results = rh.get_quotes(symbol.upper())
    if not results:
        return {}
    return results[0]


@mcp.tool()
def get_quotes(symbols: list[str]) -> list[dict]:
    """
    Get real-time quotes for multiple stock symbols in one call.

    Args:
        symbols: List of ticker symbols, e.g. ["AAPL", "TSLA"]
    """
    ensure_logged_in()
    return rh.get_quotes([s.upper() for s in symbols]) or []


@mcp.tool()
def get_fundamentals(symbol: str) -> dict:
    """
    Get fundamental data for a stock: PE ratio, market cap, dividend yield,
    52-week high/low, description, etc.
    """
    ensure_logged_in()
    results = rh.get_fundamentals(symbol.upper())
    if not results:
        return {}
    return results[0]


@mcp.tool()
def get_historicals(
    symbol: str,
    interval: str = "day",
    span: str = "month",
) -> list[dict]:
    """
    Get OHLCV historical price data for a stock.

    Args:
        symbol:   Ticker symbol.
        interval: Candle size — "5minute", "10minute", "hour", "day", "week".
        span:     Time window — "day", "week", "month", "3month", "year", "5year".
    """
    ensure_logged_in()
    return rh.get_stock_historicals(
        symbol.upper(), interval=interval, span=span
    ) or []


@mcp.tool()
def get_news(symbol: str) -> list[dict]:
    """
    Get recent news articles for a stock symbol.
    Each item includes title, source, summary, url, and published_at.
    """
    ensure_logged_in()
    return rh.get_news(symbol.upper()) or []


@mcp.tool()
def get_positions() -> list[dict]:
    """
    Get all current open stock positions.
    Each item includes symbol (via instrument URL), quantity, average buy price, etc.
    """
    ensure_logged_in()
    return rh.get_open_stock_positions() or []


@mcp.tool()
def get_holdings() -> dict:
    """
    Get a detailed summary of all stock holdings including:
    current price, quantity, equity, average buy price, percent change,
    equity change, PE ratio, and portfolio percentage.
    Keys are ticker symbols.
    """
    ensure_logged_in()
    return rh.build_holdings() or {}


@mcp.tool()
def get_portfolio() -> dict:
    """
    Get portfolio profile: total equity, extended-hours equity, market value,
    excess margin, and withdrawable amount.
    """
    ensure_logged_in()
    return rh.load_portfolio_profile() or {}


@mcp.tool()
def get_open_orders() -> list[dict]:
    """
    Get all open (pending) stock orders.
    Each item includes order ID, symbol, type, side, quantity, price, state, etc.
    Use the 'id' field with cancel_order() to cancel an order.
    """
    ensure_logged_in()
    return rh.get_all_open_stock_orders() or []


@mcp.tool()
def get_order_history(start_date: Optional[str] = None) -> list[dict]:
    """
    Get stock order history (filled, cancelled, and open orders).

    Args:
        start_date: Optional ISO date string "YYYY-MM-DD" to filter orders
                    placed on or after this date.
    """
    ensure_logged_in()
    return rh.get_all_stock_orders(start_date=start_date) or []


@mcp.tool()
def get_account_info() -> dict:
    """
    Get Robinhood account profile: account number, buying power, cash,
    portfolio cash, margin details, etc.
    """
    ensure_logged_in()
    return rh.load_account_profile() or {}


# ---------------------------------------------------------------------------
# Stock — write tools
# ---------------------------------------------------------------------------

@mcp.tool()
def buy_market(symbol: str, quantity: float, time_in_force: str = "gtc") -> dict:
    """
    Place a market buy order for a stock.

    Args:
        symbol:        Ticker symbol.
        quantity:      Number of shares; fractional amounts (e.g. 0.5) are supported.
        time_in_force: "gtc" (good-till-cancelled) or "gfd" (good-for-day).

    Returns the order confirmation dict from Robinhood, including 'id' for
    use with cancel_order().
    """
    ensure_logged_in()
    return rh.order_buy_market(symbol.upper(), quantity, timeInForce=time_in_force) or {}


@mcp.tool()
def sell_market(symbol: str, quantity: float, time_in_force: str = "gtc") -> dict:
    """
    Place a market sell order for a stock.

    Args:
        symbol:        Ticker symbol.
        quantity:      Number of shares; fractional amounts (e.g. 0.5) are supported.
        time_in_force: "gtc" (good-till-cancelled) or "gfd" (good-for-day).

    Returns the order confirmation dict from Robinhood, including 'id'.
    """
    ensure_logged_in()
    return rh.order_sell_market(symbol.upper(), quantity, timeInForce=time_in_force) or {}


@mcp.tool()
def buy_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: str = "gtc",
) -> dict:
    """
    Place a limit buy order for a stock.

    Args:
        symbol:        Ticker symbol.
        quantity:      Number of shares; fractional amounts (e.g. 0.5) are supported.
        limit_price:   Maximum price per share to pay.
        time_in_force: "gtc", "gfd", "ioc", or "opg".

    Returns the order confirmation dict from Robinhood, including 'id'.
    """
    ensure_logged_in()
    return rh.order_buy_limit(
        symbol.upper(), quantity, limit_price, timeInForce=time_in_force
    ) or {}


@mcp.tool()
def sell_limit(
    symbol: str,
    quantity: float,
    limit_price: float,
    time_in_force: str = "gtc",
) -> dict:
    """
    Place a limit sell order for a stock.

    Args:
        symbol:        Ticker symbol.
        quantity:      Number of shares; fractional amounts (e.g. 0.5) are supported.
        limit_price:   Minimum price per share to accept.
        time_in_force: "gtc", "gfd", "ioc", or "opg".

    Returns the order confirmation dict from Robinhood, including 'id'.
    """
    ensure_logged_in()
    return rh.order_sell_limit(
        symbol.upper(), quantity, limit_price, timeInForce=time_in_force
    ) or {}


@mcp.tool()
def cancel_order(order_id: str) -> dict:
    """
    Cancel an open stock order.

    Args:
        order_id: The 'id' field from get_open_orders() or any order result.
    """
    ensure_logged_in()
    return rh.cancel_stock_order(order_id) or {}


# ---------------------------------------------------------------------------
# Options — read tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_option_positions() -> list[dict]:
    """
    Get all currently open options positions.
    Each item includes option instrument URL, quantity, average price, etc.
    """
    ensure_logged_in()
    return rh.get_open_option_positions() or []


@mcp.tool()
def get_option_orders() -> list[dict]:
    """
    Get all options orders (open, filled, and cancelled).
    Use the 'id' field with cancel_option_order() to cancel pending orders.
    """
    ensure_logged_in()
    return rh.get_all_option_orders() or []


@mcp.tool()
def find_options(
    symbol: str,
    expiration_date: Optional[str] = None,
    strike: Optional[float] = None,
    option_type: Optional[str] = None,
) -> list[dict]:
    """
    Find tradable options contracts for a symbol.

    Args:
        symbol:          Ticker symbol.
        expiration_date: ISO date string "YYYY-MM-DD" (optional).
        strike:          Strike price filter (optional).
        option_type:     "call" or "put" (optional).

    Returns a list of option contract dicts with strike, expiration, bid/ask, etc.
    """
    ensure_logged_in()
    return rh.find_tradable_options(
        symbol.upper(),
        expirationDate=expiration_date,
        strikePrice=strike,
        optionType=option_type,
    ) or []


@mcp.tool()
def get_option_market_data(
    symbol: str,
    expiration_date: str,
    strike: float,
    option_type: str,
) -> dict:
    """
    Get market data for a specific options contract: greeks (delta, gamma,
    theta, vega), implied volatility, open interest, adjusted mark price, etc.

    Args:
        symbol:          Ticker symbol.
        expiration_date: ISO date "YYYY-MM-DD".
        strike:          Strike price.
        option_type:     "call" or "put".
    """
    ensure_logged_in()
    results = rh.get_option_market_data(
        symbol.upper(), expiration_date, strike, option_type
    )
    if not results:
        return {}
    # Returns a list; grab first item
    return results[0] if isinstance(results, list) else results


@mcp.tool()
def get_option_historicals(
    symbol: str,
    expiration_date: str,
    strike: float,
    option_type: str,
    interval: str = "hour",
    span: str = "week",
) -> list[dict]:
    """
    Get historical price data for a specific options contract.

    Args:
        symbol:          Ticker symbol.
        expiration_date: ISO date "YYYY-MM-DD".
        strike:          Strike price.
        option_type:     "call" or "put".
        interval:        Candle size — "5minute", "10minute", "hour", "day", "week".
        span:            Time window — "day", "week", "year", "5year".
    """
    ensure_logged_in()
    return rh.get_option_historicals(
        symbol.upper(), expiration_date, strike, option_type,
        interval=interval, span=span
    ) or []


# ---------------------------------------------------------------------------
# Options — write tools
# NOTE: Options *market* orders and multi-leg spreads are not supported by the
# Robinhood API wrapper (robin_stocks).  Only single-leg limit orders work.
# ---------------------------------------------------------------------------

@mcp.tool()
def buy_option_limit(
    symbol: str,
    expiration_date: str,
    strike: float,
    option_type: str,
    quantity: int,
    price: float,
    time_in_force: str = "gfd",
) -> dict:
    """
    Open a long options position with a limit order (buy to open).

    Args:
        symbol:          Ticker symbol.
        expiration_date: ISO date "YYYY-MM-DD".
        strike:          Strike price.
        option_type:     "call" or "put".
        quantity:        Number of contracts.
        price:           Limit price per contract (in dollars, e.g. 1.50).
        time_in_force:   "gfd" (good-for-day) or "gtc".

    Note: Options market orders and spreads are not supported.
    """
    ensure_logged_in()
    return rh.order_buy_option_limit(
        price, symbol.upper(), quantity, expiration_date, strike,
        optionType=option_type, timeInForce=time_in_force,
    ) or {}


@mcp.tool()
def sell_option_limit(
    symbol: str,
    expiration_date: str,
    strike: float,
    option_type: str,
    quantity: int,
    price: float,
    time_in_force: str = "gfd",
) -> dict:
    """
    Open a short options position with a limit order (sell to open).

    Args:
        symbol:          Ticker symbol.
        expiration_date: ISO date "YYYY-MM-DD".
        strike:          Strike price.
        option_type:     "call" or "put".
        quantity:        Number of contracts.
        price:           Limit price per contract (in dollars).
        time_in_force:   "gfd" or "gtc".

    Note: Options market orders and spreads are not supported.
    """
    ensure_logged_in()
    return rh.order_sell_option_limit(
        price, symbol.upper(), quantity, expiration_date, strike,
        optionType=option_type, timeInForce=time_in_force,
    ) or {}


@mcp.tool()
def close_option_limit(
    symbol: str,
    expiration_date: str,
    strike: float,
    option_type: str,
    quantity: int,
    price: float,
    time_in_force: str = "gfd",
) -> dict:
    """
    Close an existing long options position with a limit sell order (sell to close).

    Args:
        symbol:          Ticker symbol.
        expiration_date: ISO date "YYYY-MM-DD".
        strike:          Strike price.
        option_type:     "call" or "put".
        quantity:        Number of contracts.
        price:           Minimum limit price to accept per contract.
        time_in_force:   "gfd" or "gtc".
    """
    ensure_logged_in()
    return rh.order_option_sell_to_close(
        price, symbol.upper(), quantity, expiration_date, strike,
        optionType=option_type, timeInForce=time_in_force,
    ) or {}


@mcp.tool()
def cancel_option_order(order_id: str) -> dict:
    """
    Cancel an open options order.

    Args:
        order_id: The 'id' field from get_option_orders().
    """
    ensure_logged_in()
    return rh.cancel_option_order(order_id) or {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
