"""Settlement Agent - Manages deal lifecycle: contracts, payments, ledgers, insurance."""

import json
import logging
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.settlement import (
    SETTLEMENT_SYSTEM_PROMPT,
    SETTLEMENT_CONTRACT_PROMPT,
    SETTLEMENT_SUPPLIER_NOTIFICATION_PROMPT,
    SETTLEMENT_PAYMENT_SCHEDULE_PROMPT,
    SETTLEMENT_RISK_ASSESSMENT_PROMPT,
)

logger = logging.getLogger(__name__)


class SettlementAgent(BaseAgent):
    """Deal lifecycle manager for the WEx Clearing House.

    The settlement agent handles the post-match phase of a deal:
    generating contract summaries, supplier notifications, payment
    schedules, and risk assessments.  It enforces economic isolation
    between buyer-facing and supplier-facing outputs.

    Temperature is set low (0.2) because financial documents and
    payment schedules must be precise and deterministic.
    """

    def __init__(self):
        super().__init__(
            agent_name="settlement",
            model_name="gemini-3-flash-preview",
            temperature=0.2,  # Precise financial outputs
        )

    # ------------------------------------------------------------------
    # Contract Summary
    # ------------------------------------------------------------------

    async def generate_contract_summary(
        self,
        deal_data: dict,
    ) -> AgentResult:
        """Generate a human-readable buyer service agreement summary.

        Args:
            deal_data: Dict containing deal parameters:
                - warehouse_address, city, state
                - sqft_allocated, use_type
                - term_months, start_date, end_date
                - buyer_rate, monthly_payment
                - security_deposit, first_month, upfront_total
                - clear_height_ft, dock_doors, drive_in_bays
                - has_office_space, has_sprinkler, parking_spaces

        Returns:
            AgentResult with the contract summary text in ``data``.
        """
        sqft = deal_data.get("sqft_allocated", 0)
        buyer_rate = deal_data.get("buyer_rate", 0)
        monthly_payment = deal_data.get("monthly_payment", buyer_rate * sqft)
        security_deposit = deal_data.get("security_deposit", monthly_payment)
        first_month = deal_data.get("first_month", monthly_payment)

        prompt = SETTLEMENT_CONTRACT_PROMPT.format(
            warehouse_address=deal_data.get("warehouse_address", "N/A"),
            city=deal_data.get("city", "N/A"),
            state=deal_data.get("state", "N/A"),
            sqft_allocated=sqft,
            use_type=deal_data.get("use_type", "general storage"),
            term_months=deal_data.get("term_months", 6),
            start_date=deal_data.get("start_date", "TBD"),
            end_date=deal_data.get("end_date", "TBD"),
            buyer_rate=buyer_rate,
            monthly_payment=monthly_payment,
            security_deposit=security_deposit,
            first_month=first_month,
            upfront_total=deal_data.get("upfront_total", security_deposit + first_month),
            clear_height_ft=deal_data.get("clear_height_ft", "N/A"),
            dock_doors=deal_data.get("dock_doors", 0),
            drive_in_bays=deal_data.get("drive_in_bays", 0),
            has_office_space=deal_data.get("has_office_space", False),
            has_sprinkler=deal_data.get("has_sprinkler", False),
            parking_spaces=deal_data.get("parking_spaces", 0),
        )

        result = await self.generate(
            prompt=prompt,
            system_instruction=SETTLEMENT_SYSTEM_PROMPT,
        )

        return result

    # ------------------------------------------------------------------
    # Supplier Notification
    # ------------------------------------------------------------------

    async def generate_supplier_notification(
        self,
        deal_data: dict,
    ) -> AgentResult:
        """Generate a notification to the supplier about a new placement.

        The notification intentionally omits buyer rate, spread, and
        buyer identity details beyond the use type.  It includes the
        WEx Occupancy Guarantee Insurance badge.

        Args:
            deal_data: Dict containing:
                - warehouse_address, city, state
                - sqft_allocated, use_type
                - term_months, start_date
                - supplier_rate, monthly_supplier_payment

        Returns:
            AgentResult with the supplier notification text in ``data``.
        """
        sqft = deal_data.get("sqft_allocated", 0)
        supplier_rate = deal_data.get("supplier_rate", 0)
        monthly_supplier_payment = deal_data.get(
            "monthly_supplier_payment", supplier_rate * sqft
        )

        prompt = SETTLEMENT_SUPPLIER_NOTIFICATION_PROMPT.format(
            warehouse_address=deal_data.get("warehouse_address", "N/A"),
            city=deal_data.get("city", "N/A"),
            state=deal_data.get("state", "N/A"),
            sqft_allocated=sqft,
            use_type=deal_data.get("use_type", "general storage"),
            term_months=deal_data.get("term_months", 6),
            start_date=deal_data.get("start_date", "TBD"),
            monthly_supplier_payment=monthly_supplier_payment,
            supplier_rate=supplier_rate,
        )

        result = await self.generate(
            prompt=prompt,
            system_instruction=SETTLEMENT_SYSTEM_PROMPT,
        )

        return result

    # ------------------------------------------------------------------
    # Payment Schedule
    # ------------------------------------------------------------------

    async def create_payment_schedule(
        self,
        deal_data: dict,
    ) -> AgentResult:
        """Create a JSON payment schedule with monthly line items.

        Returns a structured schedule showing buyer payments to WEx,
        WEx payments to supplier, and WEx spread retained for each
        month of the deal term.

        Args:
            deal_data: Dict containing:
                - term_months, start_date
                - sqft_allocated
                - buyer_rate, supplier_rate
                - monthly_buyer_payment, monthly_supplier_payment, monthly_spread

        Returns:
            AgentResult with parsed JSON schedule in ``data``.
        """
        sqft = deal_data.get("sqft_allocated", 0)
        buyer_rate = deal_data.get("buyer_rate", 0)
        supplier_rate = deal_data.get("supplier_rate", 0)
        monthly_buyer = deal_data.get("monthly_buyer_payment", buyer_rate * sqft)
        monthly_supplier = deal_data.get("monthly_supplier_payment", supplier_rate * sqft)
        monthly_spread = deal_data.get("monthly_spread", monthly_buyer - monthly_supplier)

        prompt = SETTLEMENT_PAYMENT_SCHEDULE_PROMPT.format(
            term_months=deal_data.get("term_months", 6),
            start_date=deal_data.get("start_date", "TBD"),
            sqft_allocated=sqft,
            buyer_rate=buyer_rate,
            supplier_rate=supplier_rate,
            monthly_buyer_payment=monthly_buyer,
            monthly_supplier_payment=monthly_supplier,
            monthly_spread=monthly_spread,
        )

        result = await self.generate_json(
            prompt=prompt,
            system_instruction=SETTLEMENT_SYSTEM_PROMPT,
        )

        return result

    # ------------------------------------------------------------------
    # Risk Assessment
    # ------------------------------------------------------------------

    async def assess_deal_risk(
        self,
        deal_data: dict,
    ) -> AgentResult:
        """Assess default risk for a deal based on tenant and deal profile.

        Evaluates risk across multiple dimensions: tenant profile,
        deal size relative to market, term length, deposit coverage,
        and market conditions.  Returns a risk score (0-100) with
        detailed reasoning.

        Args:
            deal_data: Dict containing:
                - company_name, use_type, industry_context
                - monthly_payment, total_contract_value, sqft_allocated
                - term_months, security_deposit, deposit_coverage_months
                - city, state, market_strength

        Returns:
            AgentResult with parsed JSON risk assessment in ``data``.
        """
        monthly_payment = deal_data.get("monthly_payment", 0)
        security_deposit = deal_data.get("security_deposit", 0)
        deposit_coverage = (
            security_deposit / monthly_payment
            if monthly_payment > 0
            else 0
        )

        prompt = SETTLEMENT_RISK_ASSESSMENT_PROMPT.format(
            company_name=deal_data.get("company_name", "Unknown"),
            use_type=deal_data.get("use_type", "general storage"),
            industry_context=deal_data.get("industry_context", "Not provided"),
            monthly_payment=monthly_payment,
            total_contract_value=deal_data.get("total_contract_value", 0),
            sqft_allocated=deal_data.get("sqft_allocated", 0),
            term_months=deal_data.get("term_months", 6),
            security_deposit=security_deposit,
            deposit_coverage_months=deal_data.get(
                "deposit_coverage_months", deposit_coverage
            ),
            city=deal_data.get("city", "N/A"),
            state=deal_data.get("state", "N/A"),
            market_strength=deal_data.get("market_strength", "moderate"),
        )

        result = await self.generate_json(
            prompt=prompt,
            system_instruction=SETTLEMENT_SYSTEM_PROMPT,
        )

        return result
