"""Closed-loop load test for the HydroSage gateway.

At each concurrency level, that many simulated users each send an
analysis, wait for the answer, and immediately send another, for a fixed
duration. Reports throughput, latency percentiles, how many requests were
refused (503, the gateway's back-pressure) or failed, and how requests were
spread across the API instances (the X-Served-By header).

The requests cycle through a small fixed pool of areas. That's deliberate:
OpenTopography allows 50 elevation downloads a day, so the pool is warmed
once (--warm) and the test then measures the system's own capacity rather
than a third-party download. Each area maps to one instance through the
gateway's affinity routing, so warming costs one download per area.

    python loadtest/loadtest.py --url http://10.1.75.53:3266 --warm --levels 1,2,4,8 --seconds 60

Needs only httpx (pip install httpx).
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from dataclasses import dataclass

import httpx

# Squares of ~1.5 km (0.014 deg) around Bhilai/Durg, spaced so none overlap.
AREA_ORIGINS = [
    (81.270, 21.180), (81.300, 21.150), (81.330, 21.200), (81.240, 21.210),
    (81.360, 21.170), (81.280, 21.240), (81.320, 21.260), (81.250, 21.140),
]
AREA_SIDE_DEG = 0.014


def area(index: int) -> dict:
    lon, lat = AREA_ORIGINS[index % len(AREA_ORIGINS)]
    d = AREA_SIDE_DEG
    return {"polygon": [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d]]}


@dataclass
class Result:
    status: int  # 0 = transport error
    seconds: float
    served_by: str


async def one_request(client: httpx.AsyncClient, url: str, body: dict) -> Result:
    started = time.perf_counter()
    try:
        response = await client.post(f"{url}/analyzeArea", json=body)
        return Result(response.status_code, time.perf_counter() - started, response.headers.get("x-served-by", "-"))
    except httpx.HTTPError:
        return Result(0, time.perf_counter() - started, "-")


async def run_level(url: str, users: int, seconds: float, areas: int, timeout: float) -> list[Result]:
    results: list[Result] = []
    deadline = time.perf_counter() + seconds
    counter = 0

    async def user(client: httpx.AsyncClient) -> None:
        nonlocal counter
        while time.perf_counter() < deadline:
            index = counter
            counter += 1
            result = await one_request(client, url, area(index % areas))
            results.append(result)
            if result.status == 503:
                await asyncio.sleep(1.0)  # honour back-pressure briefly, as a real client would

    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(*(user(client) for _ in range(users)))
    return results


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def summarize(users: int, seconds: float, results: list[Result]) -> dict:
    ok = [r.seconds for r in results if r.status == 200]
    return {
        "users": users,
        "requests": len(results),
        "ok": len(ok),
        "refused_503": sum(r.status == 503 for r in results),
        "errors": sum(r.status not in (200, 503) for r in results),
        "throughput_per_min": round(len(ok) / seconds * 60, 1),
        "p50_s": round(percentile(ok, 50), 2),
        "p95_s": round(percentile(ok, 95), 2),
        "max_s": round(max(ok), 2) if ok else None,
        "mean_s": round(statistics.fmean(ok), 2) if ok else None,
        "served_by": dict(Counter(r.served_by for r in results if r.status == 200)),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="gateway base URL, e.g. http://10.1.75.53:3266")
    parser.add_argument("--levels", default="1,2,4,8", help="comma-separated concurrent-user counts")
    parser.add_argument("--seconds", type=float, default=60, help="duration of each level")
    parser.add_argument("--areas", type=int, default=6, help=f"size of the area pool (max {len(AREA_ORIGINS)})")
    parser.add_argument("--warm", action="store_true", help="analyze each area once before measuring")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--out", help="write the summaries to this JSON file")
    args = parser.parse_args()
    url = args.url.rstrip("/")

    if args.warm:
        async with httpx.AsyncClient(timeout=args.timeout) as client:
            for i in range(args.areas):
                r = await one_request(client, url, area(i))
                print(f"warm area {i}: HTTP {r.status} in {r.seconds:.1f}s via {r.served_by}")

    summaries = []
    for users in (int(x) for x in args.levels.split(",")):
        results = await run_level(url, users, args.seconds, args.areas, args.timeout)
        summary = summarize(users, args.seconds, results)
        summaries.append(summary)
        print(json.dumps(summary))

    print("\n| users | requests | ok | 503 | errors | ok/min | p50 s | p95 s | max s | served by |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in summaries:
        spread = ", ".join(f"{k}: {v}" for k, v in sorted(s["served_by"].items()))
        print(
            f"| {s['users']} | {s['requests']} | {s['ok']} | {s['refused_503']} | {s['errors']} | "
            f"{s['throughput_per_min']} | {s['p50_s']} | {s['p95_s']} | {s['max_s']} | {spread} |"
        )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summaries, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
