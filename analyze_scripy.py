#!/usr/bin/env python3
"""
Polymarket Trade Analyzer - 15min & 1hr Markets
Fetches trades from Polymarket API for any wallet,
supports both 15-minute and 1-hour markets.

Usage:
    python analyze_scripy.py <wallet> [options]

Options:
    --hours, -H    Hours to look back (default: 6)
    --type, -t     Market type: 15m or 1h (default: 15m)
    --username, -u Optional username for output folder

Examples:
    python analyze_scripy.py 0x6031b... -u gabagool22
    python analyze_scripy.py 0x6031b... --hours 24 --type 1h -u gabagool22
    python analyze_scripy.py 0xABC123... --hours 12 --type 15m
"""

import argparse
import time
import datetime
import requests
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
TRADES_URL = "https://data-api.polymarket.com/trades"
GAMMA_URL = "https://gamma-api.polymarket.com/markets"
PRICE_RESOLUTION_THRESHOLD = 0.5
DEFAULT_HOURS = 6
MAX_WORKERS = 20


def generate_15m_slugs(hours=6):
    """Generate all 15-minute market slugs for the last N hours."""
    slugs = []
    now = int(time.time())
    window_start = now - (now % 900)
    windows = hours * 4

    for i in range(windows):
        ts = window_start - (i * 900)
        slugs.append(f"btc-updown-15m-{ts}")
        slugs.append(f"eth-updown-15m-{ts}")

    return slugs


def generate_1h_slugs(hours=24):
    """Generate all 1-hour market slugs for the last N hours."""
    slugs = []
    now = datetime.datetime.now()

    # Round down to current hour
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    for i in range(hours):
        dt = current_hour - datetime.timedelta(hours=i)

        # Format: bitcoin-up-or-down-december-23-8am-et
        month = dt.strftime("%B").lower()
        day = dt.day
        hour = dt.hour

        # Convert to 12-hour format
        if hour == 0:
            hour_str = "12am"
        elif hour < 12:
            hour_str = f"{hour}am"
        elif hour == 12:
            hour_str = "12pm"
        else:
            hour_str = f"{hour - 12}pm"

        btc_slug = f"bitcoin-up-or-down-{month}-{day}-{hour_str}-et"
        eth_slug = f"ethereum-up-or-down-{month}-{day}-{hour_str}-et"

        slugs.append(btc_slug)
        slugs.append(eth_slug)

    return slugs


def get_condition_id(slug):
    """Get conditionId for a market slug from Gamma API."""
    try:
        resp = requests.get(GAMMA_URL, params={"slug": slug}, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        if markets and len(markets) > 0:
            return markets[0].get("conditionId")
    except:
        pass
    return None


def fetch_trades_for_market(user_address, condition_id, slug):
    """Fetch all trades for a user in a specific market using conditionId."""
    if not condition_id:
        return slug, []

    all_trades = []
    offset = 0

    while True:
        params = {
            "user": user_address,
            "market": condition_id,
            "limit": 500,
            "offset": offset,
        }
        try:
            resp = requests.get(TRADES_URL, params=params, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
        except:
            break

        if not batch:
            break

        all_trades.extend(batch)

        if len(batch) < 500:
            break
        offset += 500

    return slug, all_trades


def fetch_market_data(user_address, slug):
    """Fetch conditionId and trades for a single market."""
    condition_id = get_condition_id(slug)
    if not condition_id:
        return slug, None, []

    _, trades = fetch_trades_for_market(user_address, condition_id, slug)
    return slug, condition_id, trades


def fetch_all_trades(user_address, hours=6, market_type="15m"):
    """Fetch trades for all markets in parallel."""
    if market_type == "15m":
        slugs = generate_15m_slugs(hours)
        market_label = "15-min"
    else:
        slugs = generate_1h_slugs(hours)
        market_label = "1-hour"

    all_trades = []
    markets_with_trades = 0

    print(f"Fetching trades for {user_address}...")
    print(f"Scanning {len(slugs)} {market_label} markets ({hours}h window)...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_market_data, user_address, slug): slug
            for slug in slugs
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            slug, condition_id, trades = future.result()

            if trades:
                for t in trades:
                    t['_slug'] = slug
                all_trades.extend(trades)
                markets_with_trades += 1

            if completed % 20 == 0 or completed == len(slugs):
                print(f"  Progress: {completed}/{len(slugs)} markets, "
                      f"{markets_with_trades} with trades, {len(all_trades)} total trades")

    return all_trades


def infer_resolution(trades):
    """Infer resolved side from the most recent trade price."""
    if not trades:
        return None
    latest = max(trades, key=lambda t: t.get("timestamp", 0))
    price = float(latest.get("price", 0))
    outcome = latest.get("outcome", "").lower()

    if outcome not in {"up", "down"}:
        return None

    if price >= PRICE_RESOLUTION_THRESHOLD:
        return "YES" if outcome == "up" else "NO"
    else:
        return "NO" if outcome == "up" else "YES"


def calculate_market_stats(trades, resolved_side):
    """Calculate statistics for a single market's trades."""
    trades = sorted(trades, key=lambda t: t.get("timestamp", 0))

    yes_buy_sh = yes_buy_cost = 0
    yes_sell_sh = yes_sell_cost = 0
    no_buy_sh = no_buy_cost = 0
    no_sell_sh = no_sell_cost = 0
    yes_exposure = no_exposure = 0

    for t in trades:
        side = t.get("side", "BUY").upper()
        outcome = t.get("outcome", "up").lower()
        price = float(t.get("price", 0))
        size = float(t.get("size", 0))
        cost = price * size

        is_buy = side == "BUY"
        is_yes = outcome == "up"

        if is_buy:
            if is_yes:
                yes_buy_sh += size
                yes_buy_cost += cost
                yes_exposure += size
            else:
                no_buy_sh += size
                no_buy_cost += cost
                no_exposure += size
        else:
            if is_yes:
                yes_sell_sh += size
                yes_sell_cost += cost
                yes_exposure -= size
            else:
                no_sell_sh += size
                no_sell_cost += cost
                no_exposure -= size

    total_spent = (yes_buy_cost - yes_sell_cost) + (no_buy_cost - no_sell_cost)

    if resolved_side == "YES":
        final_value = yes_exposure * 1.0
    elif resolved_side == "NO":
        final_value = no_exposure * 1.0
    else:
        final_value = 0

    pnl = final_value - total_spent

    return {
        "trade_count": len(trades),
        "yes_buy_sh": yes_buy_sh,
        "yes_buy_cost": yes_buy_cost,
        "yes_sell_sh": yes_sell_sh,
        "yes_sell_cost": yes_sell_cost,
        "no_buy_sh": no_buy_sh,
        "no_buy_cost": no_buy_cost,
        "no_sell_sh": no_sell_sh,
        "no_sell_cost": no_sell_cost,
        "remaining_yes": yes_exposure,
        "remaining_no": no_exposure,
        "total_spent": total_spent,
        "final_value": final_value,
        "pnl": pnl,
        "resolved_side": resolved_side,
        "first_trade": trades[0]["timestamp"] if trades else None,
        "last_trade": trades[-1]["timestamp"] if trades else None,
    }


def format_timestamp(ts):
    if ts is None:
        return "N/A"
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def export_market_json(slug, trades, stats, resolved_side, output_dir, wallet):
    """Export detailed trade-by-trade data for a market to JSON."""
    os.makedirs(output_dir, exist_ok=True)

    sorted_trades = sorted(trades, key=lambda t: t.get("timestamp", 0))

    detailed_trades = []
    running_yes_shares = 0
    running_no_shares = 0
    running_yes_cost = 0
    running_no_cost = 0

    for i, t in enumerate(sorted_trades):
        ts = t.get("timestamp", 0)
        side = t.get("side", "BUY").upper()
        outcome = t.get("outcome", "").lower()
        price = float(t.get("price", 0))
        size = float(t.get("size", 0))
        cost = price * size

        is_buy = side == "BUY"
        is_yes = outcome == "up"

        if is_buy:
            if is_yes:
                running_yes_shares += size
                running_yes_cost += cost
            else:
                running_no_shares += size
                running_no_cost += cost
        else:
            if is_yes:
                running_yes_shares -= size
                running_yes_cost -= cost
            else:
                running_no_shares -= size
                running_no_cost -= cost

        trade_detail = {
            "trade_number": i + 1,
            "timestamp": ts,
            "datetime": format_timestamp(ts),
            "action": side,
            "outcome": "YES" if is_yes else "NO",
            "price": round(price, 4),
            "price_cents": round(price * 100, 2),
            "shares": round(size, 2),
            "cost_usd": round(cost, 4),
            "transaction_hash": t.get("transactionHash", ""),
            "running_yes_shares": round(running_yes_shares, 2),
            "running_no_shares": round(running_no_shares, 2),
            "running_yes_cost": round(running_yes_cost, 4),
            "running_no_cost": round(running_no_cost, 4),
            "running_total_exposure": round(running_yes_cost + running_no_cost, 4),
            "raw": {
                "proxyWallet": t.get("proxyWallet"),
                "asset": t.get("asset"),
                "conditionId": t.get("conditionId"),
                "outcomeIndex": t.get("outcomeIndex"),
            }
        }
        detailed_trades.append(trade_detail)

    market_data = {
        "slug": slug,
        "wallet": wallet,
        "exported_at": datetime.datetime.now().isoformat(),
        "summary": {
            "resolution": resolved_side if resolved_side else "PENDING",
            "total_trades": stats["trade_count"],
            "time_range": {
                "first_trade": format_timestamp(stats["first_trade"]),
                "last_trade": format_timestamp(stats["last_trade"]),
                "first_trade_ts": stats["first_trade"],
                "last_trade_ts": stats["last_trade"],
            },
            "final_position": {
                "remaining_yes_shares": round(stats["remaining_yes"], 2),
                "remaining_no_shares": round(stats["remaining_no"], 2),
            },
            "costs": {
                "yes_buy_shares": round(stats["yes_buy_sh"], 2),
                "yes_buy_cost": round(stats["yes_buy_cost"], 4),
                "yes_sell_shares": round(stats["yes_sell_sh"], 2),
                "yes_sell_cost": round(stats["yes_sell_cost"], 4),
                "no_buy_shares": round(stats["no_buy_sh"], 2),
                "no_buy_cost": round(stats["no_buy_cost"], 4),
                "no_sell_shares": round(stats["no_sell_sh"], 2),
                "no_sell_cost": round(stats["no_sell_cost"], 4),
            },
            "pnl": {
                "total_spent": round(stats["total_spent"], 4),
                "final_value": round(stats["final_value"], 4),
                "pnl": round(stats["pnl"], 4),
                "pnl_percent": round((stats["pnl"] / stats["total_spent"] * 100), 2) if stats["total_spent"] > 0 else 0,
            }
        },
        "trades": detailed_trades
    }

    # Clean slug for filename (replace special chars)
    safe_slug = slug.replace("/", "-")
    filename = f"{safe_slug}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w") as f:
        json.dump(market_data, f, indent=2)

    return filepath


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze Polymarket trades for any wallet (15min & 1hr markets)"
    )
    parser.add_argument("wallet", help="Wallet address to analyze")
    parser.add_argument(
        "--hours", "-H", type=int, default=DEFAULT_HOURS,
        help=f"Hours to look back (default: {DEFAULT_HOURS})"
    )
    parser.add_argument(
        "--type", "-t", choices=["15m", "1h"], default="15m",
        help="Market type: 15m or 1h (default: 15m)"
    )
    parser.add_argument(
        "--username", "-u",
        help="Optional username for output folder (default: wallet address)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    wallet = args.wallet
    hours = args.hours
    market_type = args.type

    # Use username if provided, otherwise use wallet address
    folder_name = args.username if args.username else wallet
    display_name = args.username.upper() if args.username else f"WALLET {wallet[:10]}..."

    # Set output directory based on market type
    base_output_dir = f"analysis/{folder_name}"
    if market_type == "15m":
        output_dir = os.path.join(base_output_dir, "15m-market")
        market_label = "15-MIN"
    else:
        output_dir = os.path.join(base_output_dir, "1hr-market")
        market_label = "1-HOUR"

    # Fetch trades
    all_trades = fetch_all_trades(wallet, hours, market_type)

    if not all_trades:
        print(f"No trades found in {market_label} markets for the last {hours} hours.")
        return

    # Group by slug
    markets = defaultdict(list)
    for trade in all_trades:
        slug = trade.get("_slug", trade.get("slug", "unknown"))
        markets[slug].append(trade)

    # Calculate time range
    all_timestamps = [t.get("timestamp", 0) for t in all_trades]
    min_ts = min(all_timestamps)
    max_ts = max(all_timestamps)

    # Print header
    print()
    print("=" * 60)
    print(f"{display_name} - {market_label} MARKETS (Last {hours}h)")
    print("=" * 60)
    print(f"Wallet: {wallet}")
    print(f"Total trades: {len(all_trades)}")
    print(f"Total markets: {len(markets)}")
    print(f"Time range: {format_timestamp(min_ts)} to {format_timestamp(max_ts)}")
    print()

    # Process each market
    total_pnl = 0
    resolved_count = 0
    win_count = 0
    exported_files = []

    sorted_markets = sorted(markets.items(), key=lambda x: x[0])

    for slug, trades in sorted_markets:
        resolved_side = infer_resolution(trades)
        stats = calculate_market_stats(trades, resolved_side)

        # Export to JSON
        filepath = export_market_json(slug, trades, stats, resolved_side, output_dir, wallet)
        exported_files.append(filepath)

        print("-" * 60)
        print(f"MARKET: {slug}")
        print("-" * 60)

        resolution_str = resolved_side if resolved_side else "PENDING"
        print(f"Resolution: {resolution_str}")
        print(f"Trades: {stats['trade_count']}")
        print(f"Time: {format_timestamp(stats['first_trade'])} - {format_timestamp(stats['last_trade'])}")
        print()
        print(f"Remaining YES: {stats['remaining_yes']:.2f} sh | Remaining NO: {stats['remaining_no']:.2f} sh")
        print(f"Total Spent: ${stats['total_spent']:.2f} | Final Value: ${stats['final_value']:.2f}")
        print(f"PNL: ${stats['pnl']:.2f}")
        print()
        print(f"YES: buy {stats['yes_buy_sh']:.2f} sh/${stats['yes_buy_cost']:.2f} | sell {stats['yes_sell_sh']:.2f} sh/${stats['yes_sell_cost']:.2f}")
        print(f"NO:  buy {stats['no_buy_sh']:.2f} sh/${stats['no_buy_cost']:.2f} | sell {stats['no_sell_sh']:.2f} sh/${stats['no_sell_cost']:.2f}")
        print(f"-> Exported: {filepath}")
        print()

        if resolved_side:
            total_pnl += stats['pnl']
            resolved_count += 1
            if stats['pnl'] > 0:
                win_count += 1

    # Print totals
    print("=" * 60)
    print(f"TOTALS ({market_label} markets)")
    print("=" * 60)
    print(f"Total PNL: ${total_pnl:.2f}")
    if resolved_count > 0:
        win_rate = (win_count / resolved_count) * 100
        print(f"Win rate: {win_rate:.1f}% ({win_count}/{resolved_count} resolved markets)")
    else:
        print("Win rate: N/A (no resolved markets)")
    print()
    print(f"JSON files exported to: {output_dir}/")
    print(f"Total files: {len(exported_files)}")
    print()


if __name__ == "__main__":
    main()
