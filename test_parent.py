"""
Parent Price Broadcaster (WebSocket Server)
============================================
Simulates price tick generation and broadcasts to all connected children.
Runs continuously until you press Ctrl+C.

Usage:
    python test_parent.py [--port 8765] [--interval 100] [--source HFM]
"""

import asyncio
import json
import time
import random
import argparse
import socket
from datetime import datetime
from typing import Any, Optional, Set, Tuple

try:
    import websockets  # type: ignore
    from websockets.asyncio.server import serve  # type: ignore
except ImportError:
    print("ERROR: 'websockets' library not installed.")
    print("Run:  pip install websockets")
    exit(1)


# =====================================================================
# GLOBALS
# =====================================================================

connected_clients: Set[Any] = set()
seq_counter: int = 0
total_ticks_sent: int = 0
start_time: Optional[float] = None
source_name: str = "UNKNOWN"


def get_local_ip() -> str:
    """Get the local WiFi/LAN IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return str(ip)
    except Exception:
        return "127.0.0.1"


def now_str() -> str:
    """Get current time as HH:MM:SS.mmm string."""
    return datetime.now().strftime("%H:%M:%S.") + "{:03d}".format(
        datetime.now().microsecond // 1000
    )


# =====================================================================
# CLIENT MANAGEMENT
# =====================================================================

async def handle_client(websocket: Any) -> None:
    """Handle a new child connecting."""
    global connected_clients

    client_addr = websocket.remote_address
    client_id = "{}:{}".format(client_addr[0], client_addr[1]) if client_addr else "unknown"
    connected_clients.add(websocket)
    print("[{}] [+] Child connected: {} (Total: {})".format(
        now_str(), client_id, len(connected_clients)
    ))

    try:
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        connected_clients.discard(websocket)
        print("[{}] [-] Child disconnected: {} (Total: {})".format(
            now_str(), client_id, len(connected_clients)
        ))


# =====================================================================
# PRICE SIMULATION
# =====================================================================

def generate_tick(base_price: float) -> Tuple[dict, float]:
    """Generate a simulated price tick with small random fluctuations."""
    global seq_counter
    seq_counter += 1

    movement = random.uniform(-0.00010, 0.00010)
    base_price += movement
    spread = random.uniform(0.00010, 0.00030)

    bid = float("{:.5f}".format(base_price))
    ask = float("{:.5f}".format(base_price + spread))

    ts_now = datetime.now()
    sent_time = ts_now.strftime("%H:%M:%S.") + "{:03d}".format(ts_now.microsecond // 1000)

    tick = {
        "type": "TICK",
        "seq": seq_counter,
        "source": source_name,
        "symbol": "EURUSD",
        "bid": bid,
        "ask": ask,
        "spread_pts": float("{:.1f}".format(spread * 100000)),
        "sent_ts_ms": int(time.time() * 1000),
        "sent_time": sent_time,
    }

    return tick, base_price


# =====================================================================
# BROADCAST LOOP
# =====================================================================

async def broadcast_loop(interval_ms: int) -> None:
    """Continuously generate and broadcast ticks to all children."""
    global total_ticks_sent, start_time, connected_clients

    base_price = 1.08500
    interval_sec = interval_ms / 1000.0
    start_time = time.time()
    last_stats_time = time.time()

    print("[{}] Broadcasting ticks every {}ms from [{}]...".format(
        now_str(), interval_ms, source_name
    ))
    print("[{}] Press Ctrl+C to stop\n".format(now_str()))

    while True:
        if len(connected_clients) > 0:
            tick, base_price = generate_tick(base_price)
            message = json.dumps(tick)

            dead_clients: Set[Any] = set()
            for client in connected_clients.copy():
                try:
                    await client.send(message)
                except Exception:
                    dead_clients.add(client)

            connected_clients -= dead_clients
            total_ticks_sent += 1

            now = time.time()
            if now - last_stats_time >= 1.0:
                elapsed = now - start_time
                rate = total_ticks_sent / elapsed if elapsed > 0 else 0
                print(
                    "[{}] [{}] Seq #{:>6} | Bid: {:.5f} | Ask: {:.5f} | "
                    "Children: {} | Ticks: {} | Rate: {:.1f}/sec".format(
                        tick["sent_time"], source_name,
                        tick["seq"], tick["bid"], tick["ask"],
                        len(connected_clients), total_ticks_sent, rate
                    )
                )
                last_stats_time = now
        else:
            now = time.time()
            if now - last_stats_time >= 3.0:
                print("[{}] [...] Waiting for children to connect...".format(now_str()))
                last_stats_time = now

        await asyncio.sleep(interval_sec)


# =====================================================================
# MAIN
# =====================================================================

async def main(port: int, interval_ms: int) -> None:
    """Start the WebSocket server and broadcast loop."""
    local_ip = get_local_ip()

    print("=" * 65)
    print("   PARENT PRICE BROADCASTER  [Source: {}]".format(source_name))
    print("=" * 65)
    print("[PARENT] Server on 0.0.0.0:{}".format(port))
    print("[PARENT] Tick interval: {}ms".format(interval_ms))
    print("[PARENT] Data source: {}".format(source_name))
    print("")
    print("[PARENT] --- HOW TO CONNECT ---")
    print("[PARENT] Same PC:     python test_child.py localhost {}".format(port))
    print("[PARENT] WiFi/LAN:    python test_child.py {} {}".format(local_ip, port))
    print("[PARENT] Remote/VPS:  python test_child.py <VPS_IP> {}".format(port))
    print("=" * 65)

    async with serve(handle_client, "0.0.0.0", port):
        await broadcast_loop(interval_ms)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parent Price Broadcaster")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--interval", type=int, default=100, help="Tick interval ms (default: 100)")
    parser.add_argument("--source", default="HFM-DEMO", help="Broker/source name (default: HFM-DEMO)")
    args = parser.parse_args()

    source_name = args.source

    try:
        asyncio.run(main(args.port, args.interval))
    except KeyboardInterrupt:
        elapsed = time.time() - start_time if start_time else 0
        print("\n[PARENT] Stopped. Sent {} ticks in {:.1f}s".format(total_ticks_sent, elapsed))
