"""MP17: p95 response times of the heavy read screens on the running stack (20 calls each, DEMO login).

Usage: python deploy/perf.py http://backend:8000   (inside the compose network) or http://localhost:8180
"""

import statistics
import sys
import time

import httpx

PATHS = (
    "/api/inbox",
    "/api/stock/ledger",
    "/api/reports/sales-register",
    "/api/reports/stock-summary",
    "/api/reports/gst-summary",
    "/api/planning/brief",
    "/api/trace/freshness",
    "/api/transport/cost-to-serve",
)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://backend:8000"
    with httpx.Client(base_url=base, timeout=60) as c:
        r = c.post("/api/auth/login", json={"email": "owner@aaharos-demo.invalid", "password": "change-me-demo"})
        r.raise_for_status()
        print(f"{'path':40} {'p50 ms':>8} {'p95 ms':>8}")
        for path in PATHS:
            times = []
            for _ in range(20):
                t = time.perf_counter()
                c.get(path).raise_for_status()
                times.append((time.perf_counter() - t) * 1000)
            times.sort()
            print(f"{path:40} {statistics.median(times):8.0f} {times[int(0.95 * len(times)) - 1]:8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
