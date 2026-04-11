# robinhood-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes Robinhood trading and market-data capabilities as tools for Claude and other MCP-compatible AI clients.

## Features

**Stocks — read**
- `get_quote` / `get_quotes` — real-time bid/ask, last price, volume
- `get_fundamentals` — PE ratio, market cap, dividend yield, 52-week range
- `get_historicals` — OHLCV candles (5min → weekly, day → 5yr)
- `get_news` — recent news articles with title, source, summary, URL
- `get_positions` — open stock positions
- `get_holdings` — full holdings summary with P&L and portfolio %
- `get_portfolio` — total equity, buying power, margin info
- `get_open_orders` — pending orders
- `get_order_history` — filled, cancelled, and open orders (filterable by date)
- `get_account_info` — account number, cash, margin details

**Stocks — write**
- `buy_market` / `sell_market` — market orders (fractional shares supported)
- `buy_limit` / `sell_limit` — limit orders
- `cancel_order` — cancel any open stock order by ID

**Options — read**
- `get_option_positions` — open options positions
- `get_option_orders` — all options orders
- `find_options` — search tradable contracts by symbol, expiry, strike, type
- `get_option_market_data` — greeks, IV, open interest, mark price
- `get_option_historicals` — historical candles for a specific contract

**Options — write** (limit orders only; market orders and spreads are unsupported by the underlying API)
- `buy_option_limit` — buy to open
- `sell_option_limit` — sell to open
- `close_option_limit` — sell to close
- `cancel_option_order` — cancel an open options order

**Session**
- `login` — authenticate (or re-authenticate) with Robinhood
- `logout` — log out and clear the cached session

## Requirements

- Python 3.11+
- A Robinhood account
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
git clone https://github.com/jimgitsit/robinhood-mcp.git
cd robinhood-mcp
uv sync
```

## Configuration

Create a `.env` file in the project root:

```
ROBINHOOD_USERNAME=your@email.com
ROBINHOOD_PASSWORD=yourpassword
ROBINHOOD_TOTP_SECRET=YOURBASE32SECRET   # optional — enables automatic TOTP 2FA
```

**Without `ROBINHOOD_TOTP_SECRET`:** the server will wait up to 2 minutes for you to approve a mobile push notification each time a fresh login is required.

**With `ROBINHOOD_TOTP_SECRET`:** login is fully automatic. To get your TOTP secret, enable two-factor authentication in the Robinhood app and save the base32 seed shown during setup.

Sessions are cached at `~/.tokens/robinhood.pickle` so re-authentication is only needed when the token expires.

## Usage

### With Claude Desktop

Add the server to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "robinhood": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/robinhood-mcp",
        "run", "robinhood-mcp"
      ]
    }
  }
}
```

### With Claude Code (CLI)

```bash
claude mcp add robinhood -- uv --directory /path/to/robinhood-mcp run robinhood-mcp
```

### Standalone

```bash
uv run robinhood-mcp
```

## Disclaimer

This project is not affiliated with or endorsed by Robinhood Markets, Inc. Use at your own risk. Automated trading carries significant financial risk — always review orders before execution.
