# Polymarket Trade Analyzer

Fetch and analyze trades from any Polymarket wallet for 15-minute and 1-hour BTC/ETH up-or-down markets.

## Features

- Fetch trades for **any wallet address**
- Support for **15-minute** and **1-hour** market windows
- Parallel API requests (20 workers) for fast data collection
- Automatic P&L calculation per market
- Win rate statistics
- JSON export with detailed trade-by-trade breakdown

## Installation

```bash
pip install requests
```

## Usage

```bash
python analyze_scripy.py <wallet> [options]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `wallet` | Wallet address to analyze (required) | - |
| `--hours`, `-H` | Hours to look back | 6 |
| `--type`, `-t` | Market type: `15m` or `1h` | 15m |
| `--username`, `-u` | Custom folder name for output | wallet address |

### Examples

```bash
# Analyze gabagool22's last 6 hours of 15-min markets
python analyze_scripy.py 0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d -u gabagool22

# Analyze any wallet's 1-hour markets (last 24h)
python analyze_scripy.py 0xABC123... --hours 24 --type 1h

# Quick 3-hour scan without username
python analyze_scripy.py 0xABC123... -H 3
```

## Output

### Console Output

```
============================================================
GABAGOOL22 - 15-MIN MARKETS (Last 6h)
============================================================
Wallet: 0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d
Total trades: 47
Total markets: 12
Time range: 2024-12-24 10:15:00 to 2024-12-24 16:30:00

------------------------------------------------------------
MARKET: btc-updown-15m-1735052100
------------------------------------------------------------
Resolution: YES
Trades: 4
Time: 2024-12-24 14:15:00 - 2024-12-24 14:28:00

Remaining YES: 100.00 sh | Remaining NO: 0.00 sh
Total Spent: $45.00 | Final Value: $100.00
PNL: $55.00

YES: buy 100.00 sh/$45.00 | sell 0.00 sh/$0.00
NO:  buy 0.00 sh/$0.00 | sell 0.00 sh/$0.00
-> Exported: analysis/gabagool22/15m-market/btc-updown-15m-1735052100.json

============================================================
TOTALS (15-MIN markets)
============================================================
Total PNL: $127.50
Win rate: 75.0% (9/12 resolved markets)
```

### Directory Structure

```
analysis/
├── gabagool22/              # Custom username
│   ├── 15m-market/
│   │   ├── btc-updown-15m-1735052100.json
│   │   └── eth-updown-15m-1735052100.json
│   └── 1hr-market/
│       └── bitcoin-up-or-down-december-24-2pm-et.json
└── 0x6031b6eed.../          # Wallet address (no -u flag)
    └── 15m-market/
        └── ...
```

### JSON Export Format

Each market exports a detailed JSON file:

```json
{
  "slug": "btc-updown-15m-1735052100",
  "wallet": "0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d",
  "exported_at": "2024-12-24T16:45:00",
  "summary": {
    "resolution": "YES",
    "total_trades": 4,
    "time_range": {
      "first_trade": "2024-12-24 14:15:00",
      "last_trade": "2024-12-24 14:28:00"
    },
    "final_position": {
      "remaining_yes_shares": 100.0,
      "remaining_no_shares": 0.0
    },
    "costs": {
      "yes_buy_shares": 100.0,
      "yes_buy_cost": 45.0,
      "yes_sell_shares": 0.0,
      "yes_sell_cost": 0.0,
      "no_buy_shares": 0.0,
      "no_buy_cost": 0.0,
      "no_sell_shares": 0.0,
      "no_sell_cost": 0.0
    },
    "pnl": {
      "total_spent": 45.0,
      "final_value": 100.0,
      "pnl": 55.0,
      "pnl_percent": 122.22
    }
  },
  "trades": [
    {
      "trade_number": 1,
      "timestamp": 1735052100,
      "datetime": "2024-12-24 14:15:00",
      "action": "BUY",
      "outcome": "YES",
      "price": 0.45,
      "price_cents": 45.0,
      "shares": 100.0,
      "cost_usd": 45.0,
      "transaction_hash": "0x...",
      "running_yes_shares": 100.0,
      "running_no_shares": 0.0,
      "running_yes_cost": 45.0,
      "running_no_cost": 0.0,
      "running_total_exposure": 45.0
    }
  ]
}
```

## How It Works

1. **Generate Market Slugs** - Creates all possible market identifiers for the time window
   - 15m: `btc-updown-15m-{timestamp}`, `eth-updown-15m-{timestamp}`
   - 1h: `bitcoin-up-or-down-{month}-{day}-{hour}-et`

2. **Fetch Condition IDs** - Queries Gamma API to get market condition IDs from slugs

3. **Fetch Trades** - Parallel requests to Polymarket Data API for wallet trades in each market

4. **Infer Resolution** - Determines market outcome based on final trade prices (>50% = winning side)

5. **Calculate P&L** - Computes net position, total spent, final value, and profit/loss

6. **Export** - Saves detailed trade data to JSON files

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `https://gamma-api.polymarket.com/markets` | Get market condition IDs from slugs |
| `https://data-api.polymarket.com/trades` | Fetch user trades by market |

## Limitations

- Resolution inference assumes price > 0.50 indicates winning side (may be inaccurate for unresolved markets)
- 1-hour market slug format is timezone-specific (ET)
- API rate limits may affect large time windows

## License

MIT
