"""Simulate the live demo flow end-to-end to verify everything works."""
import json, uuid, urllib.request, urllib.error, time, sys

def safe_print(text):
    if text is None:
        return
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))

BASE = "http://127.0.0.1:18081"
APP  = "app"
USER = "demo-user"
session_id = str(uuid.uuid4())

# Create session
url = f"{BASE}/apps/{APP}/users/{USER}/sessions/{session_id}"
req = urllib.request.Request(url, method="POST",
                             headers={"Content-Type": "application/json"},
                             data=b"{}")
with urllib.request.urlopen(req, timeout=5) as r:
    safe_print(f"Session created: {r.status}")

# Send Demo query
url = f"{BASE}/run_sse"
payload = json.dumps({
    "app_name": APP,
    "user_id": USER,
    "session_id": session_id,
    "new_message": {
        "role": "user",
        "parts": [{"text": "Organize a dinner for 10 guests. We want Italian cuisine at the Community Center. John paid $250 for the venue, and Mary paid $100 for decorations. Split the costs."}]
    },
    "streaming": False
}).encode()

req = urllib.request.Request(url, method="POST",
                             headers={"Content-Type": "application/json"},
                             data=payload)

safe_print("\n--- STEP 1: SEND DEMO PROMPT ---")
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        for raw_line in r:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                event = json.loads(data_str)
                content = event.get("content", {})
                if isinstance(content, dict):
                    for part in content.get("parts", []):
                        if isinstance(part, dict) and "text" in part:
                            safe_print(part["text"])
except urllib.error.HTTPError as e:
    safe_print(f"HTTP Error: {e.read().decode()}")
except Exception as e:
    safe_print(f"Error: {e}")

# Fetch session details to find interrupt ID
safe_print("\nChecking session status for interrupt...")
time.sleep(2)
url = f"{BASE}/apps/{APP}/users/{USER}/sessions/{session_id}"
req = urllib.request.Request(url, method="GET")
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        session_data = json.loads(r.read().decode())
        # Let's see if there is a pending interrupt
        # Print session state safely
        state_str = json.dumps(session_data.get("state", {}), indent=2)
        safe_print("Session State:")
        safe_print(state_str)
except Exception as e:
    safe_print(f"Failed to get session: {e}")

# Send "Yes" approval input
url = f"{BASE}/run_sse"
payload = json.dumps({
    "app_name": APP,
    "user_id": USER,
    "session_id": session_id,
    "new_message": {
        "role": "user",
        "parts": [{
            "function_response": {
                "name": "adk_request_input",
                "id": "approve_event_plan",
                "response": {"response": "Yes"}
            }
        }]
    },
    "streaming": False
}).encode()

req = urllib.request.Request(url, method="POST",
                             headers={"Content-Type": "application/json"},
                             data=payload)

safe_print("\n--- STEP 2: SEND 'YES' APPROVAL ---")
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        for raw_line in r:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                event = json.loads(data_str)
                safe_print(f"EVENT RECEIVED: {list(event.keys())}")
                safe_print(json.dumps(event, indent=2))
except Exception as e:
    safe_print(f"Approval failed: {e}")
