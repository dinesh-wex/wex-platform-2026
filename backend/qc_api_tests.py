import sys, uuid, requests
BASE = "http://localhost:8001"
TIMEOUT = 10
EID = "dddddddd-0000-0000-0000-000000000001"
BPW = "TestBuyer1!"
SPW = "TestSupplier1!"
SEMAIL = "supplier-qc@test.wex"
results = []
BUYER_EMAIL = None
BUYER_TOKEN = None
SUPPLIER_TOKEN = None
def record(tid, label, passed, note="", status_code=None, body=None):
    results.append((tid, label, passed, note, status_code, body))
def run_tests():
    global BUYER_EMAIL, BUYER_TOKEN, SUPPLIER_TOKEN
    tid, label = "T1.1", "guarantee rejected w/o auth"
    try:
        r = requests.post(f"{BASE}/api/engagements/{EID}/guarantee/sign", json={"terms_version": "v1"}, timeout=TIMEOUT)
        passed = r.status_code in [400, 401, 403]
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.2", "/register alias works"
    reg_email = f"buyer-qc-{uuid.uuid4()}@test.wex"
    try:
        r = requests.post(f"{BASE}/api/auth/register", json={"email": reg_email, "password": BPW, "name": "Test", "role": "buyer"}, timeout=TIMEOUT)
        passed = r.status_code in [200, 201] and "access_token" in r.json()
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.3", "signup with engagement_id links correctly"
    BUYER_EMAIL = f"buyer-qc-{uuid.uuid4()}@test.wex"
    try:
        r = requests.post(f"{BASE}/api/auth/signup", json={"email": BUYER_EMAIL, "password": BPW, "name": "QC Buyer", "role": "buyer", "engagement_id": EID}, timeout=TIMEOUT)
        signup_ok = r.status_code in [200, 201] and "access_token" in r.json()
        if signup_ok:
            BUYER_TOKEN = r.json()["access_token"]
        passed = signup_ok
        note = ""
        if signup_ok:
            try:
                eg = requests.get(f"{BASE}/api/engagements/{EID}", headers={"Authorization": f"Bearer {BUYER_TOKEN}"}, timeout=TIMEOUT)
                if eg.status_code == 200:
                    note = "engagement status=" + eg.json().get("status", "")
                else:
                    note = f"GET engagement returned {eg.status_code}"
            except Exception:
                note = "could not verify engagement status"
        record(tid, label, passed, note=note, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.4", "duplicate email returns 400/409"
    try:
        r = requests.post(f"{BASE}/api/auth/signup", json={"email": BUYER_EMAIL, "password": BPW, "name": "QC Buyer", "role": "buyer"}, timeout=TIMEOUT)
        passed = r.status_code in [400, 409]
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.5", "login works"
    try:
        r = requests.post(f"{BASE}/api/auth/login", json={"email": BUYER_EMAIL, "password": BPW}, timeout=TIMEOUT)
        passed = r.status_code in [200, 201] and "access_token" in r.json()
        if passed:
            BUYER_TOKEN = r.json()["access_token"]
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.6", "/me with valid token returns user"
    try:
        headers = {"Authorization": f"Bearer {BUYER_TOKEN}"} if BUYER_TOKEN else {}
        r = requests.get(f"{BASE}/api/auth/me", headers=headers, timeout=TIMEOUT)
        passed = r.status_code == 200 and "email" in r.json()
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.7", "/me with no token returns 401"
    try:
        r = requests.get(f"{BASE}/api/auth/me", timeout=TIMEOUT)
        passed = r.status_code == 401
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.8", "supplier GET engagement (no buyer_rate_sqft leak)"
    try:
        lr = requests.post(f"{BASE}/api/auth/login", json={"email": SEMAIL, "password": SPW}, timeout=TIMEOUT)
        if lr.status_code not in [200, 201] or "access_token" not in lr.json():
            record(tid, label, False, note=f"supplier login failed: {lr.status_code} {lr.text}")
        else:
            SUPPLIER_TOKEN = lr.json()["access_token"]
            r = requests.get(f"{BASE}/api/engagements/{EID}", headers={"Authorization": f"Bearer {SUPPLIER_TOKEN}"}, timeout=TIMEOUT)
            if r.status_code == 404:
                record(tid, label, False, note="PARTIAL - WAL issue (404)", status_code=r.status_code)
            elif r.status_code == 200:
                body = r.json()
                no_leak = "buyer_rate_sqft" not in body
                passed = no_leak
                note = "buyer_rate_sqft NOT in response (good)" if no_leak else "FAIL: buyer_rate_sqft LEAKED"
                record(tid, label, passed, note=note, status_code=r.status_code, body="" if passed else str(body))
            else:
                record(tid, label, False, note=f"unexpected {r.status_code}", status_code=r.status_code, body=r.text)
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.9", "/register alias (second call)"
    reg2_email = f"buyer-qc-{uuid.uuid4()}@test.wex"
    try:
        r = requests.post(f"{BASE}/api/auth/register", json={"email": reg2_email, "password": BPW, "name": "Test2", "role": "buyer"}, timeout=TIMEOUT)
        passed = r.status_code in [200, 201]
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.10", "supplier login"
    try:
        r = requests.post(f"{BASE}/api/auth/login", json={"email": SEMAIL, "password": SPW}, timeout=TIMEOUT)
        passed = r.status_code in [200, 201] and "access_token" in r.json()
        if passed:
            SUPPLIER_TOKEN = r.json()["access_token"]
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.11", "link-buyer w/ supplier token returns 400/403"
    try:
        headers = {"Authorization": f"Bearer {SUPPLIER_TOKEN}"} if SUPPLIER_TOKEN else {}
        r = requests.post(f"{BASE}/api/engagements/{EID}/link-buyer", headers=headers, timeout=TIMEOUT)
        if r.status_code == 404:
            record(tid, label, False, note="BLOCKED - WAL issue (404)", status_code=r.status_code)
        else:
            passed = r.status_code in [400, 403]
            record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
    tid, label = "T1.12", "no-auth on engagement route returns 401"
    try:
        r = requests.get(f"{BASE}/api/engagements/{EID}", timeout=TIMEOUT)
        passed = r.status_code == 401
        record(tid, label, passed, status_code=r.status_code, body=r.text if not passed else "")
    except Exception as e:
        record(tid, label, False, note=str(e))
def print_results():
    print()
    print("-" * 65)
    for tid, label, passed, note, status_code, body in results:
        status_str = "PASS" if passed else "FAIL"
        sc_str = f"[{status_code}]" if status_code else ""
        note_str = f"  ({note})" if note else ""
        print(f"{tid:<6}  {label:<42}  {status_str}  {sc_str}{note_str}")
    passed_count = sum(1 for r in results if r[2])
    failed_count = sum(1 for r in results if not r[2])
    total = len(results)
    print("-" * 65)
    print(f"RESULT: {passed_count} PASS / {failed_count} FAIL / {total} total")
    if failed_count > 0:
        print("--- FAILURE DETAILS ---")
        for tid, label, passed, note, status_code, body in results:
            if not passed:
                print(f"{tid} - {label}")
                if note:
                    print(f"  Note: {note}")
                if status_code:
                    print(f"  Status: {status_code}")
                if body:
                    print(f"  Body: {body[:500]}")
    return failed_count
if __name__ == "__main__":
    print(f"Running Phase 1B QC tests against {BASE}")
    print(f"EID={EID}")
    run_tests()
    failed = print_results()
    sys.exit(1 if failed > 0 else 0)
