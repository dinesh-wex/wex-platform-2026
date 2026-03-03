"""SMS Reply Tool — ops endpoint for answering escalated buyer questions."""
import logging
from datetime import datetime, timezone
from html import escape as html_escape

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.domain.models import BuyerConversation, Property, Warehouse
from wex_platform.domain.sms_models import EscalationThread, SMSConversationState
from wex_platform.infra.database import get_db
from wex_platform.services.sms_service import SMSService

logger = logging.getLogger(__name__)


async def verify_internal_token(x_internal_token: str = Header(...)):
    """Verify that the request includes a valid internal auth token."""
    settings = get_settings()
    if x_internal_token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid internal token")


# ── Form router (no header auth — uses query-param token for browser access) ──

form_router = APIRouter(
    prefix="/api/sms/internal",
    tags=["sms-reply-tool"],
)


@form_router.get("/form/{thread_id}", response_class=HTMLResponse)
async def reply_form(
    thread_id: str,
    token: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Serve an HTML reply form for operators to answer escalated questions."""
    settings = get_settings()

    # --- auth via query-param token ---
    if not token or token != settings.admin_password:
        return HTMLResponse(
            content=_render_error_page("Unauthorized — invalid or missing token"),
            status_code=401,
        )

    # --- load escalation thread ---
    result = await db.execute(
        select(EscalationThread).where(EscalationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        return HTMLResponse(
            content=_render_error_page("Escalation thread not found"),
            status_code=404,
        )

    # --- load conversation state ---
    state = None
    if thread.conversation_state_id:
        state_result = await db.execute(
            select(SMSConversationState).where(
                SMSConversationState.id == thread.conversation_state_id
            )
        )
        state = state_result.scalar_one_or_none()

    # --- property address ---
    address = "Unknown"
    prop_result = await db.execute(
        select(Property).where(Property.id == thread.property_id)
    )
    prop = prop_result.scalar_one_or_none()
    if prop:
        parts = [p for p in [prop.address, prop.city, prop.state] if p]
        address = ", ".join(parts) if parts else "Unknown"
    else:
        wh_result = await db.execute(
            select(Warehouse).where(Warehouse.id == thread.property_id)
        )
        wh = wh_result.scalar_one_or_none()
        if wh:
            parts = [p for p in [wh.address, wh.city, wh.state] if p]
            address = ", ".join(parts) if parts else "Unknown"

    # --- buyer info ---
    buyer_name = "(unknown)"
    buyer_phone = ""
    if state:
        first = state.renter_first_name or ""
        last = state.renter_last_name or ""
        buyer_name = f"{first} {last}".strip() or "(unknown)"
        buyer_phone = state.phone or ""

    channel = thread.source_type or "sms"

    # --- recent messages (last 5 from BuyerConversation) ---
    messages_html = "<p>No recent messages.</p>"
    if state and state.conversation_id:
        conv_result = await db.execute(
            select(BuyerConversation).where(
                BuyerConversation.id == state.conversation_id
            )
        )
        conv = conv_result.scalar_one_or_none()
        if conv and conv.messages:
            recent = (conv.messages or [])[-5:]
            if recent:
                parts = []
                for msg in recent:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    ts = msg.get("timestamp", "")
                    css_class = "buyer" if role == "buyer" else "agent"
                    label = "Buyer" if role == "buyer" else "Agent"
                    parts.append(
                        f'<div class="message {css_class}">'
                        f'<div class="message-header">'
                        f'<span class="direction">{label}</span>'
                        f'<span class="time">{html_escape(str(ts))}</span>'
                        f'</div>'
                        f'<div class="message-body">{html_escape(str(content))}</div>'
                        f'</div>'
                    )
                messages_html = "\n".join(parts)

    # --- already-answered banner ---
    answered_banner = ""
    if thread.status == "answered":
        answer_text = html_escape(thread.answer_sent_text or thread.answer_raw_text or "")
        answered_banner = (
            '<div class="alert alert-success">'
            '<strong>Already Answered</strong>'
            f'<p style="margin:8px 0 0;">{answer_text}</p>'
            '</div>'
        )

    html = _render_form_page(
        thread_id=thread_id,
        address=address,
        property_id=thread.property_id or "",
        buyer_name=buyer_name,
        buyer_phone=buyer_phone,
        channel=channel,
        question_text=thread.question_text or "",
        answered_banner=answered_banner,
        messages_html=messages_html,
        token=token,
        is_answered=thread.status == "answered",
    )
    return HTMLResponse(content=html)


# ── HTML helpers ──────────────────────────────────────────────────────────────


def _render_error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Error - WEx Escalation Reply Tool</title>
<style>
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         max-width:600px; margin:60px auto; padding:20px; text-align:center; color:#333; }}
  .error-box {{ background:#f8d7da; border:1px solid #f5c6cb; color:#721c24;
                padding:30px; border-radius:8px; }}
</style></head><body>
<div class="error-box"><h2>Error</h2><p>{html_escape(message)}</p></div>
</body></html>"""


def _render_form_page(
    *,
    thread_id: str,
    address: str,
    property_id: str,
    buyer_name: str,
    buyer_phone: str,
    channel: str,
    question_text: str,
    answered_banner: str,
    messages_html: str,
    token: str,
    is_answered: bool,
) -> str:
    disabled_attr = 'disabled' if is_answered else ''
    btn_style = 'opacity:0.5;cursor:not-allowed;' if is_answered else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>WEx Escalation Reply Tool</title>
  <style>
    * {{ box-sizing:border-box; }}
    body {{
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      line-height:1.6; color:#333; max-width:800px;
      margin:0 auto; padding:20px; background:#f5f5f5;
    }}
    .card {{
      background:#fff; border-radius:8px; padding:20px;
      margin-bottom:20px; box-shadow:0 2px 4px rgba(0,0,0,.1);
    }}
    h1 {{ color:#2c3e50; margin-top:0; }}
    h2 {{ color:#34495e; border-bottom:2px solid #3498db; padding-bottom:10px; }}
    .info-grid {{
      display:grid; grid-template-columns:120px 1fr; gap:8px 12px;
    }}
    .info-label {{ font-weight:bold; color:#666; }}
    .info-value {{ color:#333; }}
    .question-box {{
      background:#fff3cd; border-left:4px solid #ffc107;
      padding:15px; margin:15px 0; white-space:pre-wrap;
    }}
    .alert {{ padding:15px; border-radius:4px; margin-bottom:20px; }}
    .alert-success {{
      background:#d4edda; border:1px solid #c3e6cb; color:#155724;
    }}
    .messages-container {{
      max-height:350px; overflow-y:auto; border:1px solid #ddd;
      border-radius:4px; padding:15px; background:#fafafa;
    }}
    .message {{ margin-bottom:12px; padding:10px; border-radius:8px; }}
    .message.buyer {{ background:#e3f2fd; margin-right:20%; }}
    .message.agent {{ background:#e8f5e9; margin-left:20%; }}
    .message-header {{
      display:flex; justify-content:space-between;
      font-size:12px; color:#666; margin-bottom:4px;
    }}
    .message-body {{ white-space:pre-wrap; }}
    textarea {{
      width:100%; padding:12px; border:1px solid #ddd;
      border-radius:4px; font-size:14px; resize:vertical; min-height:100px;
    }}
    textarea:focus {{ outline:none; border-color:#3498db; }}
    .char-count {{ text-align:right; font-size:12px; color:#666; margin-top:5px; }}
    .char-count.warning {{ color:#e67e22; }}
    .char-count.danger {{ color:#e74c3c; }}
    .btn-primary {{
      display:inline-block; padding:12px 28px; border:none; border-radius:4px;
      font-size:14px; cursor:pointer; background:#3498db; color:#fff;
      transition:background .2s; {btn_style}
    }}
    .btn-primary:hover:not(:disabled) {{ background:#2980b9; }}
    #result {{
      margin-top:15px; padding:15px; border-radius:4px; display:none;
    }}
    #result.success {{ background:#d4edda; color:#155724; }}
    #result.error {{ background:#f8d7da; color:#721c24; }}
    .footer {{ font-size:12px; color:#999; text-align:center; margin-top:30px; }}
  </style>
</head>
<body>

  <div class="card">
    <h1>Escalation Reply Tool</h1>
    {answered_banner}
  </div>

  <div class="card">
    <h2>Property</h2>
    <div class="info-grid">
      <span class="info-label">Address:</span>
      <span class="info-value">{html_escape(address)}</span>
      <span class="info-label">Property ID:</span>
      <span class="info-value" style="font-size:12px;">{html_escape(property_id)}</span>
    </div>
  </div>

  <div class="card">
    <h2>Buyer</h2>
    <div class="info-grid">
      <span class="info-label">Name:</span>
      <span class="info-value">{html_escape(buyer_name)}</span>
      <span class="info-label">Phone:</span>
      <span class="info-value"><a href="tel:{html_escape(buyer_phone)}">{html_escape(buyer_phone)}</a></span>
      <span class="info-label">Channel:</span>
      <span class="info-value">{html_escape(channel)}</span>
    </div>
  </div>

  <div class="card">
    <h2>Escalation Question</h2>
    <div class="question-box">{html_escape(question_text)}</div>
  </div>

  <div class="card">
    <h2>Recent Conversation (Last 5)</h2>
    <div class="messages-container">
      {messages_html}
    </div>
  </div>

  <div class="card">
    <h2>Send Reply</h2>

    <label for="answer"><strong>Your Reply:</strong></label>
    <textarea id="answer" placeholder="Type your answer to the buyer's question..." {disabled_attr}></textarea>
    <div class="char-count" id="charCount">0 / 320 characters</div>

    <label for="answered_by" style="margin-top:15px;display:block;">
      <strong>Your Email (for audit):</strong>
    </label>
    <input type="email" id="answered_by" value="ops"
           style="width:100%;padding:10px;margin-top:5px;border:1px solid #ddd;border-radius:4px;"
           {disabled_attr}>

    <div style="margin-top:15px;">
      <button class="btn-primary" id="btnSend" onclick="sendReply()" {disabled_attr}>
        Send Reply to Buyer
      </button>
    </div>

    <div id="result"></div>

    <div id="sentDisplay" style="display:none;margin-top:20px;">
      <div class="alert alert-success"><strong>Message Sent</strong></div>
      <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:4px;padding:15px;margin-top:10px;">
        <strong>Final sent text:</strong>
        <p id="sentText" style="white-space:pre-wrap;margin:10px 0 0;"></p>
      </div>
    </div>
  </div>

  <div class="footer">
    Thread ID: {html_escape(thread_id)}
  </div>

  <script>
    var answerInput = document.getElementById('answer');
    var charCount = document.getElementById('charCount');

    if (answerInput) {{
      answerInput.addEventListener('input', function() {{
        var len = this.value.length;
        charCount.textContent = len + ' / 320 characters';
        charCount.className = 'char-count';
        if (len > 320) {{ charCount.className = 'char-count danger'; }}
        else if (len > 280) {{ charCount.className = 'char-count warning'; }}
      }});
    }}

    async function sendReply() {{
      var answer = document.getElementById('answer').value.trim();
      var answeredBy = document.getElementById('answered_by').value.trim() || 'ops';
      var resultDiv = document.getElementById('result');
      var sentDisplay = document.getElementById('sentDisplay');
      var btn = document.getElementById('btnSend');

      if (!answer) {{
        resultDiv.textContent = 'Please enter a reply first.';
        resultDiv.className = 'error';
        resultDiv.style.display = 'block';
        return;
      }}

      btn.disabled = true;
      btn.textContent = 'Sending...';
      resultDiv.style.display = 'none';

      try {{
        var resp = await fetch('/api/sms/internal/reply/{html_escape(thread_id)}', {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'X-Internal-Token': '{html_escape(token)}'
          }},
          body: JSON.stringify({{ answer: answer, answered_by: answeredBy }})
        }});

        var data = await resp.json();

        if (resp.ok && data.ok) {{
          resultDiv.style.display = 'none';
          sentDisplay.style.display = 'block';
          document.getElementById('sentText').textContent = data.answer_sent || answer;
          document.getElementById('answer').disabled = true;
          document.getElementById('answered_by').disabled = true;
          btn.style.display = 'none';
        }} else {{
          resultDiv.textContent = 'Error: ' + (data.detail || data.message || 'Unknown error');
          resultDiv.className = 'error';
          resultDiv.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Send Reply to Buyer';
        }}
      }} catch (err) {{
        resultDiv.textContent = 'Network error: ' + err.message;
        resultDiv.className = 'error';
        resultDiv.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Send Reply to Buyer';
      }}
    }}
  </script>

</body>
</html>"""


# ── API router (header-auth protected) ────────────────────────────────────────

router = APIRouter(
    prefix="/api/sms/internal",
    tags=["sms-reply-tool"],
    dependencies=[Depends(verify_internal_token)],
)


class ReplyRequest(BaseModel):
    answer: str
    answered_by: str = "ops"


@router.get("/reply/{thread_id}")
async def get_escalation_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get escalation thread details for the reply form."""
    result = await db.execute(
        select(EscalationThread).where(EscalationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return {
        "id": thread.id,
        "property_id": thread.property_id,
        "question": thread.question_text,
        "field_key": thread.field_key,
        "status": thread.status,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "sla_deadline_at": thread.sla_deadline_at.isoformat() if thread.sla_deadline_at else None,
    }


@router.post("/reply/{thread_id}")
async def submit_reply(
    thread_id: str,
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer to an escalated question."""
    # Load thread
    result = await db.execute(
        select(EscalationThread).where(EscalationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.status == "answered":
        raise HTTPException(status_code=400, detail="Thread already answered")

    # Load conversation state
    state_result = await db.execute(
        select(SMSConversationState).where(
            SMSConversationState.id == thread.conversation_state_id
        )
    )
    state = state_result.scalar_one_or_none()

    # Record the answer
    from wex_platform.services.escalation_service import EscalationService
    escalation_service = EscalationService(db)
    thread = await escalation_service.record_answer(
        thread_id=thread_id,
        answer_text=body.answer,
        answered_by=body.answered_by,
        state=state,
    )

    if not thread:
        raise HTTPException(status_code=500, detail="Failed to record answer")

    # ── Step 1: Always polish raw answer via PolisherAgent ──
    from wex_platform.agents.sms.polisher_agent import PolisherAgent
    from wex_platform.agents.sms.gatekeeper import validate_outbound
    from wex_platform.agents.sms.field_catalog import get_label

    polisher = PolisherAgent()
    sent_mode = "raw"  # Track for audit

    # Get recent conversation for context
    recent_messages = []
    if state:
        history = getattr(state, "messages", None) or getattr(state, "conversation_history", None) or []
        if isinstance(history, list):
            recent_messages = history[-5:]

    field_label = get_label(thread.field_key) if thread.field_key else None

    polish_result = await polisher.polish_reply(
        raw_answer=body.answer,
        question_text=thread.question_text,
        field_key=thread.field_key,
        field_label=field_label,
        recent_messages=recent_messages,
        max_length=320,
    )

    if polish_result.ok and polish_result.polished_text:
        response_text = polish_result.polished_text
        sent_mode = "polished"
        logger.info(
            "Reply polished: %d -> %d chars",
            polish_result.original_length,
            polish_result.polished_length,
        )
    else:
        # Polishing failed — build a reasonable fallback with question context
        logger.warning("Reply polish failed (code=%s), using template fallback", polish_result.error_code)
        if thread.field_key and field_label:
            response_text = f"Got an answer on {field_label}: {body.answer}"
        elif thread.question_text:
            response_text = f'You asked "{thread.question_text}" - {body.answer}'
        else:
            response_text = f"Got an answer on your question: {body.answer}"
        sent_mode = "raw"

    # ── Step 2: Gatekeeper validation ──
    gate = validate_outbound(response_text)
    if not gate.ok:
        # Try polish() to fix gatekeeper issues (length, formatting)
        fix_result = await polisher.polish(response_text, gate.hint, max_length=320)
        if fix_result.ok and fix_result.polished_text:
            response_text = fix_result.polished_text
            sent_mode = "polished"
        else:
            gate2 = validate_outbound(response_text)
            if not gate2.ok:
                response_text = body.answer[:310]
                sent_mode = "raw"

    # ── Step 3: Store all 3 answer versions for audit ──
    thread.answer_polished_text = response_text  # Update with actual polished text
    thread.answer_sent_text = response_text
    thread.answer_sent_mode = sent_mode

    # ── Step 4: Send to buyer ──
    if state and state.phone:
        try:
            sms_service = SMSService()
            await sms_service.send_buyer_sms(state.phone, response_text)

            # Update state
            state.last_system_message_at = datetime.now(timezone.utc)
            if state.phase == "AWAITING_ANSWER":
                state.phase = "PROPERTY_FOCUSED"

        except Exception as e:
            logger.error("Failed to send escalation answer SMS: %s", e)

    # ── Step 5: Write answer to ContextualMemory for future PropertyInsight lookups ──
    try:
        from wex_platform.domain.models import ContextualMemory
        import uuid as _uuid

        # Build content that PropertyInsight can match on keyword search
        question_part = thread.question_text or ""
        answer_part = response_text
        memory_content = f"Q: {question_part}\nA: {answer_part}" if question_part else answer_part

        cm = ContextualMemory(
            id=str(_uuid.uuid4()),
            warehouse_id=thread.property_id,
            property_id=thread.property_id,
            memory_type="escalation_answer",
            content=memory_content,
            source="reply_tool",
            confidence=0.95,
            metadata_={"thread_id": thread_id, "field_key": thread.field_key},
        )
        db.add(cm)
    except Exception as e:
        logger.error("Failed to write ContextualMemory for escalation answer: %s", e)

    await db.commit()

    return {
        "ok": True,
        "thread_id": thread_id,
        "answer_sent": response_text,
        "sent_mode": sent_mode,
        "status": thread.status,
    }
