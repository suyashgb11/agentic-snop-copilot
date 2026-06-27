"""
Batch forecast runner — all SKUs, all stores.
Fits AutoARIMA for every SKU/store combination and writes to the forecasts table.
Run once after load_m5.py, then re-run weekly.

Usage:
    python tools/run_baselines.py
    python tools/run_baselines.py --horizon 28 --category FOODS --store CA_1
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from tools.data_access import list_skus, get_con
from tools.forecasting import run_forecast

HORIZON  = 28
STORES   = ["CA_1", "TX_1", "WI_1"]


def run(horizon: int = HORIZON, category: str = None, store: str = None) -> None:
    skus   = list_skus(category)
    stores = [store] if store else STORES
    total  = len(skus) * len(stores)

    print(f"Running forecasts: {len(skus)} SKUs x {len(stores)} stores = {total} combinations")
    print(f"Horizon: {horizon} days")
    print("-" * 60)

    ok = 0
    failed = 0
    t_start = time.time()
    n = 0

    for store_id in stores:
        print(f"\n  Store: {store_id}")
        for i, sku in enumerate(skus, 1):
            n += 1
            t0     = time.time()
            result = run_forecast(sku, horizon_days=horizon, store_id=store_id)
            elapsed = time.time() - t0

            if "error" in result:
                print(f"    [{n:4d}/{total}] SKIP  {sku}  ({result['error']})")
                failed += 1
            else:
                fc = result["forecast"]
                print(f"    [{n:4d}/{total}] OK    {sku:<22}  "
                      f"next={fc[0]['point']:5.1f}  {elapsed:.1f}s")
                ok += 1

    total_time = time.time() - t_start
    print("\n" + "-" * 60)
    print(f"Done: {ok} OK, {failed} skipped, {total_time:.1f}s total ({total_time/60:.1f} min)")

    con = get_con()
    n_rows = con.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    stores_done = con.execute("SELECT COUNT(DISTINCT store_id) FROM forecasts").fetchone()[0]
    print(f"Forecasts table: {n_rows:,} rows across {stores_done} stores")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon",  type=int, default=HORIZON)
    parser.add_argument("--category", type=str, default=None,
                        help="FOODS, HOBBIES, or HOUSEHOLD")
    parser.add_argument("--store",    type=str, default=None,
                        help="CA_1, TX_1, or WI_1 (default: all three)")
    args = parser.parse_args()
    run(horizon=args.horizon, category=args.category, store=args.store)
