"""Agreement signing routes: mock DocuSign replacement with checkbox-based acceptance."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.routes.auth import get_current_user_dep
from wex_platform.domain.models import (
    Buyer,
    BuyerAgreement,
    SupplierAgreement,
    User,
    Warehouse,
)
from wex_platform.domain.schemas import AgreementSign, AgreementStatus
from wex_platform.infra.database import get_db

router = APIRouter(prefix="/api/agreements", tags=["agreements"])

AGREEMENT_VERSION = "1.0"


@router.post("/sign", response_model=AgreementStatus)
async def sign_agreement(
    data: AgreementSign,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """
    Record agreement signature.

    - For 'occupancy_guarantee': creates BuyerAgreement record (buyer signs before tour address reveal).
    - For 'network_agreement': creates SupplierAgreement record (supplier signs during onboarding/DLA).

    Both store: user_id, agreement_type, signed_at timestamp, agreement_version.
    """
    now = datetime.now(timezone.utc)

    if data.type == "occupancy_guarantee":
        # Look up the buyer record for this user (match by email)
        result = await db.execute(
            select(Buyer).where(Buyer.email == user.email)
        )
        buyer = result.scalar_one_or_none()

        # Create a buyer record on-the-fly if one doesn't exist yet
        if not buyer:
            buyer = Buyer(
                id=str(uuid.uuid4()),
                name=user.name,
                email=user.email,
                company=user.company,
                phone=user.phone,
            )
            db.add(buyer)
            await db.flush()

        agreement = BuyerAgreement(
            id=str(uuid.uuid4()),
            user_id=user.id,
            buyer_id=buyer.id,
            deal_id=data.deal_id,
            agreement_type="occupancy_guarantee",
            agreement_version=AGREEMENT_VERSION,
            status="signed",
            signed_at=now,
        )
        db.add(agreement)
        await db.commit()

        return AgreementStatus(
            signed=True,
            signed_at=now.isoformat(),
        )

    elif data.type == "network_agreement":
        if not data.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="warehouse_id is required for network_agreement",
            )

        # Verify warehouse exists
        result = await db.execute(
            select(Warehouse).where(Warehouse.id == data.warehouse_id)
        )
        warehouse = result.scalar_one_or_none()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse not found",
            )

        # Get truth_core_id (nullable FK on SupplierAgreement requires it)
        truth_core_id = None
        if warehouse.truth_core:
            truth_core_id = warehouse.truth_core.id

        # If no truth_core exists, we still need a value for the non-nullable FK.
        # Create a minimal placeholder or raise an error.
        if not truth_core_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse has no TruthCore record. Complete property setup first.",
            )

        agreement = SupplierAgreement(
            id=str(uuid.uuid4()),
            user_id=user.id,
            warehouse_id=data.warehouse_id,
            truth_core_id=truth_core_id,
            agreement_type="network_agreement",
            agreement_version=AGREEMENT_VERSION,
            status="signed",
            terms_json={"version": AGREEMENT_VERSION, "type": "network_agreement"},
            signed_at=now,
        )
        db.add(agreement)
        await db.commit()

        return AgreementStatus(
            signed=True,
            signed_at=now.isoformat(),
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown agreement type: {data.type}. Must be 'occupancy_guarantee' or 'network_agreement'.",
        )


@router.get("/status/{agreement_type}", response_model=AgreementStatus)
async def check_agreement(
    agreement_type: str,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Check if the current user has signed a specific agreement type."""
    if agreement_type == "occupancy_guarantee":
        result = await db.execute(
            select(BuyerAgreement)
            .where(
                BuyerAgreement.user_id == user.id,
                BuyerAgreement.agreement_type == "occupancy_guarantee",
                BuyerAgreement.status == "signed",
            )
            .order_by(BuyerAgreement.signed_at.desc())
            .limit(1)
        )
        agreement = result.scalar_one_or_none()

    elif agreement_type == "network_agreement":
        result = await db.execute(
            select(SupplierAgreement)
            .where(
                SupplierAgreement.user_id == user.id,
                SupplierAgreement.agreement_type == "network_agreement",
                SupplierAgreement.status == "signed",
            )
            .order_by(SupplierAgreement.signed_at.desc())
            .limit(1)
        )
        agreement = result.scalar_one_or_none()

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown agreement type: {agreement_type}. Must be 'occupancy_guarantee' or 'network_agreement'.",
        )

    if agreement and agreement.signed_at:
        return AgreementStatus(
            signed=True,
            signed_at=agreement.signed_at.isoformat(),
        )

    return AgreementStatus(signed=False)
