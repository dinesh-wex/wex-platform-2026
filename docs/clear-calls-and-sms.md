# Clear Calls & SMS — Quick Reference

All commands run from the `backend/` folder.

---

## Clear SMS Data (Database)

### Clear ALL buyers & SMS history
```bash
conda run -n wex python clear_sms_data.py
```

### Clear one phone number only
```bash
conda run -n wex python clear_sms_data.py --phone "+14155551234"
```

Tables cleared (in order): `escalation_threads`, `sms_signup_tokens`, `sms_conversation_states`, `search_sessions`, `buyer_conversations`, `buyer_needs`, `buyers`

---

## Fix Vapi Phone Number (if calls stop working)

If the phone number loses its assistant link (calls go silent or say "set assistant"):
```bash
python relink_assistant.py
```
Re-links `+14242873916` → assistant `ee1c27db` (Jess - WEx Warehouse Broker)

---

## Check Vapi Call Logs
```bash
powershell -ExecutionPolicy Bypass -File check_vapi_calls.ps1
```
Shows last 10 calls with status, ended reason, and transcript preview.

---

## Check Current Phone + Voice Config
```bash
python check_phone_voice.py
```
Shows what assistant, voice provider/ID, and model are currently active on the phone number.

---

## Update Vapi Assistant (model/tools/system prompt)
```bash
python update_assistant_full.py
```
Pushes the full config (Groq llama-3.1-8b-instant + OpenAI nova voice + all 5 tools + system prompt).

> **Tip:** To just change the voice, do it directly in the [Vapi dashboard](https://dashboard.vapi.ai) under the assistant's **Voice** tab → select provider + voice → **Publish**. No script needed.

---

## Key IDs
| Item | Value |
|---|---|
| Phone number | `+14242873916` |
| Phone number ID | `bb4c3eb8-863e-4ca0-b5be-02b65556d94d` |
| Assistant ID (Jess) | `ee1c27db-c3a5-49cc-8e36-12a1c644b482` |
| Vapi API Key | `b38df737-1dfd-46c1-aa31-6ff586b4cff3` |
| GCP Project | `wex-platform-2026` |
| Backend Cloud Run URL | `https://wex-backend-449870075865.us-west1.run.app` |
