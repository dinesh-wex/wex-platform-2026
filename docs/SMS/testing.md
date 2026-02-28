# SMS Testing Guide

## Clear SMS Data Before Testing

The SMS pipeline stores conversation state, buyer needs, and search sessions per phone number.
When re-testing from scratch, clear the old data first so stale criteria don't carry over.

### From PowerShell (with conda env already active)

```powershell
# Clear data for a specific phone number
python backend/clear_sms_data.py --phone "+1 415 766 1133"

# Clear ALL SMS data
python backend/clear_sms_data.py
```

### From any terminal (without conda activated)

```bash
conda run -n wex python backend/clear_sms_data.py --phone "+1 415 766 1133"
conda run -n wex python backend/clear_sms_data.py
```

### What gets deleted

| Table | `--phone` | no flag | Description |
|-------|-----------|---------|-------------|
| `escalation_threads` | yes | yes | Property question escalations to ops |
| `sms_signup_tokens` | no | yes | Guarantee signing tokens |
| `sms_conversation_states` | yes | yes | Phase, turn, criteria snapshot, presented matches |
| `search_sessions` | yes | **no** | Shared with web — only deleted per-phone |
| `buyer_conversations` | yes | yes | Message history |
| `buyer_needs` | yes | yes | Extracted search criteria (city, sqft, use_type, etc.) |
| `buyers` | yes | yes | Buyer record (phone, name, email) |

With `--phone`, only data linked to that buyer is deleted (including their search sessions).
Without it, SMS-only tables are wiped but `search_sessions` is left alone since it's shared with web.
