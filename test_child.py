"""
Child Price Receiver (WebSocket Client)
=========================================
Connects to the parent broadcaster and receives price ticks.
Logs latency, validates data integrity, and prints live stats.
Runs continuously until you press Ctrl+C -- then prints a full summary.

Usage:
    python test_child.py [host] [port] [--name Child1]

Examples:
    python test_child.py                          # Connect to localhost:8765
    python test_child.py 192.168.1.50 8765        # Connect to LAN IP
    python test_child.py localhost 8765 --name PC1 # Named child
"""

import asyncio
import json
import time
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import websockets  # type: ignore
    from websockets.asyncio.client import connect  # type: ignore
except ImportError:
    print("ERROR: 'websockets' library not installed.")
    print("Run:  pip install websockets")
    exit(1)


def now_str() -> str:
    """Get current time as HH:MM:SS.mmm string."""
    dt = datetime.now()
    return dt.strftime("%H:%M:%S.") + "{:03d}".format(dt.microsecond // 1000)


# =====================================================================
# STATS TRACKER
# =====================================================================

class LatencyTracker:
    """Tracks latency statistics and data integrity."""

    def __init__(self) -> None:
        self.latencies: List[float] = []
        self.received_seqs: List[int] = []
        self.first_tick_time: Optional[float] = None
        self.last_tick_time: Optional[float] = None
        self.total_received: int = 0
        self.max_latency: float = 0.0
        self.min_latency: float = float("inf")
        self.sum_latency: float = 0.0
        self.recent_latencies: List[float] = []
        self.source_name: str = "?"

    def record(self, latency_ms: float, seq: int) -> None:
        """Record a received tick."""
        now = time.time()
        if self.first_tick_time is None:
            self.first_tick_time = now
        self.last_tick_time = now

        self.total_received += 1
        self.latencies.append(latency_ms)
        self.received_seqs.append(seq)
        self.recent_latencies.append(latency_ms)

        self.sum_latency += latency_ms
        if latency_ms > self.max_latency:
            self.max_latency = latency_ms
        if latency_ms < self.min_latency:
            self.min_latency = latency_ms

    def get_recent_stats(self) -> Optional[Dict[str, float]]:
        """Get stats for recent ticks and reset."""
        if not self.recent_latencies:
            return None
        avg = sum(self.recent_latencies) / len(self.recent_latencies)
        mx = max(self.recent_latencies)
        mn = min(self.recent_latencies)
        self.recent_latencies = []
        return {"avg": avg, "max": mx, "min": mn}

    def get_missed_sequences(self) -> List[int]:
        """Find any gaps in the sequence numbers."""
        if not self.received_seqs:
            return []
        missed: List[int] = []
        expected = self.received_seqs[0]
        for seq in self.received_seqs:
            while expected < seq:
                missed.append(expected)
                expected += 1
            expected = seq + 1
        return missed

    def print_summary(self) -> None:
        """Print full summary report."""
        if self.total_received == 0:
            print("\n[CHILD] No ticks received.")
            return

        ft = self.first_tick_time if self.first_tick_time is not None else 0.0
        lt = self.last_tick_time if self.last_tick_time is not None else 0.0
        elapsed = lt - ft
        avg_latency = self.sum_latency / self.total_received
        missed = self.get_missed_sequences()

        sorted_lat = sorted(self.latencies)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]

        print("\n" + "=" * 65)
        print("   LATENCY & DATA INTEGRITY REPORT")
        print("=" * 65)
        print("  Data source          : {}".format(self.source_name))
        print("  Total ticks received : {}".format(self.total_received))
        print("  Test duration        : {:.1f} seconds".format(elapsed))
        if elapsed > 0:
            print("  Tick rate            : {:.1f} ticks/sec".format(self.total_received / elapsed))
        print("  -------------------------------------")
        print("  Avg latency          : {:.2f} ms".format(avg_latency))
        print("  Min latency          : {:.2f} ms".format(self.min_latency))
        print("  Max latency          : {:.2f} ms".format(self.max_latency))
        print("  P50 (median)         : {:.2f} ms".format(p50))
        print("  P95                  : {:.2f} ms".format(p95))
        print("  P99                  : {:.2f} ms".format(p99))
        print("  -------------------------------------")
        print("  Missed sequences     : {}".format(len(missed)))
        if missed and len(missed) <= 20:
            print("  Missed seq numbers   : {}".format(missed))
        elif missed:
            print("  Missed seq numbers   : {}... (+{} more)".format(missed[:10], len(missed) - 10))
        integrity = "[+] PERFECT" if not missed else "[-] GAPS DETECTED"
        print("  Data integrity       : {}".format(integrity))

        if avg_latency > 1000:
            print("")
            print("  [!] WARNING: High latency detected ({:.0f}ms).".format(avg_latency))
            print("      This is likely caused by CLOCK DESYNC between")
            print("      the two PCs, not actual network delay.")
            print("      To fix: sync both PCs' clocks via Windows")
            print("      Settings > Time & Language > Sync Now.")
        print("=" * 65)


# =====================================================================
# MAIN CLIENT
# =====================================================================

tracker = LatencyTracker()


async def run_child(host: str, port: int, name: str) -> None:
    """Connect to parent and receive ticks continuously."""
    global tracker
    uri = "ws://{}:{}".format(host, port)
    last_print_time = time.time()
    print_interval = 1.0  # Match parent's 1-second log interval

    print("=" * 65)
    print("   CHILD PRICE RECEIVER [{}]".format(name))
    print("=" * 65)
    print("[{}] Connecting to {}...".format(now_str(), uri))
    print("[{}] Press Ctrl+C to stop and see full report".format(now_str()))
    print("=" * 65)

    try:
        async with connect(uri) as ws:
            print("[{}] [+] Connected to parent!".format(now_str()))
            print("[{}] Waiting for ticks...\n".format(now_str()))

            async for message in ws:
                recv_time = now_str()
                recv_ts_ms = int(time.time() * 1000)

                try:
                    tick = json.loads(message)
                except json.JSONDecodeError:
                    print("[{}] [!] Invalid JSON received".format(recv_time))
                    continue

                if tick.get("type") != "TICK":
                    continue

                # Extract fields
                sent_ts_ms = tick.get("sent_ts_ms", 0)
                latency_ms = recv_ts_ms - sent_ts_ms
                seq = tick.get("seq", 0)
                source = tick.get("source", "?")
                sent_time = tick.get("sent_time", "?")

                # Set source name on tracker (first tick)
                if tracker.source_name == "?":
                    tracker.source_name = source

                tracker.record(float(latency_ms), int(seq))

                # Print live stats at same interval as parent (every 1s)
                now = time.time()
                if now - last_print_time >= print_interval:
                    stats = tracker.get_recent_stats()
                    if stats:
                        print(
                            "[{}] [{}] Seq #{:>6} | Bid: {:.5f} | Ask: {:.5f} | "
                            "Sent: {} | Latency: {:>5.0f}ms | "
                            "Total: {}".format(
                                recv_time, source,
                                seq, tick["bid"], tick["ask"],
                                sent_time, latency_ms,
                                tracker.total_received
                            )
                        )
                    last_print_time = now

    except OSError as e:
        err_str = str(e).lower()
        if "connect call failed" in err_str or "refused" in err_str:
            print("[{}] [-] Connection refused! Is the parent running at {}?".format(now_str(), uri))
        else:
            print("[{}] [-] Connection error: {}".format(now_str(), e))
    except Exception as e:
        print("[{}] [-] Error: {}".format(now_str(), e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Child Price Receiver")
    parser.add_argument("host", nargs="?", default="localhost",
                        help="Parent IP/hostname (default: localhost)")
    parser.add_argument("port", nargs="?", type=int, default=8765,
                        help="Parent port (default: 8765)")
    parser.add_argument("--name", default="CHILD",
                        help="Name for this child (default: CHILD)")
    args = parser.parse_args()

    try:
        asyncio.run(run_child(args.host, args.port, args.name))
    except KeyboardInterrupt:
        pass
    finally:
        tracker.print_summary()
        print("\n[{}] Stopped by user.".format(now_str()))
