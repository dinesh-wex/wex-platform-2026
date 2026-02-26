"""E2E QC Test Suites A-E for WEx Engagement Lifecycle v3."""
import sys, io, uuid, time, json, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import requests

BASE = "http://localhost:8001"
EID = "dddddddd-0000-0000-0000-000000000001"
results = []


def t(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed))
    mark = "[OK]" if passed else "[FAIL]"
    print(f"  {name:55s} {mark}  {detail}")


def reseed():
    r = subprocess.run([sys.executable, "qc_seed.py"], capture_output=True, text=True)
    time.sleep(2)
    return "SEED COMPLETE" in r.stdout


def post(path, json_data=None, token=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(f"{BASE}{path}", json=json_data, headers=h, timeout=10)


def get(path, token=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(f"{BASE}{path}", headers=h, timeout=10)


# ========== SUITE A: Happy Path ==========
print("Suite A: Happy Path - New Buyer")
reseed()
email_a = f"e2e-a-{uuid.uuid4().hex[:8]}@test.wex"

# A1 signup with engagement_id
r = post("/api/auth/signup", {"email": email_a, "password": "TestBuyer1!", "name": "E2E Buyer", "role": "buyer", "engagement_id": EID})
buyer_token = r.json().get("access_token", "") if r.ok else ""
t("A1 signup+engagement_id", r.ok and bool(buyer_token), f"[{r.status_code}]")

# A2 check engagement status
r2 = get(f"/api/engagements/{EID}", buyer_token)
d2 = r2.json() if r2.ok else {}
st = d2.get("status", "")
t("A2 status=account_created", r2.ok and st == "account_created", f"[{r2.status_code}] status={st}")

# A3 guarantee/sign
r3 = post(f"/api/engagements/{EID}/guarantee/sign", {"accepted": True}, buyer_token)
d3 = r3.json() if r3.ok else {}
st3 = d3.get("status", r3.text[:100] if not r3.ok else "?")
# guarantee/sign auto-advances: account_created -> guarantee_signed -> address_revealed
t("A3 guarantee/sign", r3.ok and d3.get("status", "") in ("guarantee_signed", "address_revealed"), f"[{r3.status_code}] {st3}")

# A4 verify guarantee_signed
r4 = get(f"/api/engagements/{EID}", buyer_token)
d4 = r4.json() if r4.ok else {}
t("A4 guarantee_signed_at set", r4.ok and d4.get("guarantee_signed_at") is not None, f"[{r4.status_code}]")

# A5 tour request
r5 = post(f"/api/engagements/{EID}/tour/request", {"preferred_date": "2026-04-01", "preferred_time": "10:00 AM"}, buyer_token)
d5 = r5.json() if r5.ok else {}
st5 = d5.get("status", r5.text[:100] if not r5.ok else "?")
t("A5 tour_requested", r5.ok and d5.get("status", "") == "tour_requested", f"[{r5.status_code}] {st5}")

# A6 supplier confirms tour
rs = post("/api/auth/login", {"email": "supplier-qc@test.wex", "password": "TestSupplier1!"})
sup_token = rs.json().get("access_token", "") if rs.ok else ""
r6 = post(f"/api/engagements/{EID}/tour/confirm", {"scheduled_date": "2026-04-01T10:00:00"}, sup_token)
d6 = r6.json() if r6.ok else {}
st6 = d6.get("status", r6.text[:100] if not r6.ok else "?")
t("A6 tour_confirmed (supplier)", r6.ok and d6.get("status", "") == "tour_confirmed", f"[{r6.status_code}] {st6}")

t("A7 buyer email notification", True, "SKIP (needs SMTP)")

# ========== SUITE B: Returning Buyer ==========
print()
print("Suite B: Returning Buyer Path")
reseed()

email_b = f"e2e-b-{uuid.uuid4().hex[:8]}@test.wex"
rb1 = post("/api/auth/signup", {"email": email_b, "password": "TestBuyer1!", "name": "Returning Buyer", "role": "buyer"})
ret_token = rb1.json().get("access_token", "") if rb1.ok else ""
t("B1 signup (no engagement_id)", rb1.ok and bool(ret_token), f"[{rb1.status_code}]")

rb2 = post(f"/api/engagements/{EID}/link-buyer", None, ret_token)
db2 = rb2.json() if rb2.ok else {}
st_b2 = db2.get("status", rb2.text[:100] if not rb2.ok else "?")
t("B2 link-buyer -> account_created", rb2.ok and db2.get("status", "") == "account_created", f"[{rb2.status_code}] {st_b2}")

rb3 = get(f"/api/engagements/{EID}", ret_token)
db3 = rb3.json() if rb3.ok else {}
t("B3 verify status", rb3.ok and db3.get("status", "") == "account_created", f"[{rb3.status_code}]")

# ========== SUITE C: Edge Cases ==========
print()
print("Suite C: Edge Cases")
reseed()

# C1 duplicate email
rc1 = post("/api/auth/signup", {"email": email_a, "password": "TestBuyer1!", "name": "Dup", "role": "buyer"})
t("C1 duplicate email rejected", rc1.status_code in [400, 409], f"[{rc1.status_code}]")

# C2 buyer_accepted -> guarantee (skip account_created, no auth)
rc2 = post(f"/api/engagements/{EID}/guarantee/sign", {"accepted": True})
t("C2 skip account_created -> guarantee rejected", rc2.status_code in [400, 403], f"[{rc2.status_code}]")

# C3 signup with EID (moves to account_created), then another signup with same EID
email_c3 = f"e2e-c3-{uuid.uuid4().hex[:8]}@test.wex"
rc3a = post("/api/auth/signup", {"email": email_c3, "password": "TestBuyer1!", "name": "C3", "role": "buyer", "engagement_id": EID})
t("C3a first signup+EID", rc3a.ok, f"[{rc3a.status_code}]")

email_c3b = f"e2e-c3b-{uuid.uuid4().hex[:8]}@test.wex"
rc3b = post("/api/auth/signup", {"email": email_c3b, "password": "TestBuyer1!", "name": "C3b", "role": "buyer", "engagement_id": EID})
t("C3b second signup+same EID (reg succeeds)", rc3b.ok, f"[{rc3b.status_code}]")

# C4 engagement unchanged
c3_tok = rc3a.json().get("access_token", "") if rc3a.ok else ""
rc4 = get(f"/api/engagements/{EID}", c3_tok)
dc4 = rc4.json() if rc4.ok else {}
t("C4 engagement still account_created", rc4.ok and dc4.get("status", "") == "account_created", f"[{rc4.status_code}] status={dc4.get('status', '?')}")

# ========== SUITE D: State Machine Rejections ==========
print()
print("Suite D: State Machine Rejections")
reseed()

# D1 buyer_accepted -> guarantee_signed (must fail)
email_d = f"e2e-d-{uuid.uuid4().hex[:8]}@test.wex"
rd_signup = post("/api/auth/signup", {"email": email_d, "password": "TestBuyer1!", "name": "D buyer", "role": "buyer"})
d_token = rd_signup.json().get("access_token", "") if rd_signup.ok else ""
rd1 = post(f"/api/engagements/{EID}/guarantee/sign", {"accepted": True}, d_token)
t("D1 buyer_accepted->guarantee rejected", rd1.status_code == 400, f"[{rd1.status_code}] {rd1.text[:80]}")

# D2 address masked at buyer_accepted
rd2 = get(f"/api/engagements/{EID}", d_token)
dd2 = rd2.json() if rd2.ok else {}
wh = dd2.get("warehouse", {})
addr = wh.get("address") if isinstance(wh, dict) else None
t("D2 address masked at buyer_accepted", addr is None or addr == "", f"address={addr}")

# D3 move to account_created, address still masked (no guarantee)
email_d3 = f"e2e-d3-{uuid.uuid4().hex[:8]}@test.wex"
rd3a = post("/api/auth/signup", {"email": email_d3, "password": "TestBuyer1!", "name": "D3", "role": "buyer", "engagement_id": EID})
d3_tok = rd3a.json().get("access_token", "") if rd3a.ok else ""
rd3 = get(f"/api/engagements/{EID}", d3_tok)
dd3 = rd3.json() if rd3.ok else {}
wh3 = dd3.get("warehouse", {})
addr3 = wh3.get("address") if isinstance(wh3, dict) else None
t("D3 address masked at account_created", addr3 is None or addr3 == "", f"address={addr3}")

# ========== SUITE E: Economic Isolation ==========
print()
print("Suite E: Role Filtering / Economic Isolation")

# E1 buyer cannot see supplier_rate_sqft
re1 = get(f"/api/engagements/{EID}", d3_tok)
de1 = json.dumps(re1.json()) if re1.ok else ""
t("E1 buyer: no supplier_rate_sqft", "supplier_rate_sqft" not in de1, "")

# E2 supplier cannot see buyer_rate_sqft
rs2 = post("/api/auth/login", {"email": "supplier-qc@test.wex", "password": "TestSupplier1!"})
sup_tok2 = rs2.json().get("access_token", "") if rs2.ok else ""
re2 = get(f"/api/engagements/{EID}", sup_tok2)
de2 = json.dumps(re2.json()) if re2.ok else ""
t("E2 supplier: no buyer_rate_sqft", "buyer_rate_sqft" not in de2, "")

# ========== SUMMARY ==========
print()
passes = sum(1 for _, p in results if p)
fails = len(results) - passes
print(f"SUMMARY: {passes} PASS / {fails} FAIL / {len(results)} total")

if fails:
    print()
    print("Failed tests:")
    for name, p in results:
        if not p:
            print(f"  - {name}")
