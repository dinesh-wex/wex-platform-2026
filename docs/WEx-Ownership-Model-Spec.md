# WEx — Warehouse Ownership Model Spec
## Why Email Is Wrong and How to Do It Right

**Version:** 1.0 · **Date:** February 2026  
**Status:** Design Decision · **Owned by:** Product (Dinesh)  
**Context:** Triggered by warehouse activation bug where warehouses were not being correctly assigned to users on creation.

---

## 1. The Bug and Why It Revealed a Deeper Problem

The immediate bug: `activate_warehouse` was never setting an owner on the warehouse record. A demo hack in the login flow was compensating by assigning all unowned warehouses to whoever logged in — which broke the moment a second user existed.

The dev's proposed fix was to set `owner_email` from the authenticated user. This is the wrong fix. It patches the symptom but locks in a fundamentally fragile ownership model that will need to be migrated later.

This is the right moment to fix the ownership model correctly, before more code builds on top of the wrong abstraction.

---

## 2. Why Email Is the Wrong Ownership Key

Email feels natural because it's the thing humans use to identify each other. But as a database ownership key it has serious problems.

**Email is mutable.** People change email addresses. If `warehouse.owner_email = "john@oldcompany.com"` and John changes his email, that warehouse is now orphaned or needs a cascading update across every table that stored the email as a key.

**Email is not unique across intent.** The same person can have a personal email and a work email. Which one owns the warehouse? If they log in with the wrong one, they lose access.

**Email is a contact field, not an identity field.** The database has a stable, immutable UUID for every user — that is the identity. Email is just one attribute of that identity, and it can change.

**Email makes reassignment painful.** When an admin leaves and their warehouse needs new ownership, you'd be doing string matching across tables to find everything associated with `john@company.com`. Then updating multiple rows. Then verifying nothing was missed. With a UUID FK this is a single query.

**Email breaks team scenarios.** When a company has multiple users managing the same warehouse, "which email owns it" becomes ambiguous. There is no clean answer.

---

## 3. The Correct Ownership Model

Warehouse ownership does not belong to a **person**. It belongs to a **company**. Individual users are members of a company with different roles. The warehouse never needs to know which specific person is managing it — only which company it belongs to.

This is how every major B2B marketplace models it: Airbnb (hosts can have teams), Stripe (accounts have team members), Shopify (stores have staff). The organizational unit owns the asset. People are just members of the organization.

```
Company
  id:            uuid (PK)           ← stable, never changes
  name:          string              ← "Acme Logistics" or "John Smith"
  type:          enum [individual,   ← display distinction only,
                       business]        not a structural difference
  created_at:    timestamp

User
  id:            uuid (PK)
  email:         string              ← contact field, not ownership key
  name:          string
  company_id:    uuid (FK → Company) ← already in schema
  company_role:  enum [admin,        ← admin = full control
                       member]          member = limited access
  created_at:    timestamp

Warehouse
  id:            uuid (PK)
  company_id:    uuid (FK → Company) ← THIS is the ownership link
  created_by:    uuid (FK → User)    ← audit trail only, not ownership
  ...all other fields
```

The ownership chain is always: **Warehouse → Company → Users**.

`created_by` on the warehouse is an audit field only — it records who activated the warehouse for historical purposes. It has no role in access control or reassignment.

---

## 4. Handling Individuals Without a Company

Individuals who own warehouses personally (not through a business) do not require a different data model. They simply have a Company record that happens to have one member.

At registration, a Company record is **always** created automatically, even for individuals. The user never sees this unless they choose to add team members later. The `type` field distinguishes individuals from businesses for display purposes only — it does not change the ownership structure.

```
At user registration:
  1. Create User record
  2. Auto-create Company record
       name:  user's full name (editable later if they formalize as a business)
       type:  individual
  3. Set user.company_id → new company id
  4. Set user.company_role = admin

If the user later adds team members:
  - Invite goes to the same company
  - New user gets company_id = same company, company_role = member or admin
  - Warehouse ownership does not change — it was always the company's

If the user later formalizes as a business:
  - Update company.name and company.type
  - No ownership migration needed
```

**Why not make company_id nullable?** Every nullable FK creates two code paths everywhere it appears — every query needs a null check, every permission function needs two branches, every team invite must check if a company exists first. A uniform model where every user always has a company_id eliminates this complexity entirely. The individual case is handled by type, not by nullability.

---

## 5. The Admin Leaves Scenario

This was the original concern that surfaced the model question. Under the correct model, an admin leaving requires no warehouse reassignment at all.

**Current (wrong) model:**
```
Admin leaves → warehouse.owner_email is now stale
→ must find all warehouses with that email
→ update each one to new owner's email
→ hope nothing was missed
```

**Correct model:**
```
Admin leaves → remove user from company or change company_role to member
→ warehouse.company_id unchanged
→ other admins in the company retain full access automatically
→ nothing else to do
```

The warehouse never knew about the specific person. It only knows about the company. Personnel changes inside a company are invisible to the ownership model.

If a company dissolves entirely and warehouses need to be transferred to a different company, that is an admin operation — `warehouse.company_id` is updated to the new company. This is a rare, deliberate action, not something triggered by normal staff turnover.

---

## 6. Access Control Logic

With this model, access control at every layer becomes a single consistent check.

**Can this user manage this warehouse?**
```
user.company_id == warehouse.company_id
```

**Can this user perform admin actions on this warehouse?**
```
user.company_id == warehouse.company_id AND user.company_role == admin
```

**Which warehouses should this user see in their dashboard?**
```
SELECT * FROM warehouses WHERE company_id = user.company_id
```

There is no email matching. There is no nullable check. There is no "assign unowned warehouses" hack. The query is always the same regardless of whether the user is an individual, a two-person partnership, or a 10-person team.

---

## 7. Fix for the Immediate Bug

The dev's two-part fix should be replaced with the following:

**Fix 1 — Registration:**
When a new user is created, auto-create a Company record and set `user.company_id`. No user should ever exist without a `company_id`. This is enforced at the database level — `company_id` is non-nullable on the User table.

**Fix 2 — activate_warehouse:**
Set `warehouse.company_id = current_user.company_id` (not owner_email).  
Set `warehouse.created_by = current_user.id` (audit trail).  
Remove any reference to `owner_email` as an ownership mechanism.

**Enforcement note — created_by must never become load-bearing:**
The temptation when debugging will be to write `WHERE created_by = user.id` — it's a faster query to write than the company join and it returns the right result in simple cases. If that shortcut gets in once, it becomes load-bearing and you'll have two ownership models running silently in parallel. Prevent this at the definition site with an explicit comment in both the model and the warehouse route:

```python
# created_by is AUDIT ONLY. Never use for access control.
# Correct access control query: WHERE company_id = user.company_id
```

This comment should live directly above the `created_by` field definition in the model and above any warehouse list query in the routes. Visible at the moment of temptation is the only reliable enforcement.

**Fix 3 — Login/dashboard query:**
Replace the "assign all unowned warehouses" hack with:
```
SELECT * FROM warehouses WHERE company_id = current_user.company_id
```
This is the permanent, correct query. The demo hack is deleted entirely.

---

## 8. What the Outsource Team Needs to Do

**Backend:**
- Add `company_id: uuid NOT NULL (FK → Company)` to Warehouse table
- Add `created_by: uuid NULLABLE (FK → User)` to Warehouse table (audit only)
- Create Company record automatically at user registration
- Update `activate_warehouse` to set `company_id` from authenticated user
- Remove `owner_email` as an ownership field (retain as contact data only if needed elsewhere)
- Write Alembic migration for the schema changes
- Update all warehouse list queries to filter by `company_id`

**Frontend:**
- No structural changes needed — dashboard warehouse query becomes simpler, not more complex
- Remove the "assign unowned warehouses on login" demo hack from login flow

---

## 9. Summary

| Question | Answer |
|----------|--------|
| What owns a warehouse? | Company |
| What links users to a warehouse? | user.company_id = warehouse.company_id |
| What happens when an admin leaves? | Change their company_role. Warehouse unaffected. |
| How do individuals fit in? | Auto-created single-member company. Same model. |
| Is company_id nullable? | No. Every user always has a company. |
| What is email's role? | Contact field only. Never an ownership or access key. |
| What is created_by for? | Audit trail. Not access control. Comment enforces this in code. |
| What is Engagement.supplier_id for? | Audit trail — records who actioned the deal ping. Authorization uses company_id, not supplier_id. |

---

## 10. Engagement.supplier_id — The Same Pattern Applies

The Engagement model has `supplier_id: uuid (FK → User)`. This records the specific user who actioned the deal ping — the person who replied YES, confirmed availability, or signed the agreement on behalf of the supplier company. It is an audit field, exactly like `created_by` on Warehouse.

The same brittleness applies if it's used for access control. If the user who accepted a deal ping leaves the company, any permission check written as `engagement.supplier_id == current_user.id` will silently fail for every other user at that company — even though they should have full access to that engagement.

**The rule:**

> `Engagement.supplier_id` records who actioned the deal ping. It is audit trail only.  
> Authorization checks use `company_id`, not `supplier_id` directly.

In practice, when checking whether a supplier user can action an engagement:

```python
# WRONG — breaks when the original user leaves the company
if engagement.supplier_id == current_user.id:

# CORRECT — any authorized user at the company can action this engagement
if engagement.property.company_id == current_user.company_id \
   and current_user.company_role == "admin":
```

This applies to every engagement action: accepting a deal ping, confirming a tour, signing an agreement. The authorization check is always via `company_id`. The `supplier_id` field answers "who specifically did this?" for audit purposes — it does not answer "who is allowed to do this?"

Add the same enforcement comment at the `supplier_id` field definition in the Engagement model:

```python
# supplier_id is AUDIT ONLY — records who actioned the deal ping.
# Never use for authorization. Use company_id via the property FK instead.
```

---

*This spec supersedes any existing ownership implementation using owner_email or the "assign unowned warehouses" login hack. Both should be considered bugs and removed.*
