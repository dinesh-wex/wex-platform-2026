"""Push the full system prompt and correct config to the static Vapi assistant."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import requests
from wex_platform.services.vapi_assistant_config import _build_system_prompt, _build_tool_definitions

VAPI_API_KEY = "b38df737-1dfd-46c1-aa31-6ff586b4cff3"
ASSISTANT_ID = "ee1c27db-c3a5-49cc-8e36-12a1c644b482"
WEBHOOK_URL = "https://wex-backend-449870075865.us-west1.run.app/api/voice/webhook"

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

system_prompt = _build_system_prompt(sms_context=None)
print(f"System prompt: {len(system_prompt)} chars")

tools = _build_tool_definitions()
print(f"Tools: {[t['function']['name'] for t in tools]}")

payload = {
    "name": "Robin - WEx Warehouse Broker",
    "model": {
        "provider": "google",
        "model": "gemini-3-flash-preview",
        "messages": [
            {"role": "system", "content": system_prompt}
        ],
        "tools": tools,
        "temperature": 0.7,
    },
    "voice": {
        "provider": "11labs",
        "voiceId": "jBzLvP03992lMFEkj2kJ",
    },
    "firstMessage": "Hey, thanks for calling Warehouse Exchange, this is Robin. Who am I speaking with?",
    "server": {
        "url": WEBHOOK_URL,
    },
    "endCallFunctionEnabled": True,
    "recordingEnabled": True,
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 600,
}

resp = requests.patch(
    f"https://api.vapi.ai/assistant/{ASSISTANT_ID}",
    json=payload,
    headers=headers,
    timeout=30,
)

if resp.status_code == 200:
    d = resp.json()
    msgs = d.get("model", {}).get("messages", [])
    sys_content = next((m.get("content", "") for m in msgs if m.get("role") == "system"), "")
    print(f"\nDone!")
    print(f"  Model: {d.get('model', {}).get('provider')} / {d.get('model', {}).get('model')}")
    print(f"  Voice: {d.get('voice', {}).get('provider')} / {d.get('voice', {}).get('voiceId')}")
    print(f"  System prompt on Vapi: {len(sys_content)} chars")
    print(f"  Tools: {[t['function']['name'] for t in d.get('model', {}).get('tools', [])]}")
else:
    print(f"ERROR {resp.status_code}: {resp.text}")
