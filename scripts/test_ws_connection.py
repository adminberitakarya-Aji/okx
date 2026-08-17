"""Manual WebSocket connectivity test for all exchanges.

Connects to each exchange's PUBLIC WebSocket endpoint (no API keys needed),
subscribes to a ticker channel, waits for a message, and reports success.

Usage:
    uv run python scripts/test_ws_connection.py
    uv run python scripts/test_ws_connection.py --exchange okx
    uv run python scripts/test_ws_connection.py --exchange binance
    uv run python scripts/test_ws_connection.py --exchange bybit
    uv run python scripts/test_ws_connection.py --timeout 15

NOTE: This script requires real network access. It is NOT run by pytest.
"""

import argparse
import asyncio
import json
import sys
import time

import websockets

# ---------------------------------------------------------------------------
# Exchange WS configurations (public endpoints only — no auth required)
# ---------------------------------------------------------------------------

EXCHANGES: dict[str, dict] = {
    "okx": {
        "url": "wss://ws.okx.com:8443/ws/v5/public",
        "subscribe": {
            "op": "subscribe",
            "args": [{"channel": "tickers", "instId": "BTC-USDT"}],
        },
        "description": "OKX Public WS (tickers BTC-USDT)",
    },
    "binance": {
        "url": "wss://stream.binance.com:9443/ws/btcusdt@ticker",
        "subscribe": None,  # Binance combined streams: channel is in the URL
        "description": "Binance Public WS (btcusdt@ticker)",
    },
    "bybit": {
        "url": "wss://stream.bybit.com/v5/public/spot",
        "subscribe": {
            "op": "subscribe",
            "args": ["tickers.BTCUSDT"],
        },
        "description": "Bybit Public WS (tickers.BTCUSDT)",
    },
}


async def test_ws_connection(name: str, config: dict, timeout: int) -> bool:
    """Test WebSocket connection for a single exchange."""
    url = config["url"]
    subscribe_msg = config["subscribe"]
    description = config["description"]

    print(f"\n{'=' * 60}")
    print(f"  {description}")
    print(f"  URL: {url}")
    print(f"{'=' * 60}")

    start = time.monotonic()
    try:
        async with websockets.connect(url, open_timeout=timeout) as ws:
            connect_time = time.monotonic() - start
            print(f"  [OK] Connected in {connect_time:.2f}s")

            # Subscribe if needed
            if subscribe_msg is not None:
                await ws.send(json.dumps(subscribe_msg))
                print("  [OK] Subscription sent")

            # Wait for first message
            print(f"  [..] Waiting for first message (timeout={timeout}s)...")
            msg_start = time.monotonic()
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg_time = time.monotonic() - msg_start

            # Parse and display
            try:
                data = json.loads(raw)
                preview = json.dumps(data, indent=2)[:300]
            except (json.JSONDecodeError, TypeError):
                preview = str(raw)[:300]

            print(f"  [OK] First message received in {msg_time:.2f}s")
            print(f"  Preview: {preview}")

            total = time.monotonic() - start
            print(f"  [PASS] {name.upper()} — total {total:.2f}s")
            return True

    except TimeoutError:
        elapsed = time.monotonic() - start
        print(f"  [FAIL] {name.upper()} — timeout after {elapsed:.2f}s")
        return False
    except OSError as e:
        elapsed = time.monotonic() - start
        print(f"  [FAIL] {name.upper()} — network error after {elapsed:.2f}s: {e}")
        return False
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"  [FAIL] {name.upper()} — {type(e).__name__} after {elapsed:.2f}s: {e}")
        return False


async def main() -> None:
    """Run WS connectivity tests."""
    parser = argparse.ArgumentParser(description="Test WebSocket connectivity to exchanges")
    parser.add_argument(
        "--exchange",
        choices=list(EXCHANGES.keys()),
        default=None,
        help="Test only a specific exchange (default: all)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Connection/message timeout in seconds (default: 10)",
    )
    args = parser.parse_args()

    exchanges_to_test = {args.exchange: EXCHANGES[args.exchange]} if args.exchange else EXCHANGES

    print("\n" + "=" * 60)
    print("  WebSocket Connectivity Test")
    print("  (Public endpoints — no API keys required)")
    print("=" * 60)

    results: dict[str, bool] = {}
    for name, config in exchanges_to_test.items():
        results[name] = await test_ws_connection(name, config, args.timeout)

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name.upper():>10}: {status}")

    all_passed = all(results.values())
    print(f"\n  Overall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print("=" * 60 + "\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
