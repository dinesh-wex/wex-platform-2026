# Aircall SMS Fix — Deployment & Configuration Guide

## What Was Implemented

### Problem
The Aircall webhook was registered at the **account level**, meaning every inbound SMS to any number on the account triggered our bot. Human-agent numbers received unwanted auto-replies.

### Changes (3 files)

**1. Number ID filtering on inbound webhooks (already done before this deploy)**

- `backend/src/wex_platform/app/routes/buyer_sms.py` — checks `data.number.id` against `AIRCALL_BUYER_NUMBER_ID`. Ignores messages to any other number.
- `backend/src/wex_platform/app/routes/sms.py` — checks `data.number.id` against `AIRCALL_NUMBER_ID`. Ignores messages to any other number.

**2. Outbound SMS endpoint switch**

- `backend/src/wex_platform/services/sms_service.py` — both `send_sms()` and `send_buyer_sms()` now use:
  ```
  /v1/numbers/{number_id}/messages/send-in-agent-conversation
  ```
  instead of:
  ```
  /v1/numbers/{number_id}/messages/send
  ```

### Why the new endpoint

| | Old (`/messages/send`) | New (`/send-in-agent-conversation`) |
|---|---|---|
| Bot messages in Aircall app | Not visible | Visible to agents |
| Per-number Public API config | Required | Not required |
| Inbound replies in app | Webhook only | App + webhook |
| Auth & request body | Basic Auth, `{"to", "body"}` | Same |

---

## Webhook Configuration (Aircall Dashboard)

### Step 1: Re-add the account-level webhook

1. Go to **Aircall Dashboard** > **Integrations** > **Webhooks**
2. Add a new webhook:
   - **URL:** `https://wex-backend-4tjtpxax5a-uw.a.run.app/api/sms/buyer/webhook`
   - **Events:** `message.received`
3. Save

> The webhook fires for all numbers on the account. The code now filters by number ID, so only the buyer and supplier numbers trigger bot processing.

### Step 2: Remove old Public API config from bot numbers

Since the new endpoint doesn't require per-number Public API configuration, remove it from both bot numbers:

```bash
# Supplier/DLA number
curl -X DELETE -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID/messages/configuration

# Buyer number
curl -X DELETE -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_BUYER_NUMBER_ID/messages/configuration
```

Other numbers don't need changes — they were never in Public API mode.

---

## Environment Variables

No new env vars. These existing secrets (already in Cloud Secret Manager) are used:

| Secret | Purpose |
|---|---|
| `AIRCALL_API_ID` | Basic Auth username |
| `AIRCALL_API_TOKEN` | Basic Auth password |
| `AIRCALL_NUMBER_ID` | Supplier/DLA number — used for filtering + sending |
| `AIRCALL_BUYER_NUMBER_ID` | Buyer number — used for filtering + sending |
| `AIRCALL_WEBHOOK_TOKEN` | Validates inbound webhook authenticity |

---

## Expected Behavior After Deploy

### Bot-managed numbers (buyer + supplier)
- Inbound SMS triggers webhook → code processes it → bot auto-replies
- Bot-sent messages are now **visible in the Aircall app** (agents can see what the bot sent)
- Inbound replies also appear in the Aircall app conversation view

### All other numbers (human-agent numbers)
- Inbound SMS triggers webhook → code checks number ID → **skips processing** (returns `{"ok": true}`)
- No bot auto-reply
- Messages appear only in the Aircall app for the human agent, as before

---

## Verification Checklist

Run these after deploy + webhook re-activation:

- [ ] GitHub Actions deploy completed successfully (new Cloud Run revision serving)
- [ ] Webhook re-added in Aircall Dashboard with `message.received` event
- [ ] **Test buyer number:** Send a text → bot auto-reply received
- [ ] **Test supplier number:** Send a text → bot auto-reply received
- [ ] **Test human-agent number:** Send a text → NO bot auto-reply, message visible in Aircall app
- [ ] **Check Aircall app:** Bot-sent messages visible in conversation view (new behavior)
- [ ] **Check Cloud Run logs:** No unexpected errors from the new endpoint
  ```bash
  gcloud run services logs read wex-backend --region us-west1 --limit 100
  ```
  Look for any 4xx/5xx responses — the new endpoint may return different error codes than `/messages/send`

---

## Known Issue (separate fix)

`send_buyer_notification()` in `sms_service.py` (line ~202) calls `send_sms()` (supplier number) instead of `send_buyer_sms()` (buyer number). Buyer match-alert notifications are sent from the wrong number. This is a pre-existing bug and not part of this fix.
