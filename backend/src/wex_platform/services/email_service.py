"""SendGrid email service for WEx smoke test.

Sends income report emails to suppliers and internal alerts to the WEx team.
Uses asyncio.to_thread to wrap the synchronous SendGrid client.
"""

import asyncio
import logging
import urllib.parse

import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read from Pydantic settings (which loads .env)
# ---------------------------------------------------------------------------


def _get_config():
    """Get email config from app settings (lazy to avoid import-time issues)."""
    from wex_platform.app.config import get_settings
    s = get_settings()
    return s.sendgrid_api_key, s.supply_alert_from, s.supply_alert_to


def _get_client() -> sendgrid.SendGridAPIClient:
    """Return a configured SendGrid API client."""
    api_key, _, _ = _get_config()
    return sendgrid.SendGridAPIClient(api_key=api_key)


def _format_currency(value) -> str:
    """Format a number as $XX,XXX."""
    try:
        return f"${int(float(value)):,}"
    except (ValueError, TypeError):
        return "$0"


def _build_income_report_html(data: dict) -> str:
    """Build the Additional Income Report HTML email body."""
    address = data.get("address", "your property")
    sqft = data.get("sqft", 0)
    rate = data.get("rate", 0)
    revenue = data.get("revenue", 0)
    pricing_path = data.get("pricing_path", "")
    building_data = data.get("building_data") or {}

    revenue_display = _format_currency(revenue)

    # Build verify-lead URL with pre-filled params
    from wex_platform.app.config import get_settings
    frontend_url = get_settings().frontend_url.rstrip("/")
    params_dict = {
        "email": data.get("email", ""),
        "address": address,
        "sqft": str(int(float(sqft))),
        "revenue": str(int(float(revenue))),
        "rate": str(rate),
        "pricing_path": pricing_path,
    }
    if data.get("market_rate_low"):
        params_dict["market_rate_low"] = str(data["market_rate_low"])
    if data.get("market_rate_high"):
        params_dict["market_rate_high"] = str(data["market_rate_high"])
    if data.get("recommended_rate"):
        params_dict["recommended_rate"] = str(data["recommended_rate"])
    if data.get("session_id"):
        params_dict["session_id"] = data["session_id"]
    if data.get("is_test"):
        params_dict["is_test"] = "true"
    verify_params = urllib.parse.urlencode(params_dict)
    verify_url = f"{frontend_url}/verify-lead?{verify_params}"

    # Pricing path description
    pricing_line = ""
    if pricing_path == "set_rate":
        pricing_line = f"""
        <tr>
            <td style="padding: 8px 0; color: #4b5563; font-size: 15px;">
                You selected a fixed rate of ${float(rate):.2f}/sqft/mo
            </td>
        </tr>
        """
    elif pricing_path == "commission":
        pricing_line = """
        <tr>
            <td style="padding: 8px 0; color: #4b5563; font-size: 15px;">
                You selected the manual control model (15% commission)
            </td>
        </tr>
        """

    # Building details section
    building_rows = ""
    if building_data:
        details = []
        if building_data.get("year_built"):
            details.append(f"Year Built: {building_data['year_built']}")
        if building_data.get("clear_height_ft"):
            details.append(f"Clear Height: {building_data['clear_height_ft']} ft")
        if building_data.get("construction_type"):
            details.append(f"Construction: {building_data['construction_type']}")
        if building_data.get("dock_doors"):
            details.append(f"Dock Doors: {building_data['dock_doors']}")
        if building_data.get("zoning"):
            details.append(f"Zoning: {building_data['zoning']}")

        if details:
            detail_items = "".join(
                f'<li style="padding: 4px 0; color: #4b5563;">{d}</li>'
                for d in details
            )
            building_rows = f"""
            <tr>
                <td style="padding: 20px 0 8px 0;">
                    <span style="font-size: 14px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 0.5px;">
                        Building Details
                    </span>
                </td>
            </tr>
            <tr>
                <td>
                    <ul style="margin: 0; padding-left: 20px; font-size: 15px;">
                        {detail_items}
                    </ul>
                </td>
            </tr>
            """

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #065f46; padding: 32px 40px;">
                            <span style="font-size: 14px; font-weight: 700; color: rgba(255,255,255,0.7); letter-spacing: 3px; text-transform: uppercase; display: block; margin-bottom: 4px;">
                                EARNCHECK™ REPORT
                            </span>
                            <span style="font-size: 20px; font-weight: 600; color: #ffffff; letter-spacing: -0.3px;">
                                Warehouse Exchange
                            </span>
                        </td>
                    </tr>
                    <!-- Green accent bar -->
                    <tr>
                        <td style="background-color: #10b981; height: 4px;"></td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="font-size: 16px; color: #1f2937; padding-bottom: 16px;">
                                        Hi there,
                                    </td>
                                </tr>
                                <tr>
                                    <td style="font-size: 16px; color: #4b5563; line-height: 1.6; padding-bottom: 24px;">
                                        Your EarnCheck analysis for <strong>{address}</strong> is ready. Here's what your under-utilized space could earn:
                                    </td>
                                </tr>
                                <!-- Big revenue number -->
                                <tr>
                                    <td align="center" style="padding: 24px 0;">
                                        <div style="background-color: #ecfdf5; border-radius: 12px; padding: 28px 40px; display: inline-block;">
                                            <span style="font-size: 42px; font-weight: 800; color: #059669; letter-spacing: -1px;">
                                                {revenue_display}/yr
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                                <!-- Details -->
                                <tr>
                                    <td align="center" style="padding: 8px 0 24px 0; font-size: 15px; color: #6b7280;">
                                        {int(float(sqft)):,} sqft at ${float(rate):.2f}/sqft/mo
                                    </td>
                                </tr>
                                {pricing_line}
                                {building_rows}
                                <!-- Next Step: Verify Ownership -->
                                <tr>
                                    <td style="padding: 28px 0 8px 0;">
                                        <span style="font-size: 14px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 0.5px;">
                                            Next Step: Verify Ownership
                                        </span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="font-size: 15px; color: #4b5563; line-height: 1.6; padding-bottom: 24px;">
                                        To unlock this additional revenue stream, we need to confirm the primary point of contact for this asset. Please verify your details to proceed.
                                    </td>
                                </tr>
                                <!-- CTA Button -->
                                <tr>
                                    <td align="center" style="padding: 0 0 16px 0;">
                                        <a href="{verify_url}" style="display: inline-block; background-color: #059669; color: #ffffff; font-size: 18px; font-weight: 700; text-decoration: none; padding: 16px 48px; border-radius: 10px; letter-spacing: 0.3px;">
                                            Start Earning Now
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- About EarnCheck -->
                    <tr>
                        <td style="padding: 24px 40px 0 40px; border-top: 1px solid #e5e7eb;">
                            <p style="font-size: 12px; font-weight: 600; color: #6b7280; margin: 0 0 6px 0;">About EarnCheck™</p>
                            <p style="font-size: 11px; color: #9ca3af; line-height: 1.6; margin: 0;">
                                This number is an estimate of your potential revenue based on public rental listings, local market data, and active tenant demand on the Warehouse Exchange network. It is a starting point, not a guaranteed offer. Actual income will vary based on your building's final amenities and availability.
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 24px 40px; border-top: 1px solid #e5e7eb;">
                            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="font-size: 13px; color: #9ca3af; line-height: 1.6;">
                                        &copy; 2026 Warehouse Exchange Inc.
                                    </td>
                                </tr>
                                <tr>
                                    <td style="font-size: 13px; color: #9ca3af; padding-top: 8px;">
                                        <a href="https://warehouseexchange.com/resources/privacy-policy" style="color: #6b7280; text-decoration: underline;">Privacy Policy</a>
                                        &nbsp;&middot;&nbsp;
                                        <a href="https://warehouseexchange.com/resources/terms-of-services" style="color: #6b7280; text-decoration: underline;">Terms of Service</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return html


def _build_internal_alert_html(data: dict) -> str:
    """Build the internal alert HTML email body."""
    email = data.get("email", "unknown")
    address = data.get("address", "N/A")
    sqft = data.get("sqft", "N/A")
    rate = data.get("rate", "N/A")
    revenue = data.get("revenue", "N/A")
    pricing_path = data.get("pricing_path", "N/A")
    building_data = data.get("building_data") or {}

    building_lines = ""
    if building_data:
        for key, val in building_data.items():
            if val is not None:
                label = key.replace("_", " ").title()
                building_lines += f"<li><strong>{label}:</strong> {val}</li>"

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f3f4f6;">
    <table width="600" cellpadding="0" cellspacing="0" style="background: #fff; border-radius: 8px; padding: 32px; margin: 0 auto;">
        <tr>
            <td>
                <h2 style="color: #065f46; margin-top: 0;">New Supplier Lead</h2>
                <table width="100%" cellpadding="6" cellspacing="0" style="font-size: 14px; color: #374151;">
                    <tr><td style="font-weight:600; width:140px;">Email:</td><td>{email}</td></tr>
                    <tr><td style="font-weight:600;">Address:</td><td>{address}</td></tr>
                    <tr><td style="font-weight:600;">Square Footage:</td><td>{sqft}</td></tr>
                    <tr><td style="font-weight:600;">Rate:</td><td>${rate}/sqft/mo</td></tr>
                    <tr><td style="font-weight:600;">Est. Revenue:</td><td>{_format_currency(revenue)}/yr</td></tr>
                    <tr><td style="font-weight:600;">Pricing Path:</td><td>{"Automated (Fixed Rate)" if pricing_path == "set_rate" else "Manual (Negotiated)" if pricing_path in ("commission", "negotiate") else pricing_path}</td></tr>
                </table>
                {"<h3 style='color:#065f46; margin-top:24px;'>Building Data</h3><ul style='font-size:14px; color:#4b5563;'>" + building_lines + "</ul>" if building_lines else ""}
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return html


def _send_mail(mail: Mail) -> bool:
    """Synchronous send via SendGrid. Returns True on success."""
    client = _get_client()
    response = client.send(mail)
    if response.status_code in (200, 201, 202):
        return True
    logger.error(
        "SendGrid returned status %s: %s",
        response.status_code,
        response.body,
    )
    return False


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def send_income_report(email: str, data: dict) -> bool:
    """Send the Additional Income Report email to a supplier.

    Args:
        email: Recipient email address.
        data: Dict containing address, sqft, rate, revenue, pricing_path,
              and optionally building_data.

    Returns:
        True on success, False on failure.
    """
    api_key, alert_from, _ = _get_config()
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set — skipping income report email")
        return False

    try:
        html_body = _build_income_report_html(data)
        mail = Mail(
            from_email=Email(alert_from, "Warehouse Exchange"),
            to_emails=To(email),
            subject=f"Your EarnCheck Result for {data.get('address', 'your property')}",
            html_content=HtmlContent(html_body),
        )
        result = await asyncio.to_thread(_send_mail, mail)
        if result:
            logger.info("Income report email sent to %s", email)
        return result
    except Exception:
        logger.exception("Failed to send income report email to %s", email)
        return False


async def send_internal_alert(data: dict) -> bool:
    """Send an internal alert when a new supplier lead is captured.

    Args:
        data: Dict containing email, address, sqft, rate, revenue,
              pricing_path, and optionally building_data.

    Returns:
        True on success, False on failure.
    """
    api_key, alert_from, alert_to = _get_config()
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set — skipping internal alert email")
        return False

    try:
        address = data.get("address", "Unknown")
        html_body = _build_internal_alert_html(data)
        mail = Mail(
            from_email=Email(alert_from, "Warehouse Exchange Alerts"),
            to_emails=To(alert_to),
            subject=f"[Warehouse Exchange] New Supplier Lead: {address}",
            html_content=HtmlContent(html_body),
        )
        result = await asyncio.to_thread(_send_mail, mail)
        if result:
            logger.info("Internal alert sent for lead: %s", address)
        return result
    except Exception:
        logger.exception("Failed to send internal alert for %s", data.get("address"))
        return False


# ---------------------------------------------------------------------------
# Escalation emails (buyer question the AI cannot answer)
# ---------------------------------------------------------------------------


def _build_escalation_email_html(data: dict) -> str:
    """Build HTML email for an escalation notification (buyer question needs answer)."""
    property_address = data.get("property_address", "Unknown Property")
    property_id = data.get("property_id", "N/A")
    question_text = data.get("question_text", "")
    source_type = data.get("source_type", "unknown")
    buyer_phone = data.get("buyer_phone", "N/A")
    buyer_name = data.get("buyer_name") or "Unknown"
    thread_id = data.get("thread_id", "N/A")
    reply_tool_url = data.get("reply_tool_url", "#")
    recent_messages = data.get("recent_messages") or []
    field_key = data.get("field_key")

    channel_display = "SMS" if source_type == "sms" else "Voice" if source_type == "voice" else source_type.title()

    # Build recent conversation rows (last 5)
    conversation_rows = ""
    for msg in recent_messages[-5:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "buyer":
            prefix = "&#128229; Buyer"
            color = "#1f2937"
        else:
            prefix = "&#128228; Agent"
            color = "#4b5563"
        conversation_rows += (
            f'<p style="margin: 6px 0; font-size: 13px; color: {color};">'
            f'<strong>{prefix}:</strong> {content}</p>'
        )

    if not conversation_rows:
        conversation_rows = '<p style="margin: 6px 0; font-size: 13px; color: #6b7280;">No recent messages available.</p>'

    # Optional field key line
    field_key_row = ""
    if field_key:
        field_key_row = f"""
    <tr>
      <td style="padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6; width: 30%;"><strong>Field</strong></td>
      <td style="padding: 10px; border: 1px solid #dee2e6;">{field_key}</td>
    </tr>"""

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">

  <div style="background-color: #f8f9fa; border-left: 4px solid #dc3545; padding: 15px; margin-bottom: 20px;">
    <h2 style="margin: 0 0 10px 0; color: #dc3545;">Escalation &mdash; Buyer Question Needs Answer</h2>
    <p style="margin: 0; font-size: 14px; color: #666;">Action required &mdash; PropertyInsight + cache could not resolve</p>
  </div>

  <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
    <tr>
      <td style="padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6; width: 30%;"><strong>Property</strong></td>
      <td style="padding: 10px; border: 1px solid #dee2e6;">{property_address}</td>
    </tr>
    <tr>
      <td style="padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6;"><strong>Property ID</strong></td>
      <td style="padding: 10px; border: 1px solid #dee2e6;">{property_id}</td>
    </tr>
    <tr>
      <td style="padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6;"><strong>Buyer</strong></td>
      <td style="padding: 10px; border: 1px solid #dee2e6;">
        {buyer_name}<br>
        <a href="tel:{buyer_phone}" style="color: #007bff;">{buyer_phone}</a>
      </td>
    </tr>
    <tr>
      <td style="padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6;"><strong>Channel</strong></td>
      <td style="padding: 10px; border: 1px solid #dee2e6;">{channel_display}</td>
    </tr>{field_key_row}
  </table>

  <div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
    <h3 style="margin: 0 0 10px 0; color: #856404;">Question</h3>
    <p style="margin: 0; white-space: pre-wrap;">{question_text}</p>
  </div>

  <div style="background-color: #e7f3ff; border: 1px solid #b6d4fe; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
    <h3 style="margin: 0 0 10px 0; color: #084298;">Recent Conversation</h3>
    {conversation_rows}
  </div>

  <div style="text-align: center; margin: 30px 0;">
    <a href="{reply_tool_url}"
       style="display: inline-block; background-color: #007bff; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">
      Open Reply Tool
    </a>
  </div>

  <p style="text-align: center; font-size: 12px; color: #666;">
    If the button doesn't work, copy this link:<br>
    <a href="{reply_tool_url}" style="color: #007bff; word-break: break-all;">{reply_tool_url}</a>
  </p>

  <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">

  <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 10px; margin-bottom: 15px;">
    <p style="margin: 0; color: #721c24; font-size: 13px;">
      <strong>Important:</strong> This is an internal ops notification. The property owner has NOT been contacted.
    </p>
  </div>

  <p style="font-size: 11px; color: #999;">
    Thread ID: {thread_id}<br>
    Property ID: {property_id}
  </p>

</body>
</html>
"""
    return html


async def send_escalation_email(data: dict) -> bool:
    """Send escalation notification when PropertyInsight + cache can't answer a buyer question."""
    api_key, alert_from, alert_to = _get_config()
    if not api_key:
        logger.warning("SendGrid not configured, skipping escalation email")
        return False

    property_address = data.get("property_address", "Unknown Property")
    html = _build_escalation_email_html(data)

    mail = Mail(
        from_email=Email(alert_from, "Warehouse Exchange Escalation"),
        to_emails=alert_to,
        subject=f"[Warehouse Exchange] Buyer Question — {property_address}",
        html_content=Content("text/html", html),
    )

    try:
        success = await asyncio.to_thread(_send_mail, mail)
        if success:
            logger.info("Escalation email sent for thread %s", data.get("thread_id"))
        return success
    except Exception:
        logger.exception("Failed to send escalation email")
        return False


def _build_human_escalation_html(data: dict) -> str:
    """Build HTML for human escalation notification."""
    phone = data.get("phone", "Unknown")
    buyer_name = data.get("buyer_name", "Unknown")
    reason = data.get("reason", "Buyer requested human assistance")
    phase = data.get("phase", "Unknown")
    criteria = data.get("criteria_snapshot", {})
    recent = data.get("conversation_history", [])

    criteria_rows = ""
    for key, val in criteria.items():
        if val and key != "match_summaries":
            label = key.replace("_", " ").title()
            criteria_rows += f"<tr><td style='font-weight:600; padding: 6px 12px 6px 0;'>{label}:</td><td>{val}</td></tr>"

    conversation_rows = ""
    for msg in recent[-5:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        prefix = "Buyer" if role in ("buyer", "user") else "Robin"
        conversation_rows += f"<p style='margin: 4px 0; font-size: 13px;'><strong>{prefix}:</strong> {content}</p>"

    return f"""
<html><body style="font-family: Arial, sans-serif; padding: 20px;">
<div style="background-color: #fef3cd; border-left: 4px solid #f59e0b; padding: 15px; margin-bottom: 20px;">
  <h2 style="margin: 0; color: #92400e;">Human Assistance Requested</h2>
  <p style="margin: 8px 0 0; color: #92400e;">{reason}</p>
</div>
<table style="font-size: 14px; color: #374151;">
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Phone:</td><td><a href="tel:{phone}">{phone}</a></td></tr>
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Name:</td><td>{buyer_name}</td></tr>
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Phase:</td><td>{phase}</td></tr>
  {criteria_rows}
</table>
<h3 style="color: #374151; margin-top: 20px;">Recent Conversation</h3>
<div style="background: #f3f4f6; padding: 12px; border-radius: 6px;">{conversation_rows or '<p>No messages available.</p>'}</div>
</body></html>
"""


async def send_human_escalation_email(data: dict) -> bool:
    """Send notification when a buyer requests human assistance.

    Args:
        data: Dict with phone, buyer_name, conversation_history, criteria_snapshot,
              phase, reason.
    """
    api_key, alert_from, alert_to = _get_config()
    if not api_key:
        logger.warning("SendGrid not configured, skipping human escalation email")
        return False

    phone = data.get("phone", "Unknown")
    html = _build_human_escalation_html(data)

    mail = Mail(
        from_email=Email(alert_from, "Warehouse Exchange"),
        to_emails=To(alert_to),
        subject=f"[WEx] Human Assistance Requested - {phone}",
        html_content=Content("text/html", html),
    )

    try:
        success = await asyncio.to_thread(_send_mail, mail)
        if success:
            logger.info("Human escalation email sent for %s", phone)
        return success
    except Exception:
        logger.exception("Failed to send human escalation email for %s", phone)
        return False


def _build_callback_request_html(data: dict) -> str:
    """Build HTML for callback request notification."""
    phone = data.get("phone", "Unknown")
    buyer_name = data.get("buyer_name", "Unknown")
    requested_time = data.get("requested_time", "Not specified")
    criteria = data.get("criteria_snapshot", {})
    recent = data.get("conversation_history", [])

    criteria_rows = ""
    for key, val in list(criteria.items())[:5]:
        if val and key != "match_summaries":
            label = key.replace("_", " ").title()
            criteria_rows += f"<tr><td style='font-weight:600; padding: 6px 12px 6px 0;'>{label}:</td><td>{val}</td></tr>"

    conversation_rows = ""
    for msg in recent[-5:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        prefix = "Buyer" if role in ("buyer", "user") else "Robin"
        conversation_rows += f"<p style='margin: 4px 0; font-size: 13px;'><strong>{prefix}:</strong> {content}</p>"

    return f"""
<html><body style="font-family: Arial, sans-serif; padding: 20px;">
<div style="background-color: #dbeafe; border-left: 4px solid #3b82f6; padding: 15px; margin-bottom: 20px;">
  <h2 style="margin: 0; color: #1e40af;">Callback Requested</h2>
  <p style="margin: 8px 0 0; color: #1e40af;">Preferred time: {requested_time}</p>
</div>
<table style="font-size: 14px; color: #374151;">
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Phone:</td><td><a href="tel:{phone}">{phone}</a></td></tr>
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Name:</td><td>{buyer_name}</td></tr>
  {criteria_rows}
</table>
<h3 style="color: #374151; margin-top: 20px;">Recent Conversation</h3>
<div style="background: #f3f4f6; padding: 12px; border-radius: 6px;">{conversation_rows or '<p>No messages available.</p>'}</div>
</body></html>
"""


async def send_callback_request_email(data: dict) -> bool:
    """Send notification when a buyer requests a callback."""
    api_key, alert_from, alert_to = _get_config()
    if not api_key:
        logger.warning("SendGrid not configured, skipping callback request email")
        return False

    phone = data.get("phone", "Unknown")
    requested_time = data.get("requested_time", "Not specified")
    html = _build_callback_request_html(data)

    mail = Mail(
        from_email=Email(alert_from, "Warehouse Exchange"),
        to_emails=To(alert_to),
        subject=f"[WEx] Callback Requested - {phone} ({requested_time})",
        html_content=Content("text/html", html),
    )

    try:
        success = await asyncio.to_thread(_send_mail, mail)
        if success:
            logger.info("Callback request email sent for %s", phone)
        return success
    except Exception:
        logger.exception("Failed to send callback request email for %s", phone)
        return False


def _build_tool_limit_html(data: dict) -> str:
    """Build HTML for tool limit notification email."""
    phone = data.get("phone", "Unknown")
    channel = data.get("channel", "unknown")
    tool_key = data.get("tool_key", "unknown")
    count = data.get("count", 0)
    limits = data.get("limits", {})
    call_id = data.get("call_id", "")

    limits_str = ", ".join(f"{k}: {v}" for k, v in limits.items())

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
        <div style="background: #f57c00; color: white; padding: 12px 20px; border-radius: 8px 8px 0 0;">
            <strong>Tool Limit Hit</strong>
        </div>
        <div style="border: 1px solid #ddd; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
            <p><strong>Phone:</strong> {phone}</p>
            <p><strong>Channel:</strong> {channel}</p>
            <p><strong>Tool:</strong> {tool_key} (hit {count} calls)</p>
            <p><strong>Configured limits:</strong> {limits_str}</p>
            {"<p><strong>Call ID:</strong> " + call_id + "</p>" if call_id else ""}
            <p style="color: #666; font-size: 13px; margin-top: 16px;">
                This buyer was redirected to team follow-up. Check if this is a legitimate buyer
                who needs more options or a potential enumeration attempt.
            </p>
        </div>
    </div>
    """


async def send_tool_limit_email(data: dict) -> bool:
    """Send notification when a buyer hits tool usage limits."""
    api_key, alert_from, alert_to = _get_config()
    if not api_key:
        logger.warning("SendGrid not configured, skipping tool limit email")
        return False

    phone = data.get("phone", "Unknown")
    channel = data.get("channel", "unknown")
    tool_key = data.get("tool_key", "unknown")

    subject = f"[WEx] Tool Limit Hit - {phone} ({channel})"
    html = _build_tool_limit_html(data)

    mail = Mail(
        from_email=Email(alert_from, "Warehouse Exchange"),
        to_emails=To(alert_to),
        subject=subject,
        html_content=Content("text/html", html),
    )

    try:
        await asyncio.to_thread(_send_mail, mail)
        logger.info("Tool limit email sent for %s (%s, %s)", phone, channel, tool_key)
        return True
    except Exception:
        logger.exception("Failed to send tool limit email")
        return False


async def send_supplier_redirect_email(data: dict) -> bool:
    """Send internal notification when a supplier contacts the buyer SMS line."""
    api_key, alert_from, alert_to = _get_config()
    if not api_key:
        logger.warning("SendGrid not configured, skipping supplier redirect email")
        return False

    phone = data.get("phone", "Unknown")
    buyer_name = data.get("buyer_name") or "Unknown"
    message_text = data.get("message", "")
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""
<html><body style="font-family: Arial, sans-serif; padding: 20px;">
<h2 style="color: #065f46;">Supplier Inquiry via SMS</h2>
<table style="font-size: 14px; color: #374151;">
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Phone:</td><td>{phone}</td></tr>
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Name:</td><td>{buyer_name}</td></tr>
  <tr><td style="font-weight:600; padding: 6px 12px 6px 0;">Time:</td><td>{timestamp}</td></tr>
</table>
<h3 style="color: #374151; margin-top: 20px;">Message</h3>
<p style="background: #f3f4f6; padding: 12px; border-radius: 6px; white-space: pre-wrap;">{message_text}</p>
</body></html>
"""

    mail = Mail(
        from_email=Email(alert_from, "Warehouse Exchange"),
        to_emails=To(alert_to),
        subject=f"[WEx] Supplier Inquiry from {phone}",
        html_content=Content("text/html", html),
    )

    try:
        success = await asyncio.to_thread(_send_mail, mail)
        if success:
            logger.info("Supplier redirect email sent for phone %s", phone)
        return success
    except Exception:
        logger.exception("Failed to send supplier redirect email")
        return False
