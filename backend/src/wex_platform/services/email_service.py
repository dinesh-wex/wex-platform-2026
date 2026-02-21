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
            from_email=Email(alert_from, "WEx Alerts"),
            to_emails=To(alert_to),
            subject=f"[WEx EarnCheck] New Supplier Lead: {address}",
            html_content=HtmlContent(html_body),
        )
        result = await asyncio.to_thread(_send_mail, mail)
        if result:
            logger.info("Internal alert sent for lead: %s", address)
        return result
    except Exception:
        logger.exception("Failed to send internal alert for %s", data.get("address"))
        return False
