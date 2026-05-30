"""
Generate M5-like Walmart data and load it into DuckDB.
Run directly: python data/load_m5.py
Idempotent — skips if the database already looks complete.

Scale:
  100 SKUs x 3 stores x 1,941 days = 582,300 sales rows
  25+ anomaly events spread across 5 years
"""

import os
import time
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("DUCKDB_PATH", "data/snop.duckdb"))

SKUS = (
    [f"FOODS_1_{i:03d}" for i in range(1, 36)] +      # 35 food SKUs
    [f"HOBBIES_1_{i:03d}" for i in range(1, 36)] +    # 35 hobby SKUs
    [f"HOUSEHOLD_1_{i:03d}" for i in range(1, 31)]    # 30 household SKUs
)  # 100 SKUs

STORES = ["CA_1", "TX_1", "WI_1"]   # 3 states, different SNAP schedules

START_DATE = "2011-01-29"
END_DATE   = "2016-05-22"

# ─────────────────────────────────────────────
# Calendar
# ─────────────────────────────────────────────

_FIXED_HOLIDAYS = {
    (1, 1):  "NewYear",
    (2, 14): "ValentinesDay",
    (3, 17): "StPatricksDay",
    (7, 4):  "IndependenceDay",
    (10, 31):"Halloween",
    (11, 11):"VeteransDay",
    (12, 25):"Christmas",
    (12, 31):"NewYearsEve",
}


def _holiday_name(d: pd.Timestamp) -> str:
    key = (d.month, d.day)
    if key in _FIXED_HOLIDAYS:
        return _FIXED_HOLIDAYS[key]
    dow = d.weekday()
    if d.month == 11 and dow == 3 and 22 <= d.day <= 28:
        return "Thanksgiving"
    if d.month == 9  and dow == 0 and d.day <= 7:
        return "LaborDay"
    if d.month == 5  and dow == 0 and d.day >= 25:
        return "MemorialDay"
    if d.month == 5  and dow == 6 and 8  <= d.day <= 14:
        return "MothersDay"
    if d.month == 6  and dow == 6 and 15 <= d.day <= 21:
        return "FathersDay"
    if d.month == 2  and dow == 6 and d.day <= 7:
        return "SuperBowl"
    if d.month == 11 and dow == 4 and d.day <= 7:
        return "ElectionDay"
    if d.month == 11 and dow == 5 and 23 <= d.day <= 30:
        return "BlackFriday"
    return ""


def _snap(d: pd.Timestamp, state: str) -> bool:
    """Each state has a different SNAP distribution schedule."""
    if state == "CA":
        return d.day <= 10
    if state == "TX":
        return d.day <= 10 or 16 <= d.day <= 20
    if state == "WI":
        return d.day <= 15
    return False


def _make_calendar(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    rows = []
    for d in dates:
        hname = _holiday_name(d)
        rows.append({
            "date":        d.date(),
            "day_of_week": int(d.weekday()),
            "is_weekend":  bool(d.weekday() >= 5),
            "is_holiday":  bool(hname),
            "holiday_name":hname,
            "snap_ca":     bool(_snap(d, "CA")),
            "snap_tx":     bool(_snap(d, "TX")),
            "snap_wi":     bool(_snap(d, "WI")),
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# Sales generation
# ─────────────────────────────────────────────

_DOW_FOODS     = [0.85, 0.90, 0.90, 0.95, 1.10, 1.35, 1.20]
_DOW_HOBBIES   = [0.80, 0.85, 0.85, 0.90, 1.05, 1.40, 1.30]
_DOW_HOUSEHOLD = [0.95, 1.00, 0.95, 1.00, 1.05, 1.10, 0.90]

_HOLIDAY_BOOST = {
    "Christmas":      {"FOODS": 1.70, "HOBBIES": 1.50, "HOUSEHOLD": 1.40},
    "Thanksgiving":   {"FOODS": 1.60, "HOBBIES": 1.20, "HOUSEHOLD": 1.30},
    "BlackFriday":    {"FOODS": 1.20, "HOBBIES": 2.10, "HOUSEHOLD": 1.80},
    "SuperBowl":      {"FOODS": 1.50, "HOBBIES": 1.25, "HOUSEHOLD": 1.10},
    "IndependenceDay":{"FOODS": 1.40, "HOBBIES": 1.30, "HOUSEHOLD": 1.10},
    "MemorialDay":    {"FOODS": 1.25, "HOBBIES": 1.20, "HOUSEHOLD": 1.10},
    "LaborDay":       {"FOODS": 1.25, "HOBBIES": 1.15, "HOUSEHOLD": 1.10},
    "NewYear":        {"FOODS": 1.30, "HOBBIES": 1.10, "HOUSEHOLD": 1.05},
    "NewYearsEve":    {"FOODS": 1.35, "HOBBIES": 1.15, "HOUSEHOLD": 1.05},
    "ValentinesDay":  {"FOODS": 1.20, "HOBBIES": 1.40, "HOUSEHOLD": 1.10},
    "Halloween":      {"FOODS": 1.45, "HOBBIES": 1.60, "HOUSEHOLD": 1.20},
    "MothersDay":     {"FOODS": 1.20, "HOBBIES": 1.50, "HOUSEHOLD": 1.30},
}

# Store-level base demand multipliers (TX slightly higher volume, WI slightly lower)
_STORE_FACTOR = {"CA_1": 1.00, "TX_1": 1.12, "WI_1": 0.88}

# SNAP flag per store
_SNAP_FLAG = {"CA_1": "snap_ca", "TX_1": "snap_tx", "WI_1": "snap_wi"}


def _make_sales(
    skus: list,
    stores: list,
    dates: pd.DatetimeIndex,
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    cal = calendar.set_index("date").to_dict("index")

    rows = []
    for sku in skus:
        cat     = sku.split("_")[0]
        sku_num = int(sku.split("_")[-1])
        # Each SKU gets a unique base demand
        base = float(rng.integers(10, 65)) + (sku_num % 7) * 2.5

        for store in stores:
            store_f  = _STORE_FACTOR[store]
            snap_col = _SNAP_FLAG[store]

            for d in dates:
                dk = d.date()
                c  = cal.get(dk, {})

                # Day-of-week factor
                dow = d.weekday()
                if   cat == "FOODS":     dow_f = _DOW_FOODS[dow]
                elif cat == "HOBBIES":   dow_f = _DOW_HOBBIES[dow]
                else:                    dow_f = _DOW_HOUSEHOLD[dow]

                # Annual seasonal wave
                seasonal = 1.0 + 0.15 * np.sin(
                    2 * np.pi * d.dayofyear / 365 - np.pi / 4
                )

                # Holiday boost
                hname  = c.get("holiday_name", "")
                hboost = _HOLIDAY_BOOST.get(hname, {}).get(cat, 1.15 if hname else 1.0)

                # SNAP boost for FOODS only
                snap_f = 1.30 if (cat == "FOODS" and c.get(snap_col)) else 1.0

                lam   = base * store_f * dow_f * seasonal * hboost * snap_f
                units = int(rng.poisson(max(lam, 0.5)))
                rows.append({"sku_id": sku, "store_id": store, "date": dk, "units": units})

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# Anomaly injection — 25+ events across 5 years
# ─────────────────────────────────────────────

def _inject_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Inject a diverse set of realistic anomalies spread across the full
    5-year history.  Each anomaly has a different type, severity, and
    cause — some explainable (tied to a real event), some mysterious.

    Types injected:
      - Demand spikes      (sudden single-day or multi-day surge)
      - Stockouts          (sustained zero demand)
      - Demand dips        (gradual or sudden drop, non-zero)
      - Upward drift       (new long-term trend)
      - Downward drift     (eroding demand)
      - Regional event     (affects one store only)
      - Category-wide      (affects all SKUs in a category on the same day)
    """
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])

    def spike(sku, store, date, multiplier):
        mask = (out["sku_id"] == sku) & (out["store_id"] == store) & (out["date"] == pd.Timestamp(date))
        out.loc[mask, "units"] = (out.loc[mask, "units"] * multiplier).clip(lower=1).astype(int)

    def multi_spike(sku, store, start, end, multiplier):
        mask = (out["sku_id"] == sku) & (out["store_id"] == store) & \
               (out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))
        out.loc[mask, "units"] = (out.loc[mask, "units"] * multiplier).clip(lower=1).astype(int)

    def stockout(sku, store, start, end):
        mask = (out["sku_id"] == sku) & (out["store_id"] == store) & \
               (out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))
        out.loc[mask, "units"] = 0

    def drift(sku, store, start, end, end_multiplier):
        """Linearly ramp demand from 1x to end_multiplier over the period."""
        mask = (out["sku_id"] == sku) & (out["store_id"] == store) & \
               (out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))
        dates_in = sorted(out.loc[mask, "date"].unique())
        n = len(dates_in)
        for i, d in enumerate(dates_in):
            m = 1.0 + (end_multiplier - 1.0) * (i / max(n - 1, 1))
            day_mask = mask & (out["date"] == d)
            out.loc[day_mask, "units"] = (out.loc[day_mask, "units"] * m).clip(lower=0).astype(int)

    def category_spike(cat, store, date, multiplier):
        """All SKUs in a category spike on the same day — systemic event."""
        mask = (out["sku_id"].str.startswith(cat)) & \
               (out["store_id"] == store) & \
               (out["date"] == pd.Timestamp(date))
        out.loc[mask, "units"] = (out.loc[mask, "units"] * multiplier).clip(lower=1).astype(int)

    # ── 2011 ──────────────────────────────────────────────────────────
    # Mystery spike: FOODS SKU right after Super Bowl (not the day of — that's explained)
    spike("FOODS_1_005",     "CA_1", "2011-02-08", 6.5)   # day-after Super Bowl, unexplained
    # Stockout: supply chain issue hits one HOUSEHOLD SKU in TX for 2 weeks
    stockout("HOUSEHOLD_1_003", "TX_1", "2011-04-10", "2011-04-24")
    # Upward drift: new product gaining traction (HOBBIES)
    drift("HOBBIES_1_012",  "CA_1", "2011-06-01", "2011-12-31", 1.9)

    # ── 2012 ──────────────────────────────────────────────────────────
    # Demand spike: viral social media moment lifts a HOBBIES SKU for 3 days
    multi_spike("HOBBIES_1_022", "CA_1", "2012-03-15", "2012-03-17", 8.0)
    # Regional weather event: TX store sees HOUSEHOLD spike (storm prep)
    category_spike("HOUSEHOLD", "TX_1", "2012-06-22", 4.2)
    # Stockout: FOODS SKU goes to zero at WI store for 10 days
    stockout("FOODS_1_019",  "WI_1", "2012-08-05", "2012-08-15")
    # Downward drift: product losing shelf space (FOODS)
    drift("FOODS_1_030",    "CA_1", "2012-09-01", "2013-03-31", 0.35)
    # Demand dip: HOBBIES SKU drops 70% for a week (competitor went on sale)
    multi_spike("HOBBIES_1_008", "TX_1", "2012-11-05", "2012-11-12", 0.30)

    # ── 2013 ──────────────────────────────────────────────────────────
    # Spike: FOODS SKU in CA around back-to-school restocking
    multi_spike("FOODS_1_011",  "CA_1", "2013-08-20", "2013-08-25", 5.5)
    # Stockout: 3-week fulfilment failure at WI
    stockout("HOUSEHOLD_1_017","WI_1", "2013-05-10", "2013-05-31")
    # Stockout: TX store, FOODS SKU, 12 days
    stockout("FOODS_1_024",    "TX_1", "2013-10-14", "2013-10-26")
    # Upward drift: seasonal product picks up permanently (HOBBIES outdoor)
    drift("HOBBIES_1_031",  "TX_1", "2013-03-01", "2013-09-01", 2.2)
    # Mystery spike: no calendar explanation
    spike("HOUSEHOLD_1_022", "CA_1", "2013-07-17", 7.0)

    # ── 2014 ──────────────────────────────────────────────────────────
    # Category-wide FOODS spike in WI — SNAP policy change boosts payout window
    category_spike("FOODS",   "WI_1", "2014-01-03", 2.8)
    # Demand dip: HOUSEHOLD SKU in CA drops 60% for 2 weeks (planogram change)
    multi_spike("HOUSEHOLD_1_010", "CA_1", "2014-03-01", "2014-03-14", 0.40)
    # Stockout: HOBBIES SKU TX for 8 days
    stockout("HOBBIES_1_027", "TX_1", "2014-06-20", "2014-06-28")
    # Downward drift: product being phased out
    drift("FOODS_1_007",    "WI_1", "2014-07-01", "2015-01-01", 0.25)
    # Multi-day spike: store grand reopening (all categories, one store)
    multi_spike("FOODS_1_002",     "TX_1", "2014-09-10", "2014-09-14", 3.5)
    multi_spike("HOBBIES_1_005",   "TX_1", "2014-09-10", "2014-09-14", 3.5)
    multi_spike("HOUSEHOLD_1_006", "TX_1", "2014-09-10", "2014-09-14", 3.5)

    # ── 2015 ──────────────────────────────────────────────────────────
    # Long stockout: 3 weeks FOODS at CA
    stockout("FOODS_1_016",   "CA_1", "2015-02-15", "2015-03-08")
    # Upward drift: health food trend lifts FOODS SKU permanently
    drift("FOODS_1_028",    "CA_1", "2015-01-01", "2016-05-22", 1.75)
    # Mystery spike: HOBBIES SKU, no explanation
    spike("HOBBIES_1_034",  "WI_1", "2015-04-22", 9.0)
    # Demand dip followed by recovery (delivery partner issue)
    multi_spike("HOUSEHOLD_1_025","CA_1", "2015-07-01", "2015-07-10", 0.20)
    multi_spike("HOUSEHOLD_1_025","CA_1", "2015-07-11", "2015-07-20", 1.60)  # rebound
    # Stockout: WI store, HOUSEHOLD, 14 days
    stockout("HOUSEHOLD_1_008","WI_1", "2015-09-05", "2015-09-19")

    # ── 2016 (up to May 22) ───────────────────────────────────────────
    # Spike near end of data — anomaly agent's primary working window
    spike("FOODS_1_003",    "CA_1", "2016-05-04", 7.0)
    spike("HOBBIES_1_007",  "TX_1", "2016-04-30", 6.5)
    spike("HOUSEHOLD_1_015","WI_1", "2016-05-13", 5.5)
    # Stockout at end of data (active alert)
    stockout("FOODS_1_012", "CA_1", "2016-05-02", "2016-05-07")
    stockout("HOUSEHOLD_1_008","CA_1","2016-05-07", "2016-05-22")
    # Slow drift upward (active, ongoing)
    drift("FOODS_1_020",   "CA_1", "2016-03-01", "2016-05-22", 1.80)

    out["date"] = out["date"].dt.date
    return out


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def load(force: bool = False) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    if not force:
        try:
            tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
            if "sales" in tables and "calendar" in tables:
                n = con.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
                if n > 100_000:
                    print(f"Database already loaded ({n:,} rows). Pass force=True to reload.")
                    con.close()
                    return
        except Exception:
            pass

    t0 = time.time()
    print(f"Building M5-like dataset: {len(SKUS)} SKUs x {len(STORES)} stores")

    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    print(f"  Date range : {START_DATE} to {END_DATE} ({len(dates):,} days)")
    print(f"  Total rows : {len(SKUS) * len(STORES) * len(dates):,} before anomaly injection")

    calendar_df = _make_calendar(START_DATE, END_DATE)
    sales_df    = _make_sales(SKUS, STORES, dates, calendar_df)
    sales_df    = _inject_anomalies(sales_df)

    print(f"  Anomalies injected across 5 years")

    con.execute("DROP TABLE IF EXISTS forecasts")
    con.execute("DROP TABLE IF EXISTS sales")
    con.execute("DROP TABLE IF EXISTS calendar")

    con.execute("""
        CREATE TABLE calendar (
            date DATE PRIMARY KEY,
            day_of_week  INTEGER,
            is_weekend   BOOLEAN,
            is_holiday   BOOLEAN,
            holiday_name TEXT,
            snap_ca      BOOLEAN,
            snap_tx      BOOLEAN,
            snap_wi      BOOLEAN
        )
    """)
    con.execute("INSERT INTO calendar SELECT * FROM calendar_df")

    con.execute("""
        CREATE TABLE sales (
            sku_id   TEXT    NOT NULL,
            store_id TEXT    NOT NULL,
            date     DATE    NOT NULL,
            units    INTEGER NOT NULL
        )
    """)
    con.execute("INSERT INTO sales SELECT * FROM sales_df")
    con.execute("CREATE INDEX idx_sales ON sales(sku_id, store_id, date)")

    con.execute("""
        CREATE TABLE forecasts (
            sku_id       TEXT,
            store_id     TEXT,
            date_made    DATE,
            horizon_date DATE,
            model        TEXT,
            point        DOUBLE,
            lo80         DOUBLE,
            hi80         DOUBLE,
            lo95         DOUBLE,
            hi95         DOUBLE
        )
    """)

    n = con.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    con.close()
    print(f"  Done in {time.time()-t0:.1f}s -- {n:,} rows written to {DB_PATH}")


if __name__ == "__main__":
    load(force=True)
