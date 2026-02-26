# Buyer Account Creation Flow — Implementation Plan

**Version:** 1.0 · **Date:** February 2026  
**Spec Reference:** WEx-Engagement-Lifecycle-Spec-v3.md  
**Scope:** Replace contact capture step with account creation in the buyer commitment flow. Covers backend, frontend, and database migration.

---

## What Changed (Summary)

The buyer commitment flow previously had a lightweight contact capture step (email + phone only) before the WEx Guarantee. This is replaced by full account creation. A buyer must create a verified account before the guarantee is presented. The property address remains gated behind the guarantee — the overall protection model is strengthened, not weakened.

**Old flow:** buyer_accepted → contact_captured → guarantee_signed → address_revealed  
**New flow:** buyer_accepted → account_created → guarantee_signed → address_revealed

---

## Phase 0 — Database Migration

Run before any backend or frontend code changes.

**0A. Update EngagementStatus enum**

```sql
-- Remove contact_captured, add account_created
ALTER TYPE engagementstatus RENAME VALUE 'contact_captured' TO 'account_created';
```

If direct rename is not supported (depends on Postgres version), use the safe migration path:
```sql
ALTER TYPE engagementstatus ADD VALUE 'account_created';
-- Deploy backend changes
-- Then remove old value once no rows reference it
```

**0B. Update Engagement table columns**

```sql
-- Remove contact capture fields
ALTER TABLE engagements DROP COLUMN IF EXISTS buyer_email;
ALTER TABLE engagements DROP COLUMN IF EXISTS buyer_phone;
ALTER TABLE engagements DROP COLUMN IF EXISTS contact_captured_at;

-- Add account creation timestamp
ALTER TABLE engagements ADD COLUMN account_created_at TIMESTAMP NULL;
```

**0C. Migrate existing data**

```sql
-- Any existing contact_captured rows become account_created
UPDATE engagements 
SET status = 'account_created', 
    account_created_at = status_changed_at
WHERE status = 'contact_captured';
```

**0D. Write Alembic migration**

Wrap all of the above in a single Alembic revision file. Migration must be reversible — include `downgrade()` that restores the old columns and enum value.

---

## Phase 1 — Backend

**1A. Enums**  
File: `backend/src/wex_platform/domain/enums.py`

```python
# Remove:
contact_captured = "contact_captured"

# Add:
account_created = "account_created"
```

**1B. Engagement Model**  
File: `backend/src/wex_platform/domain/models.py`

```python
# Remove these three columns:
buyer_email = Column(String, nullable=True)
buyer_phone = Column(String, nullable=True)
contact_captured_at = Column(DateTime, nullable=True)

# Add:
account_created_at = Column(DateTime, nullable=True)

# Update buyer_id comment:
buyer_id = Column(UUID, ForeignKey("users.id"), nullable=True)
# buyer_id is null from deal_ping_sent through buyer_accepted.
# Populated at account_created when buyer creates verified account.
# buyer_need_id is the anonymous link until buyer_id is set.
# DO NOT use buyer_id for access control before account_created state.
```

**1C. State Machine**  
File: `backend/src/wex_platform/services/engagement_state_machine.py`

Remove:
```python
(EngagementStatus.buyer_accepted, EngagementStatus.contact_captured, EngagementActor.buyer),
(EngagementStatus.contact_captured, EngagementStatus.guarantee_signed, EngagementActor.buyer),
```

Add:
```python
(EngagementStatus.buyer_accepted, EngagementStatus.account_created, EngagementActor.buyer),
(EngagementStatus.account_created, EngagementStatus.guarantee_signed, EngagementActor.buyer),
```

Update `DEADLINE_FIELDS`:
```python
# Remove:
EngagementStatus.contact_captured: None,

# Add:
EngagementStatus.account_created: None,  # No deadline — form stays open
```

Update unit tests: replace all `contact_captured` transition tests with `account_created`. Add new rejection test: `buyer_accepted → guarantee_signed` (skipping account_created) must be rejected.

**1D. Remove /contact Endpoint, Add /link-buyer**  
File: `backend/src/wex_platform/app/routes/engagement.py`

Remove:
```python
@router.post("/{id}/contact")
async def capture_contact(...):
    ...
```

Add:
```python
@router.post("/{id}/link-buyer")
async def link_buyer(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Links an authenticated buyer to an in-progress engagement.
    Called after login when a returning buyer accepts a match.
    Transitions: buyer_accepted → account_created
    Sets engagement.buyer_id = current_user.id
    """
    engagement = get_engagement_or_404(id, db)
    
    EngagementStateMachine.validate_transition(
        engagement.status,
        EngagementStatus.account_created,
        EngagementActor.buyer,
        engagement
    )
    
    engagement.buyer_id = current_user.id
    engagement.account_created_at = datetime.utcnow()
    engagement.status = EngagementStatus.account_created
    
    log_event(engagement, EngagementEventType.account_created, actor=EngagementActor.buyer, data={
        "method": "login",
        "user_id": str(current_user.id)
    })
    
    db.commit()
    return serialize_engagement(engagement, role="buyer")
```

**1E. Auth Router — Accept engagement_id at Registration**  
File: `backend/src/wex_platform/app/routes/auth.py`

Update the register endpoint to accept an optional `engagement_id`. If provided, link the new user to the engagement within the same transaction.

```python
class RegisterRequest(BaseModel):
    email: str
    password: str
    phone: Optional[str] = None
    engagement_id: Optional[uuid.UUID] = None  # links to in-progress engagement

@router.post("/register")
async def register(body: RegisterRequest, db: Session = Depends(get_db)):
    # 1. Create user record (existing logic)
    user = create_user(body.email, body.password, body.phone, db)
    
    # 2. If engagement_id provided, link within same transaction
    if body.engagement_id:
        engagement = db.query(Engagement).filter(
            Engagement.id == body.engagement_id,
            Engagement.status == EngagementStatus.buyer_accepted
        ).first()
        
        if engagement:
            EngagementStateMachine.validate_transition(
                engagement.status,
                EngagementStatus.account_created,
                EngagementActor.buyer,
                engagement
            )
            engagement.buyer_id = user.id
            engagement.account_created_at = datetime.utcnow()
            engagement.status = EngagementStatus.account_created
            log_event(engagement, EngagementEventType.account_created, 
                      actor=EngagementActor.buyer,
                      data={"method": "registration", "user_id": str(user.id)})
    
    db.commit()
    
    # 3. Return token + engagement context
    token = create_auth_token(user)
    return {
        "user": UserResponse.from_orm(user),
        "token": token,
        "engagement_id": str(body.engagement_id) if body.engagement_id else None
    }
```

**1F. Role-Filtered Serializer — Remove buyer_email/buyer_phone**  
File: `backend/src/wex_platform/app/schemas/engagement.py`

Remove `buyer_email` and `buyer_phone` from all three response schemas (EngagementBuyerView, EngagementSupplierView, EngagementAdminView). Add `account_created_at` to EngagementAdminView.

---

## Phase 2 — Frontend

**2A. TourBookingFlow.tsx — Replace Step 1**  
File: `frontend/src/app/buyer/TourBookingFlow.tsx` (or equivalent path)

Replace the existing Step 1 (auto-advancing contact confirmation) entirely.

New Step 1 — Account Creation form:

```tsx
function AccountCreationStep({ engagementId, onSuccess }: {
  engagementId: string
  onSuccess: () => void
}) {
  const [mode, setMode] = useState<'register' | 'login'>('register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [phone, setPhone] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleRegister = async () => {
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await api.register({ 
        email, password, phone: phone || undefined,
        engagement_id: engagementId 
      })
      storeAuthToken(res.token)
      onSuccess()  // advance to guarantee step
    } catch (e) {
      if (e.status === 409) {
        setError('An account with this email already exists. Sign in instead.')
      } else {
        setError('Something went wrong. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.login({ email, password })
      storeAuthToken(res.token)
      // Link existing account to engagement
      await api.linkBuyer(engagementId)
      onSuccess()
    } catch (e) {
      setError('Incorrect email or password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="commitment-step">
      {mode === 'register' ? (
        <>
          <h2>Create your WEx account to continue.</h2>
          <input type="email" placeholder="Email" value={email}
                 onChange={e => setEmail(e.target.value)} />
          <div className="password-field">
            <input type={showPassword ? 'text' : 'password'}
                   placeholder="Password" value={password}
                   onChange={e => setPassword(e.target.value)} />
            <button onClick={() => setShowPassword(!showPassword)}>
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          <input type={showPassword ? 'text' : 'password'}
                 placeholder="Confirm password" value={confirmPassword}
                 onChange={e => setConfirmPassword(e.target.value)} />
          <input type="tel" placeholder="Mobile number (optional)"
                 value={phone} onChange={e => setPhone(e.target.value)} />
          <p className="field-hint">For tour reminders and updates</p>
          {error && <p className="error">{error}</p>}
          <button onClick={handleRegister} disabled={loading || !email || !password}>
            {loading ? 'Creating account...' : 'Create Account & Continue'}
          </button>
          <button className="link" onClick={() => setMode('login')}>
            Already have an account? Sign in
          </button>
        </>
      ) : (
        <>
          <h2>Sign in to continue.</h2>
          <input type="email" placeholder="Email" value={email}
                 onChange={e => setEmail(e.target.value)} />
          <input type="password" placeholder="Password" value={password}
                 onChange={e => setPassword(e.target.value)} />
          {error && <p className="error">{error}</p>}
          <button onClick={handleLogin} disabled={loading || !email || !password}>
            {loading ? 'Signing in...' : 'Sign In & Continue'}
          </button>
          <button className="link" onClick={() => setMode('register')}>
            New to WEx? Create an account
          </button>
        </>
      )}
    </div>
  )
}
```

**2B. API Client — Add New Methods, Remove /contact**  
File: `frontend/src/lib/api.ts`

```typescript
// Remove:
captureContact(engagementId: string, body: { email: string; phone: string })

// Add:
register(body: { 
  email: string; 
  password: string; 
  phone?: string; 
  engagement_id?: string 
}): Promise<{ user: User; token: string; engagement_id?: string }>

login(body: { 
  email: string; 
  password: string 
}): Promise<{ user: User; token: string }>

linkBuyer(engagementId: string): Promise<Engagement>
```

**2C. TypeScript Types — Update Engagement Interface**  
File: `frontend/src/types/supplier.ts`

```typescript
// Remove from Engagement interface:
buyer_email?: string
buyer_phone?: string
contact_captured_at?: string

// Add:
account_created_at?: string

// Update EngagementStatus enum — remove and add:
// Remove: 'contact_captured'
// Add:    'account_created'

export type EngagementStatus =
  | 'deal_ping_sent' | 'deal_ping_accepted' | 'deal_ping_declined'
  | 'matched' | 'buyer_reviewing' | 'buyer_accepted' | 'account_created'
  | 'guarantee_signed' | 'address_revealed'
  | 'tour_requested' | 'tour_confirmed' | 'tour_rescheduled' | 'tour_completed'
  | 'instant_book_requested'
  | 'buyer_confirmed' | 'agreement_sent' | 'agreement_signed'
  | 'onboarding' | 'active' | 'completed'
  | 'cancelled' | 'expired' | 'declined_by_buyer' | 'declined_by_supplier'
```

**2D. StatusBadge Component**  
File: `frontend/src/components/supplier/StatusBadge.tsx`

```typescript
// Remove:
'contact_captured': { label: 'Contact Captured', color: 'blue' },

// Add:
'account_created': { label: 'Account Created', color: 'blue' },
```

**2E. Demo Data**  
File: `frontend/src/lib/supplier-demo-data.ts`

Replace all instances of `status: 'contact_captured'` with `status: 'account_created'`. Remove `buyer_email` and `buyer_phone` fields from demo engagement objects. Add `account_created_at` where relevant.

---

## Phase 3 — QC & Verification

### Happy Path — New Buyer

1. Browse results anonymously — no prompt, no friction, confirm no account gate appears
2. Click "Accept & Schedule Tour" → account creation form appears (Step 1)
3. Enter email + password → account created → `engagement.buyer_id` set → status = `account_created`
4. Guarantee presented automatically (Step 2) — no additional navigation
5. Sign guarantee → `guarantee_signed` → `guarantee_ip_address` stored
6. Address revealed automatically
7. Pick tour date → `tour_requested`
8. Supplier confirms → `tour_confirmed`
9. Buyer receives confirmation email to the registered email address

### Returning Buyer Path

1. Click "Accept & Schedule Tour" → account creation form appears
2. Click "Already have an account? Sign in" → login form shown
3. Login → `POST /api/engagements/{id}/link-buyer` called → `account_created`
4. Guarantee presented → continue normally

### Edge Cases

| Scenario | Expected Behavior |
|----------|------------------|
| Email already registered | Error: "Account with this email exists. Sign in instead." Login link highlighted. |
| Password mismatch | Inline error before submit. Form stays on Step 1. |
| Password too short | Inline validation. No API call made. |
| Buyer creates account, closes browser, returns | Engagement is `account_created`, buyer is authenticated via stored token → resume at guarantee step |
| Unauthenticated buyer tries to reach address directly | Blocked — guarantee gate enforced by API (existing behavior) |
| `buyer_accepted → guarantee_signed` attempt (skipping account_created) | State machine rejects — returns 400 |
| Registration with `engagement_id` that is not in `buyer_accepted` state | Engagement not linked — registration still succeeds, engagement unchanged |

### State Machine Rejection Tests

- `buyer_accepted → guarantee_signed` → must return 400 (invalid transition)
- `buyer_accepted → address_revealed` → must return 400
- `account_created → address_revealed` (skipping guarantee) → must return 400

### Role Filtering Tests

- `GET /api/engagements/{id}` as buyer at `account_created` — response must not include `supplier_rate_sqft`
- `GET /api/engagements/{id}` as supplier — response must not include `buyer_rate_sqft`
- `GET /api/engagements/{id}` as admin — all fields visible including `account_created_at`

### Type Safety

- `npm run build` passes with zero TypeScript errors
- No references to `contact_captured`, `buyer_email`, or `buyer_phone` remain in frontend source

---

## File Change Summary

| File | Change |
|------|--------|
| `alembic/versions/xxx_account_creation_flow.py` | New migration — enum + column changes |
| `domain/enums.py` | Remove `contact_captured`, add `account_created` |
| `domain/models.py` | Remove 3 fields, add `account_created_at`, update `buyer_id` comment |
| `services/engagement_state_machine.py` | Remove old transitions, add new ones, update unit tests |
| `routes/engagement.py` | Remove `/contact`, add `/link-buyer` |
| `routes/auth.py` | Accept optional `engagement_id` in register body |
| `app/schemas/engagement.py` | Remove buyer_email/phone from serializers, add account_created_at to admin view |
| `frontend/src/app/buyer/TourBookingFlow.tsx` | Replace Step 1 entirely with account creation form |
| `frontend/src/lib/api.ts` | Remove captureContact, add register/login/linkBuyer |
| `frontend/src/types/supplier.ts` | Update EngagementStatus enum + Engagement interface |
| `frontend/src/components/supplier/StatusBadge.tsx` | Swap contact_captured → account_created mapping |
| `frontend/src/lib/supplier-demo-data.ts` | Update status values, remove old fields |

---

## What Does NOT Change

- Anonymous browsing — no changes
- The guarantee content, IP capture, terms versioning — unchanged
- Address reveal gate (only after guarantee) — unchanged  
- Tour request, confirm, reschedule flows — unchanged
- Supplier-side experience — unchanged
- All post-tour states — unchanged
- Background jobs — unchanged
- Admin portal — unchanged (account_created_at visible in admin view only)
