# Aircall Webhook Issue & Fix Plan

## The Issue

Our Aircall account has multiple phone numbers. Only 2 of them are bot-managed (buyer intake + supplier DLA outreach). The rest are used by human agents who send and receive texts manually through the Aircall app.

When we set up the inbound SMS webhook in the Aircall Dashboard (under **Integrations > Webhooks**), it registered at the **account level** — meaning every inbound SMS to ANY number on the account triggered our webhook. Our webhook code had no filter to check which number received the message, so the bot processed and auto-replied to texts on every number, not just the buyer and supplier numbers.

**Impact:** People texting any of our Aircall numbers received automated bot replies instead of reaching the human agents who manage those numbers.

**Immediate action taken:** The webhook was disconnected (removed from Aircall Dashboard) to stop the unwanted auto-replies. SMS on all numbers is currently working normally through the Aircall app, but the buyer and supplier bot automation is offline.

---

## What We Learned from Aircall Support

Aircall confirmed (via Emily H., Senior Customer Support):

> - **Webhooks are account-level.** Message event webhooks track toggled-on events for ALL numbers on the account. There is no way to scope a webhook to a single number.
> - **API endpoint configurations are per-number.** The `POST /messages/configuration` (Public API mode) is individual to each number.

Aircall has **two SMS API endpoints**:

| | "Send Message" (what we used) | "Send Message in Agent Conversation" (recommended) |
|---|---|---|
| Endpoint | `/v1/numbers/{id}/messages/send` | `/v1/numbers/{id}/messages/send-in-agent-conversation` |
| Per-number config | Requires `POST /messages/configuration` | No configuration needed |
| Messages in Aircall app | No — invisible to agents | Yes — visible to agents |
| Inbound replies in app | No — only sent to webhook | Yes — appear in app AND webhooks |

**Reference:** [Aircall Messaging API](https://support.aircall.io/en-gb/articles/20698710100381)

---

## Recommended Fix: Switch to "Send Message in Agent Conversation"

Switching to the newer endpoint solves both problems:

1. **Bot messages become visible in the Aircall app** — team can see what the bot is sending
2. **No per-number Public API configuration needed** — removes the risk of accidentally misconfiguring numbers
3. **Inbound replies appear in the Aircall app AND webhooks** — human agents can see conversations even on bot-managed numbers

The webhook still fires for all numbers (Aircall limitation), but our code now filters by number ID so only the buyer/supplier numbers trigger auto-replies.

---

## Code Changes

### Already Done: Webhook number filters

Both webhook handlers now check `data.number.id` from the Aircall payload and skip processing if the message wasn't sent to the expected number.

**`backend/src/wex_platform/app/routes/buyer_sms.py`** — filters against `AIRCALL_BUYER_NUMBER_ID`:
```python
if settings.aircall_buyer_number_id:
    receiving_number_id = str(
        (body.get("data", {}).get("number") or {}).get("id", "")
        or (body.get("data", {}).get("message", {}).get("number") or {}).get("id", "")
    )
    if receiving_number_id and receiving_number_id != settings.aircall_buyer_number_id:
        logger.debug("Ignoring SMS to Aircall number %s (not buyer number %s)", ...)
        return {"ok": True}
```

**`backend/src/wex_platform/app/routes/sms.py`** — same filter against `AIRCALL_NUMBER_ID`.

### Remaining: Switch send endpoint in sms_service.py

**File:** `backend/src/wex_platform/services/sms_service.py`

Change the URL path in both `send_sms()` and `send_buyer_sms()`:

```
OLD: /v1/numbers/{number_id}/messages/send
NEW: /v1/numbers/{number_id}/messages/send-in-agent-conversation
```

Same auth (Basic Auth) and same request body (`{"to": ..., "body": ...}`).

---

## Pending: Questions for Aircall

Before making the endpoint switch, we emailed Aircall to confirm:

1. Does `/messages/send-in-agent-conversation` use the same request body as `/messages/send` — `{"to": "+1...", "body": "..."}`?
2. After switching, should we remove the existing Public API configuration (`DELETE /messages/configuration`) from our 2 bot numbers, or can both coexist?
3. Will this change affect our other numbers? We want human agents' numbers to continue working exactly as they do today.

**Do not proceed with the endpoint switch until Aircall confirms.**

---

## Aircall Admin Steps (after deploying code)

### 1. Re-add the account-level webhook

In the Aircall Dashboard:
1. Go to **Integrations** > **Webhooks**
2. Add webhook URL: `https://your-domain.com/api/sms/buyer/webhook`
3. Select events: `message.received`
4. Save

The code now filters by number ID, so only buyer/supplier numbers trigger auto-replies.

### 2. (After switching endpoint) Remove Public API config from bot numbers

Since the new endpoint doesn't need it:

```bash
curl -X DELETE -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_BUYER_NUMBER_ID/messages/configuration

curl -X DELETE -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID/messages/configuration
```

Other numbers don't need changes — they were never in Public API mode.

---

## Verification

1. Deploy the code (number filters + new endpoint)
2. Re-add the webhook in Aircall Dashboard
3. Remove Public API config from buyer + supplier numbers
4. **Test bot numbers:** Text the buyer number → should get bot auto-reply as before
5. **Test other numbers:** Text another Aircall number → NO bot auto-reply, message visible in Aircall app for the agent managing that number
6. **Test bot visibility:** Check that bot-sent messages now appear in the Aircall app conversation view
