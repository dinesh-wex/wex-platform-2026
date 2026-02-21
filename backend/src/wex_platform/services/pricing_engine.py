"""Pricing Engine - Calculates buyer rates and WEx spread.

ECONOMIC ISOLATION: This service contains the core spread logic.
Buyer-facing endpoints must NEVER expose supplier_rate, spread, or spread_pct.
Only the buyer_rate is safe to return to buyers.
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_default_buyer_rate(supplier_rate: float) -> float:
    """WEx default pricing: supplier × 1.20 (margin) × 1.06 (guarantee fee), round UP to cent.

    This is the standard "Global Rate" applied when no custom pricing is set.
    Can be overridden per-warehouse by admin.
    """
    if not supplier_rate or supplier_rate <= 0:
        return 0.0
    return math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100


class PricingEngine:
    """Calculates buyer-facing rates based on supplier rates and features."""

    # Base spread by market
    MARKET_SPREADS = {
        "SC": 0.18,  # 18%
        "CA": 0.22,  # Higher spread in competitive CA market
        "GA": 0.18,
        "MI": 0.20,
        "AZ": 0.20,
        "MD": 0.19,
        "TX": 0.18,
    }

    # Feature adjustments (added to buyer rate)
    FEATURE_ADJUSTMENTS = {
        "has_office_space": 0.05,
        "has_sprinkler": 0.02,
        "has_24_7_access": 0.03,
        "has_security": 0.02,
        "clear_height_30_plus": 0.03,
        "dock_doors_10_plus": 0.02,
        "certifications": 0.05,
    }

    def calculate_buyer_rate(
        self,
        supplier_rate: float,
        state: str,
        warehouse_features: Optional[dict] = None,
    ) -> dict:
        """Calculate the buyer rate and WEx spread.

        Args:
            supplier_rate: What WEx pays the supplier (per sqft/month)
            state: Warehouse state (for market-specific spread)
            warehouse_features: Dict of feature flags for price adjustments

        Returns:
            Dict with buyer_rate, spread, spread_pct, feature_adjustments
        """
        features = warehouse_features or {}
        base_spread_pct = self.MARKET_SPREADS.get(state, 0.20)

        # Calculate feature adjustments
        adjustments = []
        total_adjustment = 0.0

        if features.get("has_office_space"):
            adjustments.append({"feature": "Office Space", "adjustment": 0.05})
            total_adjustment += 0.05

        if features.get("has_sprinkler"):
            adjustments.append({"feature": "Sprinkler System", "adjustment": 0.02})
            total_adjustment += 0.02

        if features.get("clear_height_ft") and features["clear_height_ft"] >= 30:
            adjustments.append({"feature": "30+ ft Clear Height", "adjustment": 0.03})
            total_adjustment += 0.03

        if features.get("dock_doors_receiving") and features["dock_doors_receiving"] >= 10:
            adjustments.append({"feature": "10+ Dock Doors", "adjustment": 0.02})
            total_adjustment += 0.02

        if features.get("parking_spaces") and features["parking_spaces"] >= 100:
            adjustments.append({"feature": "100+ Parking Spaces", "adjustment": 0.01})
            total_adjustment += 0.01

        # Base buyer rate = supplier rate + spread
        base_buyer_rate = supplier_rate * (1 + base_spread_pct)

        # Add feature adjustments
        buyer_rate = base_buyer_rate + total_adjustment

        spread = buyer_rate - supplier_rate
        spread_pct = (spread / buyer_rate * 100) if buyer_rate > 0 else 0

        return {
            "buyer_rate": round(buyer_rate, 2),
            "supplier_rate": round(supplier_rate, 2),
            "spread": round(spread, 2),
            "spread_pct": round(spread_pct, 1),
            "base_spread_pct": round(base_spread_pct * 100, 1),
            "feature_adjustments": adjustments,
            "total_feature_adjustment": round(total_adjustment, 2),
        }

    def calculate_deal_economics(
        self,
        supplier_rate: float,
        buyer_rate: float,
        sqft: int,
        term_months: int,
    ) -> dict:
        """Calculate full deal economics.

        Args:
            supplier_rate: Per-sqft monthly rate paid to supplier.
            buyer_rate: Per-sqft monthly rate charged to buyer.
            sqft: Square footage allocated for the deal.
            term_months: Duration of the lease in months.

        Returns:
            Dict with monthly/total payments, WEx revenue, and deposit info.
        """
        monthly_supplier = supplier_rate * sqft
        monthly_buyer = buyer_rate * sqft
        monthly_spread = monthly_buyer - monthly_supplier

        return {
            "monthly_supplier_payment": round(monthly_supplier, 2),
            "monthly_buyer_payment": round(monthly_buyer, 2),
            "monthly_wex_revenue": round(monthly_spread, 2),
            "total_contract_value": round(monthly_buyer * term_months, 2),
            "total_wex_revenue": round(monthly_spread * term_months, 2),
            "security_deposit": round(monthly_buyer, 2),
            "first_month_payment": round(monthly_buyer, 2),
            "upfront_total": round(monthly_buyer * 2, 2),
        }
