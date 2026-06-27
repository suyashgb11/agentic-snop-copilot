"""
Helpers for the root cause agent.
Kept in their own module so the agent file stays short (the Windows mount
silently truncates large single writes).
"""

import re

ALL_STORES = ["CA_1", "TX_1", "WI_1"]
_SNAP_KEY = {"CA_1": "snap_ca", "TX_1": "snap_tx", "WI_1": "snap_wi"}
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def extract_date(query: str):
    """Pull an ISO date out of 'on 2015-02-08' style phrasing."""
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", query)
    return m.group(1) if m else None


def extract_store(query: str):
    q = query.upper()
    for s in ALL_STORES:
        if s in q:
            return s
    return None


def build_candidate_causes(detail, cal_today, cal_window, peer, store):
    """Rank candidate causes by evidence. Returns list of {cause, evidence, confidence}."""
    causes = []
    anomaly_type = detail.get("type", "none") if detail else "none"
    zscore = (detail.get("zscore") if detail else 0) or 0
    direction = "up" if anomaly_type == "spike" else ("down" if anomaly_type == "dip" else None)

    # 1. Stockout (highest confidence when it applies)
    evidence_text = (detail.get("evidence") if detail else "") or ""
    if "stockout" in evidence_text.lower():
        causes.append({
            "cause": "Likely stockout",
            "evidence": evidence_text,
            "confidence": "high",
        })

    # 2. Holiday in the +/- 3 day window
    nearby_holidays = [d for d in (cal_window or []) if d.get("is_holiday")]
    if nearby_holidays:
        closest = min(nearby_holidays, key=lambda d: abs(d["offset_days"]))
        off = closest["offset_days"]
        if off == 0:
            phrase = "falls on the anomaly date"
        elif off > 0:
            phrase = f"falls {abs(off)} day(s) before the anomaly"
        else:
            phrase = f"falls {abs(off)} day(s) after the anomaly"
        if off == 0 and direction == "up":
            conf = "high"
        elif abs(off) <= 1:
            conf = "medium"
        else:
            conf = "low"
        causes.append({
            "cause": "Holiday: " + closest["holiday_name"],
            "evidence": (f"{closest['holiday_name']} {phrase} "
                         f"({closest['date']}, {closest['day_name']})."),
            "confidence": conf,
        })

    # 3. SNAP benefit day for this store's state
    snap_key = _SNAP_KEY.get(store)
    if cal_today and snap_key and cal_today.get(snap_key):
        causes.append({
            "cause": "SNAP benefit day",
            "evidence": f"{store} had SNAP benefits issued on {cal_today.get('date')}.",
            "confidence": "medium" if direction == "up" else "low",
        })

    # 4. Category-wide vs idiosyncratic from peer comparison
    if peer and "error" not in peer:
        sku_chg = peer.get("sku_pct_change", 0) or 0
        peer_chg = peer.get("peer_pct_change", 0) or 0
        same_dir = peer.get("peers_moved_same_direction", False)
        n_peers = peer.get("n_peers", 0)
        if same_dir and abs(peer_chg) >= 15:
            causes.append({
                "cause": "Category-wide demand shift",
                "evidence": (f"SKU moved {sku_chg:+.1f}% while {n_peers} category peers in "
                             f"{store} moved {peer_chg:+.1f}% (same direction). Not isolated."),
                "confidence": "high" if abs(peer_chg) >= 30 else "medium",
            })
        elif abs(sku_chg) >= 15 and abs(peer_chg) < 5:
            causes.append({
                "cause": "Idiosyncratic to this SKU",
                "evidence": (f"SKU moved {sku_chg:+.1f}% but peers moved {peer_chg:+.1f}%. "
                             "Investigate SKU-specific factors: promo, pricing, supplier, "
                             "local stockout."),
                "confidence": "medium",
            })

    # 5. Fallback
    if not causes:
        causes.append({
            "cause": "Unclassified",
            "evidence": (f"Anomaly (type={anomaly_type}, z={zscore}) does not match nearby "
                         "calendar, SNAP, or peer-trend patterns. Manual review recommended."),
            "confidence": "low",
        })

    causes.sort(key=lambda c: _CONFIDENCE_RANK.get(c["confidence"], 3))
    return causes
