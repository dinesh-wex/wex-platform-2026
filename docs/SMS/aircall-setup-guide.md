# Aircall SMS API Setup Guide

How to configure Aircall for sending and receiving SMS in the WEx Platform.

## Prerequisites

- Aircall **Professional plan** (required for API messaging)
- An Aircall phone number with SMS capability (US number)
- Aircall API credentials (API ID + API Token) from the Aircall Dashboard
- A publicly accessible webhook URL (Cloudflare Tunnel, ngrok, or production domain)

## 1. Get API Credentials

1. Log into the [Aircall Dashboard](https://dashboard.aircall.io)
2. Go to **Integrations** > **API Keys**
3. Copy your **API ID** and **API Token**
4. Add them to `backend/.env`:

```env
AIRCALL_API_ID=your_api_id_here
AIRCALL_API_TOKEN=your_api_token_here
AIRCALL_NUMBER_ID=your_number_id
AIRCALL_BUYER_NUMBER_ID=your_number_id
```

`AIRCALL_NUMBER_ID` is the numeric ID of your Aircall number (not the phone number itself). You can find it via:

```bash
curl -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" https://api.aircall.io/v1/numbers
```

Look for your number in the response and note the `id` field.

## 2. Configure Number for Public API Messaging

**This is a one-time setup step.** Before you can send SMS via the API, you must register the number for "Public Api" messaging mode.

### Configure

```bash
curl -X POST \
  -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID/messages/configuration
```

Expected response (200):
```json
{
  "token": "b6c705f4-...",
  "type": "Public Api"
}
```

**Save the `token` value** — this is your new webhook token. Update `backend/.env`:

```env
AIRCALL_WEBHOOK_TOKEN=b6c705f4-...
```

### Verify Configuration

```bash
curl -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID/messages/configuration
```

Expected response:
```json
{
  "token": "b6c705f4-...",
  "callbackUrl": null,
  "type": "Public Api"
}
```

### Remove Configuration (if needed)

```bash
curl -X DELETE \
  -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID/messages/configuration
```

This reverts the number back to native mode.

## 3. Set Up Inbound Webhook

Aircall sends a POST request to your webhook URL when an SMS is received. The webhook URL must be publicly accessible.

### For Local Development

Use a Cloudflare Tunnel (or ngrok):

```bash
cloudflared tunnel --url http://localhost:8000
```

This gives you a URL like `https://randomly-named.trycloudflare.com`.

### Register the Webhook

In the Aircall Dashboard:
1. Go to **Integrations** > **Webhooks**
2. Add a webhook URL: `https://your-domain.com/api/sms/buyer/webhook`
3. Select events: `message.received`, `message.sent`, `message.status_updated`
4. Note the **Token** shown on the webhook settings page

### When You Change Your Tunnel URL

Every time you get a new Cloudflare Tunnel URL:
1. Go to Aircall Dashboard > **Integrations** > **Webhooks** > your webhook
2. Update the **URL** field to `https://NEW-TUNNEL.trycloudflare.com/api/sms/buyer/webhook`
3. Save. The token stays the same — no `.env` change needed.
4. Restart your backend (settings are cached by `@lru_cache`).

### Webhook Token Validation

Our webhook handler validates the token sent by Aircall in each request. The token comes from either:
- The `x-aircall-token` header, or
- The `token` field in the JSON body

This must match `AIRCALL_WEBHOOK_TOKEN` in your `.env`.

### Two Different Tokens (Don't Confuse Them)

| Token | Source | Purpose |
|-------|--------|---------|
| **Dashboard webhook token** | Aircall Dashboard > Webhooks page | Sent in every webhook POST payload. Must match `AIRCALL_WEBHOOK_TOKEN` in `.env` |
| **API config token** | Response from `POST /messages/configuration` | Used internally by Aircall for the send API. You don't need to store this |

The dashboard webhook token is stable — it doesn't change when you update the webhook URL. The API config token only changes if you DELETE and re-POST the `/messages/configuration`.

## 4. API Endpoints Reference

### Sending SMS

**Endpoint:** `POST /v1/numbers/{number_id}/messages/send`

**Auth:** Basic Auth (`API_ID:API_TOKEN` base64-encoded)

**Request:**
```json
{
  "to": "+11234567890",
  "body": "Your message text here"
}
```

**Response (200):**
```json
{
  "id": "abcdSMc6Dc8ea2bc71ab19102c3de4f60ba18aa",
  "status": "pending",
  "direction": "outbound",
  "body": "Your message text here",
  "raw_digits": "11234567890",
  "number": {
    "id": 476258,
    "digits": "+1 424-416-2288"
  }
}
```

**Common errors:**

| Status | Key | Meaning |
|--------|-----|---------|
| 400 | `InvalidPayload` | Invalid phone number in `to` field |
| 400 | `SameDestinationAsSender` | Cannot send SMS to your own Aircall number |
| 403 | `LineIsNotNativeException` | Number not configured for API messaging (run Step 2) |
| 403 | `Forbidden` | Invalid API credentials |
| 401 | `Unauthorized` | Missing or bad auth header |

### Receiving SMS (Webhook Payload)

Aircall sends a POST to your webhook URL:

```json
{
  "resource": "message",
  "event": "message.received",
  "timestamp": 1722604989549,
  "token": "your-webhook-token",
  "data": {
    "id": "abdcSM11da5...",
    "status": "received",
    "direction": "inbound",
    "body": "The SMS text from the sender",
    "raw_digits": "18704575426",
    "number": {
      "id": 476258,
      "digits": "+1 424-416-2288"
    }
  }
}
```

### Important: Native vs Public Api Mode

Aircall has two messaging modes per number:

| Mode | Send Endpoint | How to Enable |
|------|--------------|---------------|
| **Native** | `/messages/native/send` | Default (Aircall app sends) |
| **Public Api** | `/messages/send` | After `POST /messages/configuration` |

Once you run the configuration endpoint, the number switches to **Public Api** mode. The `/messages/native/send` endpoint will return 403 `LineIsNotNativeException`. Use `/messages/send` instead.

To switch back to native mode, DELETE the configuration (see Step 2).

## 5. Testing the Setup

### Verify Credentials

```bash
curl -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" https://api.aircall.io/v1/company
```

Should return 200 with your company name.

### Verify Number Exists

```bash
curl -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID
```

### Test Send SMS

```bash
curl -X POST \
  -u "$AIRCALL_API_ID:$AIRCALL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1YOUR_PHONE", "body": "WEx test message"}' \
  https://api.aircall.io/v1/numbers/$AIRCALL_NUMBER_ID/messages/send
```

### Test Inbound Webhook (simulate locally)

```bash
curl -X POST http://localhost:8000/api/sms/buyer/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event": "message.received",
    "token": "YOUR_WEBHOOK_TOKEN",
    "data": {
      "direction": "inbound",
      "body": "I need 10k sqft in Carson CA for storage",
      "raw_digits": "+11234567890",
      "number": {"digits": "+14244162288"}
    }
  }'
```

## 6. Environment Variables Summary

| Variable | Description | Example |
|----------|-------------|---------|
| `AIRCALL_API_ID` | API credentials (ID) | `c0a290ce...` |
| `AIRCALL_API_TOKEN` | API credentials (token) | `a1224775...` |
| `AIRCALL_NUMBER_ID` | Supplier Aircall number ID | `476258` |
| `AIRCALL_BUYER_NUMBER_ID` | Buyer Aircall number ID | `476258` |
| `AIRCALL_WEBHOOK_TOKEN` | Token from `/messages/configuration` | `b6c705f4-...` |

## 7. Troubleshooting

**401 Unauthorized on webhook:**
- The webhook token changed. Re-run `GET /messages/configuration` to see the current token. Update `.env` and restart backend.

**403 on sending (`LineIsNotNativeException`):**
- Number is in native mode but you're calling `/messages/send`, or vice versa. Check config mode with `GET /messages/configuration` and use the matching endpoint.

**403 on sending (`Forbidden`):**
- API credentials are wrong or the Aircall plan doesn't include API messaging. Verify with `GET /v1/company`.

**Aircall webhook disabled (50 retries failed):**
- Aircall auto-disables webhooks after 50 failed deliveries. Check the Aircall Dashboard for alerts. Fix the endpoint, and Aircall will retry failed events for 12 hours. Once a success is received, the webhook re-enables automatically.

**Aircall webhook timeout (5 seconds):**
- Aircall times out after 5 seconds. Our webhook returns 200 immediately and processes the LLM pipeline in a background task. If you see "context canceled" errors, ensure the background processing pattern is in place (see `buyer_sms.py`).

**Messages not appearing in Aircall Dashboard:**
- Expected behavior. Messages sent via the Public API are NOT recorded in the Aircall platform UI. Use your own logging/DB to track messages.

**`@lru_cache` on settings:**
- Config changes in `.env` require a backend restart. The `get_settings()` function caches on first call.
