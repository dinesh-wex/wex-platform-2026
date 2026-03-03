"""End-to-end verification of match scoring against real dev DB data.

Reads actual Property, PropertyKnowledge, PropertyListing, MarketRateCache,
and BuyerNeed records from the SQLite dev database and runs them through
compute_composite_score() to verify the results are sane.

Run:  conda run -n wex python backend/tests/verify_scoring_e2e.py
"""

import sqlite3
import json
import sys
import os

# Add backend src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wex_platform.services.match_scorer import (
    compute_composite_score,
    TIER_MULTIPLIERS,
    W_LOCATION, W_SIZE, W_USE_TYPE, W_FEATURE, W_TIMING, W_VALUE,
    NEUTRAL,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "wex_platform.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # -- Fetch market rates by zip -----------------------------------
    mrc_rows = conn.execute("SELECT zipcode, nnn_low, nnn_high FROM market_rate_cache").fetchall()
    market_rates = {r["zipcode"]: (r["nnn_low"] + r["nnn_high"]) / 2 for r in mrc_rows}

    print("=" * 90)
    print("MARKET RATE CACHE")
    print("=" * 90)
    for r in sorted(mrc_rows, key=lambda x: x["zipcode"]):
        mid = (r["nnn_low"] + r["nnn_high"]) / 2
        print(f"  {r['zipcode']}  NNN ${r['nnn_low']:.2f}–${r['nnn_high']:.2f}  (avg ${mid:.2f})")

    # -- Fetch active buyer needs ------------------------------------
    needs = conn.execute("""
        SELECT id, city, state, lat, lng, radius_miles,
               min_sqft, max_sqft, use_type, needed_from, duration_months,
               max_budget_per_sqft, requirements
        FROM buyer_needs
        WHERE status = 'active'
    """).fetchall()

    # -- Fetch all properties with knowledge + listing ---------------
    props = conn.execute("""
        SELECT
            p.id, p.address, p.city, p.state, p.zip, p.lat, p.lng,
            pk.building_size_sqft, pk.activity_tier, pk.has_office,
            pk.clear_height_ft, pk.dock_doors_receiving,
            pl.min_sqft AS pl_min, pl.max_sqft AS pl_max,
            pl.supplier_rate_per_sqft, pl.available_from,
            pl.available_sqft, pl.activation_status AS listing_status
        FROM properties p
        LEFT JOIN property_knowledge pk ON pk.property_id = p.id
        LEFT JOIN property_listings pl ON pl.property_id = p.id
        WHERE pl.activation_status = 'on'
    """).fetchall()

    print(f"\n{'=' * 90}")
    print(f"ELIGIBLE PROPERTIES ({len(props)} with listing status='on')")
    print("=" * 90)
    for p in props:
        tier = p["activity_tier"] or "unknown"
        rate = p["supplier_rate_per_sqft"] or 0
        mkt = market_rates.get(p["zip"])
        mkt_str = f"${mkt:.2f}" if mkt else "N/A"
        print(f"  {p['city']:20s} {p['state']}  {p['zip'] or '?????'}  "
              f"{p['pl_min']:>6,}–{p['pl_max']:>6,} sqft  "
              f"rate=${rate:.2f}  mkt={mkt_str}  tier={tier}")

    # -- Score each buyer need × property ----------------------------
    for need in needs:
        buyer_target = 0
        if need["min_sqft"] and need["max_sqft"]:
            buyer_target = (need["min_sqft"] + need["max_sqft"]) / 2
        elif need["min_sqft"]:
            buyer_target = need["min_sqft"]

        print(f"\n{'=' * 90}")
        print(f"BUYER NEED: {need['city']}, {need['state']}")
        print(f"  lat/lng: {need['lat']}, {need['lng']}  radius: {need['radius_miles']}mi")
        print(f"  sqft: {need['min_sqft']:,}–{need['max_sqft']:,}  (target: {buyer_target:,.0f})")
        print(f"  use_type: {need['use_type']}  needed_from: {need['needed_from']}")
        print("=" * 90)

        buyer_dict = {
            "city": need["city"],
            "state": need["state"],
            "lat": need["lat"],
            "lng": need["lng"],
            "radius_miles": need["radius_miles"],
            "min_sqft": need["min_sqft"],
            "max_sqft": need["max_sqft"],
            "use_type": need["use_type"],
            "needed_from": need["needed_from"],
            "duration_months": need["duration_months"],
        }

        results = []

        for p in props:
            wh_dict = {
                "id": p["id"],
                "address": p["address"],
                "city": p["city"],
                "state": p["state"],
                "lat": p["lat"],
                "lng": p["lng"],
                "building_size_sqft": p["building_size_sqft"],
            }

            tc_dict = {
                "min_sqft": p["pl_min"],
                "max_sqft": p["pl_max"],
                "activity_tier": p["activity_tier"],
                "has_office_space": bool(p["has_office"]),
                "available_from": p["available_from"],
                "supplier_rate_per_sqft": p["supplier_rate_per_sqft"],
                "generic_market_avg": market_rates.get(p["zip"]),
            }

            scores = compute_composite_score(buyer_dict, wh_dict, tc_dict)
            results.append((p, scores))

        # Sort by composite descending
        results.sort(key=lambda x: x[1]["composite_score"], reverse=True)

        # Print ranked results
        print(f"\n  {'#':>2}  {'City':20s}  {'Dist':>6s}  {'Comp':>5s}  "
              f"{'Loc':>4s}  {'Size':>4s}  {'Use':>4s}  {'Feat':>4s}  {'Time':>4s}  {'Val':>4s}  Notes")
        print(f"  {'-' * 2}  {'-' * 20}  {'-' * 6}  {'-' * 5}  "
              f"{'-' * 4}  {'-' * 4}  {'-' * 4}  {'-' * 4}  {'-' * 4}  {'-' * 4}  {'-' * 30}")

        for rank, (p, s) in enumerate(results, 1):
            dist = s["distance_miles"]
            dist_str = f"{dist:.1f}mi" if dist is not None else "N/A"

            # Build notes
            notes = []
            rate = p["supplier_rate_per_sqft"] or 0
            mkt = market_rates.get(p["zip"])
            if mkt and rate > 0:
                tier_mult = TIER_MULTIPLIERS.get(p["activity_tier"] or "", 1.0)
                adj = mkt * tier_mult
                pct = ((rate - adj) / adj) * 100
                notes.append(f"rate=${rate:.2f} vs adj_mkt=${adj:.2f} ({pct:+.0f}%)")
            elif rate == 0:
                notes.append("no rate")
            else:
                notes.append("no mkt data")

            if s["use_type_callouts"]:
                notes.append(f"callouts: {s['use_type_callouts']}")

            print(f"  {rank:>2}  {p['city']:20s}  {dist_str:>6s}  "
                  f"{s['composite_score']:>5.1f}  "
                  f"{s['location_score']:>4.0f}  {s['size_score']:>4.0f}  "
                  f"{s['use_type_score']:>4.0f}  {s['feature_score']:>4.0f}  "
                  f"{s['timing_score']:>4.0f}  {s['value_score']:>4.0f}  "
                  f"{'  '.join(notes)}")

        # -- Sanity checks -------------------------------------------
        print(f"\n  SANITY CHECKS:")
        for p, s in results:
            issues = []

            # 1. Value score: if rate and market data exist, verify math
            rate = p["supplier_rate_per_sqft"] or 0
            mkt = market_rates.get(p["zip"])
            if rate > 0 and mkt:
                tier_mult = TIER_MULTIPLIERS.get(p["activity_tier"] or "", 1.0)
                adj = mkt * tier_mult
                expected_val = max(0.0, min(100.0, round(70 - ((rate - adj) / adj * 100), 1)))
                if abs(s["value_score"] - expected_val) > 0.1:
                    issues.append(f"VALUE MISMATCH: got {s['value_score']} expected {expected_val}")
            elif rate == 0 and s["value_score"] != 50.0:
                issues.append(f"VALUE: no rate but score={s['value_score']} (expected 50)")
            elif not mkt and rate > 0 and s["value_score"] != 50.0:
                issues.append(f"VALUE: no market data but score={s['value_score']} (expected 50)")

            # 2. Timing: all available_from are null → should be 100
            if p["available_from"] is None and s["timing_score"] != 100.0:
                issues.append(f"TIMING: null available_from but score={s['timing_score']} (expected 100)")

            # 3. Feature: should be NEUTRAL (50) at Layer 1
            if s["feature_score"] != NEUTRAL:
                issues.append(f"FEATURE: expected {NEUTRAL} placeholder, got {s['feature_score']}")

            # 4. Composite math verification
            expected_comp = round(
                s["location_score"] * W_LOCATION
                + s["size_score"] * W_SIZE
                + s["use_type_score"] * W_USE_TYPE
                + s["feature_score"] * W_FEATURE
                + s["timing_score"] * W_TIMING
                + s["value_score"] * W_VALUE, 1
            )
            if abs(s["composite_score"] - expected_comp) > 0.1:
                issues.append(f"COMPOSITE MATH: got {s['composite_score']} expected {expected_comp}")

            # 5. Location: out of state should score low
            if p["state"] != buyer_dict["state"] and s["location_score"] > 50:
                dist = s["distance_miles"]
                if dist and dist > 100:
                    issues.append(f"LOCATION: {dist:.0f}mi away, different state, but score={s['location_score']}")

            if issues:
                print(f"  FAIL {p['city']:20s}: {'; '.join(issues)}")

        if not any(issues for _, s in results):
            print(f"  OK All {len(results)} properties passed sanity checks")

    conn.close()
    print(f"\n{'=' * 90}")
    print("VERIFICATION COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
