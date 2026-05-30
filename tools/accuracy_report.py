"""
Walk-forward accuracy report across all 100 SKUs.
Computes MAPE, bias, RMSE, and 80% interval coverage per SKU and per category.

Usage:
    python tools/accuracy_report.py
    python tools/accuracy_report.py --eval-days 28 --category FOODS
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
from tools.data_access import list_skus
from tools.forecasting import get_accuracy


def run(eval_days: int = 28, category: str = None) -> None:
    skus = list_skus(category)
    total = len(skus)
    print(f"Accuracy report: {total} SKUs, eval_days={eval_days}")
    print("=" * 65)

    results = []
    t_start = time.time()

    for i, sku in enumerate(skus, 1):
        acc = get_accuracy(sku, eval_days=eval_days)
        if "error" in acc:
            print(f"  [{i:3d}/{total}] SKIP  {sku}  ({acc['error']})")
            continue

        results.append(acc)
        bias_flag = "^" if abs(acc["bias"]) > 5 else " "
        mape_flag = "!" if (acc["mape"] or 0) > 25 else " "
        print(
            f"  [{i:3d}/{total}] {sku:<22}  "
            f"MAPE={str(acc['mape'])+'%':>7}  "
            f"bias={acc['bias']:>6.2f}{bias_flag}  "
            f"RMSE={acc['rmse']:>6.2f}  "
            f"cov80={acc['coverage_80pct']:>5.1f}%{mape_flag}"
        )

    if not results:
        print("No results.")
        return

    print("=" * 65)
    _print_summary("ALL SKUs", results)
    print()

    # Per-category breakdown
    for cat in ["FOODS", "HOBBIES", "HOUSEHOLD"]:
        cat_results = [r for r in results if r["sku_id"].startswith(cat)]
        if cat_results:
            _print_summary(cat, cat_results)

    print()
    _print_outliers(results)
    print(f"\nTotal time: {time.time()-t_start:.1f}s")


def _print_summary(label: str, results: list[dict]) -> None:
    mapes   = [r["mape"] for r in results if r["mape"] is not None]
    biases  = [r["bias"] for r in results]
    rmses   = [r["rmse"] for r in results]
    covs    = [r["coverage_80pct"] for r in results]

    print(f"  {label:<22}  "
          f"MAPE={np.mean(mapes):>5.1f}%  "
          f"bias={np.mean(biases):>+6.2f}  "
          f"RMSE={np.mean(rmses):>5.2f}  "
          f"cov80={np.mean(covs):>5.1f}%  "
          f"n={len(results)}")


def _print_outliers(results: list[dict]) -> None:
    print("--- Top 5 worst MAPE ---")
    by_mape = sorted([r for r in results if r["mape"]], key=lambda x: -x["mape"])
    for r in by_mape[:5]:
        print(f"  {r['sku_id']:<22}  MAPE={r['mape']}%  bias={r['bias']:+.2f}")

    print("--- Top 5 most biased (over-forecasting) ---")
    by_bias = sorted(results, key=lambda x: -x["bias"])
    for r in by_bias[:5]:
        print(f"  {r['sku_id']:<22}  bias={r['bias']:+.2f}  ({r['interpretation']})")

    print("--- Top 5 most biased (under-forecasting) ---")
    for r in by_bias[-5:]:
        print(f"  {r['sku_id']:<22}  bias={r['bias']:+.2f}  ({r['interpretation']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-days", type=int, default=28)
    parser.add_argument("--category", type=str, default=None)
    args = parser.parse_args()
    run(eval_days=args.eval_days, category=args.category)
