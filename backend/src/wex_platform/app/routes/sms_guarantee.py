"""SMS Guarantee routes — mobile-optimized signing flow."""
import html
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.infra.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sms/guarantee", tags=["sms-guarantee"])


class SignRequest(BaseModel):
    signer_name: str
    signer_email: str | None = None


@router.get("/{token}", response_class=HTMLResponse)
async def guarantee_page(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Render the guarantee signing page (mobile-optimized)."""
    from wex_platform.services.sms_token_service import SmsTokenService

    token_service = SmsTokenService(db)
    token_record = await token_service.validate_token(token)

    if not token_record:
        return HTMLResponse(
            content="<html><body><h2>This link has expired or is invalid.</h2>"
                    "<p>Please text us to get a new signing link.</p></body></html>",
            status_code=400,
        )

    name = html.escape(token_record.prefilled_name or "")
    email = html.escape(token_record.prefilled_email or "")

    # Simple mobile-optimized HTML form
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WEx Occupancy Guarantee</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; padding: 20px; max-width: 500px; margin: 0 auto; }}
        h1 {{ font-size: 1.5em; color: #1a1a1a; }}
        .field {{ margin: 15px 0; }}
        label {{ display: block; font-weight: 600; margin-bottom: 5px; }}
        input {{ width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; box-sizing: border-box; }}
        button {{ width: 100%; padding: 15px; background: #2563eb; color: white; border: none; border-radius: 8px; font-size: 18px; cursor: pointer; margin-top: 20px; }}
        button:hover {{ background: #1d4ed8; }}
        .terms {{ font-size: 0.85em; color: #666; margin-top: 15px; }}
    </style>
</head>
<body>
    <h1>WEx Occupancy Guarantee</h1>
    <p>Sign below to confirm your interest and unlock the property address.</p>
    <form id="signForm">
        <div class="field">
            <label>Full Name</label>
            <input type="text" id="signer_name" value="{name}" required>
        </div>
        <div class="field">
            <label>Email</label>
            <input type="email" id="signer_email" value="{email}">
        </div>
        <p class="terms">By signing, you agree to WEx's occupancy guarantee terms.
        You will not be charged unless you proceed with a lease.</p>
        <button type="submit">Sign & View Property</button>
    </form>
    <div id="result" style="display:none; margin-top:20px;"></div>
    <script>
        document.getElementById('signForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const btn = e.target.querySelector('button');
            btn.disabled = true;
            btn.textContent = 'Signing...';
            try {{
                const res = await fetch('/sms/guarantee/{token}/sign', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        signer_name: document.getElementById('signer_name').value,
                        signer_email: document.getElementById('signer_email').value || null,
                    }})
                }});
                const data = await res.json();
                if (data.ok) {{
                    document.getElementById('signForm').style.display = 'none';
                    document.getElementById('result').style.display = 'block';
                    document.getElementById('result').innerHTML =
                        '<h2 style="color:#16a34a">Guarantee Signed!</h2>' +
                        '<p>Check your texts for the property address and next steps.</p>';
                }} else {{
                    btn.disabled = false;
                    btn.textContent = 'Sign & View Property';
                    alert(data.detail || 'Something went wrong. Please try again.');
                }}
            }} catch (err) {{
                btn.disabled = false;
                btn.textContent = 'Sign & View Property';
                alert('Network error. Please try again.');
            }}
        }});
    </script>
</body>
</html>"""

    return HTMLResponse(content=html)


@router.post("/{token}/sign")
async def sign_guarantee(
    token: str,
    body: SignRequest,
    db: AsyncSession = Depends(get_db),
):
    """Process guarantee signature."""
    from wex_platform.services.sms_token_service import SmsTokenService
    from wex_platform.services.engagement_bridge import EngagementBridge
    from wex_platform.domain.sms_models import SMSConversationState
    from wex_platform.services.sms_service import SMSService

    token_service = SmsTokenService(db)
    token_record = await token_service.redeem_token(token)

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Handle guarantee signing on the engagement
    engagement_bridge = EngagementBridge(db)

    if token_record.engagement_id:
        result = await engagement_bridge.handle_guarantee_signed(
            engagement_id=token_record.engagement_id,
            signer_name=body.signer_name,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

    # Update conversation state
    state_result = await db.execute(
        select(SMSConversationState).where(
            SMSConversationState.id == token_record.conversation_state_id
        )
    )
    state = state_result.scalar_one_or_none()

    if state:
        state.guarantee_signed_at = datetime.now(timezone.utc)
        state.phase = "TOUR_SCHEDULING"

        if body.signer_name:
            parts = body.signer_name.strip().split(None, 1)
            state.renter_first_name = parts[0]
            state.renter_last_name = parts[1] if len(parts) > 1 else None

        if body.signer_email:
            state.buyer_email = body.signer_email

        # Send address reveal SMS
        if state.focused_match_id and state.phone:
            from wex_platform.domain.models import Property
            prop = await db.get(Property, state.focused_match_id)
            if prop and prop.address:
                try:
                    sms_service = SMSService()
                    await sms_service.send_buyer_sms(
                        state.phone,
                        f"Guarantee signed! Here's the property address: "
                        f"{prop.address}, {prop.city}, {prop.state}. "
                        f"Text me when you'd like to schedule a tour.",
                    )
                    state.last_system_message_at = datetime.now(timezone.utc)
                except Exception as e:
                    logger.error("Failed to send address reveal SMS: %s", e)

    await db.commit()

    return {
        "ok": True,
        "signed": True,
        "engagement_id": token_record.engagement_id,
    }
