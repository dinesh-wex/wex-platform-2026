"""Engagement state machine — validates transitions and enforces business rules.

Encodes the full engagement lifecycle from the spec (Sections 1.2 and 1.3).
"""

from datetime import datetime, timezone
from typing import Optional

from wex_platform.domain.enums import EngagementActor, EngagementStatus


class InvalidTransitionError(Exception):
    """Raised when an engagement state transition is not allowed."""

    def __init__(
        self,
        current_status: EngagementStatus,
        target_status: EngagementStatus,
        reason: str,
    ):
        self.current_status = current_status
        self.target_status = target_status
        self.reason = reason
        super().__init__(
            f"Invalid transition from {current_status.value} to {target_status.value}: {reason}"
        )


# ---------------------------------------------------------------------------
# Transition map: from_status -> {to_status: set_of_allowed_actors}
# ---------------------------------------------------------------------------

S = EngagementStatus
A = EngagementActor

TRANSITION_MAP: dict[EngagementStatus, dict[EngagementStatus, set[EngagementActor]]] = {
    S.DEAL_PING_SENT: {
        S.DEAL_PING_ACCEPTED: {A.SUPPLIER},
        S.DEAL_PING_DECLINED: {A.SUPPLIER},
        S.DEAL_PING_EXPIRED: {A.SYSTEM},
    },
    S.DEAL_PING_ACCEPTED: {
        S.MATCHED: {A.SYSTEM},
    },
    S.MATCHED: {
        S.BUYER_REVIEWING: {A.SYSTEM, A.BUYER},
    },
    S.BUYER_REVIEWING: {
        S.BUYER_ACCEPTED: {A.BUYER},
        S.DECLINED_BY_BUYER: {A.BUYER},
    },
    S.BUYER_ACCEPTED: {
        S.CONTACT_CAPTURED: {A.BUYER},
    },
    S.CONTACT_CAPTURED: {
        S.GUARANTEE_SIGNED: {A.BUYER},
    },
    S.GUARANTEE_SIGNED: {
        S.ADDRESS_REVEALED: {A.SYSTEM},
        S.INSTANT_BOOK_REQUESTED: {A.BUYER, A.SYSTEM},
    },
    S.ADDRESS_REVEALED: {
        S.TOUR_REQUESTED: {A.BUYER},
        S.INSTANT_BOOK_REQUESTED: {A.BUYER},
        S.EXPIRED: {A.SYSTEM},
    },
    S.TOUR_REQUESTED: {
        S.TOUR_CONFIRMED: {A.SUPPLIER},
        S.TOUR_RESCHEDULED: {A.BUYER, A.SUPPLIER},
        S.DECLINED_BY_SUPPLIER: {A.SUPPLIER},
        S.EXPIRED: {A.SYSTEM},
    },
    S.TOUR_CONFIRMED: {
        S.TOUR_COMPLETED: {A.SYSTEM},
        S.TOUR_RESCHEDULED: {A.BUYER, A.SUPPLIER},
    },
    S.TOUR_RESCHEDULED: {
        S.TOUR_CONFIRMED: {A.SUPPLIER},
        S.TOUR_REQUESTED: {A.BUYER},
        S.EXPIRED: {A.SYSTEM},
    },
    S.INSTANT_BOOK_REQUESTED: {
        S.BUYER_CONFIRMED: {A.SYSTEM},
        S.ADDRESS_REVEALED: {A.SYSTEM},  # revert if unavailable
    },
    S.TOUR_COMPLETED: {
        S.BUYER_CONFIRMED: {A.BUYER},
        S.DECLINED_BY_BUYER: {A.BUYER},
        S.EXPIRED: {A.SYSTEM},
    },
    S.BUYER_CONFIRMED: {
        S.AGREEMENT_SENT: {A.SYSTEM},
    },
    S.AGREEMENT_SENT: {
        S.AGREEMENT_SIGNED: {A.SYSTEM},
        S.EXPIRED: {A.SYSTEM},
    },
    S.AGREEMENT_SIGNED: {
        S.ONBOARDING: {A.SYSTEM},
    },
    S.ONBOARDING: {
        S.ACTIVE: {A.SYSTEM},
    },
    S.ACTIVE: {
        S.COMPLETED: {A.SYSTEM},
    },
}

# States from which a buyer can decline at any time
BUYER_DECLINE_STATES: set[EngagementStatus] = {
    S.BUYER_REVIEWING,
    S.BUYER_ACCEPTED,
    S.CONTACT_CAPTURED,
    S.GUARANTEE_SIGNED,
    S.ADDRESS_REVEALED,
    S.TOUR_REQUESTED,
    S.TOUR_CONFIRMED,
    S.TOUR_RESCHEDULED,
    S.TOUR_COMPLETED,
}

# States from which a supplier can decline at any time
SUPPLIER_DECLINE_STATES: set[EngagementStatus] = {
    S.TOUR_REQUESTED,
    S.TOUR_CONFIRMED,
    S.TOUR_RESCHEDULED,
}

# Admin can override status from any non-terminal state
TERMINAL_STATES: set[EngagementStatus] = {
    S.DEAL_PING_EXPIRED,
    S.DEAL_PING_DECLINED,
    S.COMPLETED,
    S.DECLINED_BY_BUYER,
    S.DECLINED_BY_SUPPLIER,
    S.CANCELLED,
    S.EXPIRED,
}

# States from which cancellation is allowed (any non-terminal active state)
CANCELLABLE_STATES: set[EngagementStatus] = {
    s for s in EngagementStatus if s not in TERMINAL_STATES
}

# Deadline fields per status — maps status to the timestamp field used for expiry checks
DEADLINE_FIELDS: dict[EngagementStatus, str] = {
    S.DEAL_PING_SENT: "deal_ping_expires_at",
    S.TOUR_REQUESTED: "tour_requested_at",       # 12h for supplier to confirm
    S.TOUR_RESCHEDULED: "updated_at",             # 24h for reschedule response
    S.TOUR_COMPLETED: "tour_completed_at",        # 72h buyer decision window
    S.AGREEMENT_SENT: "agreement_sent_at",        # 72h signing deadline
    S.ADDRESS_REVEALED: "updated_at",             # 7-day activity window
}

# Max tour reschedules before admin flag
MAX_TOUR_RESCHEDULES = 2


class EngagementStateMachine:
    """Validates engagement state transitions and enforces business rules."""

    def validate_transition(
        self,
        current_status: EngagementStatus,
        target_status: EngagementStatus,
        actor: EngagementActor,
        engagement=None,
    ) -> bool:
        """Return True if the transition is valid. Raise InvalidTransitionError if not.

        Checks:
        1. The transition is in the allowed map (or is a valid decline).
        2. The actor has permission for this transition.
        3. Deadline is not expired for forward transitions.
        4. Tour reschedule limit is enforced.
        """
        # Check admin override — admin can force any non-terminal to any state
        if actor == A.ADMIN and current_status not in TERMINAL_STATES:
            return True

        # Check buyer decline from any eligible state
        if (
            target_status == S.DECLINED_BY_BUYER
            and actor == A.BUYER
            and current_status in BUYER_DECLINE_STATES
        ):
            return True

        # Check supplier decline from any eligible state
        if (
            target_status == S.DECLINED_BY_SUPPLIER
            and actor == A.SUPPLIER
            and current_status in SUPPLIER_DECLINE_STATES
        ):
            return True

        # Check cancellation from any non-terminal state (admin or system only)
        if (
            target_status == S.CANCELLED
            and actor in (A.ADMIN, A.SYSTEM)
            and current_status in CANCELLABLE_STATES
        ):
            return True

        # Look up in the transition map
        allowed_targets = TRANSITION_MAP.get(current_status)
        if allowed_targets is None:
            raise InvalidTransitionError(
                current_status,
                target_status,
                f"No transitions allowed from {current_status.value}",
            )

        if target_status not in allowed_targets:
            raise InvalidTransitionError(
                current_status,
                target_status,
                f"Transition from {current_status.value} to {target_status.value} is not allowed",
            )

        allowed_actors = allowed_targets[target_status]
        if actor not in allowed_actors:
            raise InvalidTransitionError(
                current_status,
                target_status,
                f"Actor {actor.value} is not permitted for this transition "
                f"(allowed: {', '.join(a.value for a in allowed_actors)})",
            )

        # Check deadline expiry — block forward transitions if deadline has passed
        if engagement is not None:
            deadline_field = DEADLINE_FIELDS.get(current_status)
            if deadline_field:
                deadline_value = getattr(engagement, deadline_field, None)
                if deadline_value is not None:
                    now = datetime.now(timezone.utc)
                    # Ensure deadline is tz-aware for comparison
                    if deadline_value.tzinfo is None:
                        deadline_value = deadline_value.replace(tzinfo=timezone.utc)
                    if now > deadline_value and target_status not in (
                        S.DEAL_PING_EXPIRED,
                        S.EXPIRED,
                    ):
                        raise InvalidTransitionError(
                            current_status,
                            target_status,
                            f"Deadline has passed ({deadline_field}={deadline_value.isoformat()})",
                        )

        # Check tour reschedule limit
        if (
            target_status == S.TOUR_RESCHEDULED
            and engagement is not None
        ):
            count = getattr(engagement, "tour_reschedule_count", 0) or 0
            if count >= MAX_TOUR_RESCHEDULES:
                raise InvalidTransitionError(
                    current_status,
                    target_status,
                    f"Tour reschedule limit reached ({MAX_TOUR_RESCHEDULES}). "
                    "Admin intervention required.",
                )

        return True

    def get_allowed_transitions(
        self,
        current_status: EngagementStatus,
        actor: EngagementActor,
    ) -> list[EngagementStatus]:
        """Return list of valid next states for the given actor from the current status."""
        results: list[EngagementStatus] = []

        # Admin can go anywhere from non-terminal states
        if actor == A.ADMIN and current_status not in TERMINAL_STATES:
            all_statuses = list(EngagementStatus)
            return [s for s in all_statuses if s != current_status]

        # Check transition map
        allowed_targets = TRANSITION_MAP.get(current_status, {})
        for target_status, allowed_actors in allowed_targets.items():
            if actor in allowed_actors:
                results.append(target_status)

        # Check global decline transitions
        if actor == A.BUYER and current_status in BUYER_DECLINE_STATES:
            if S.DECLINED_BY_BUYER not in results:
                results.append(S.DECLINED_BY_BUYER)

        if actor == A.SUPPLIER and current_status in SUPPLIER_DECLINE_STATES:
            if S.DECLINED_BY_SUPPLIER not in results:
                results.append(S.DECLINED_BY_SUPPLIER)

        # Cancellation available to admin from any non-terminal state
        if actor == A.ADMIN and current_status in CANCELLABLE_STATES:
            if S.CANCELLED not in results:
                results.append(S.CANCELLED)

        return results

    def check_deadline(self, engagement) -> bool:
        """Return True if the current state's deadline has passed.

        Returns False if there is no deadline for the current state or no deadline value set.
        """
        status = engagement.status
        if isinstance(status, str):
            status = EngagementStatus(status)

        deadline_field = DEADLINE_FIELDS.get(status)
        if deadline_field is None:
            return False

        deadline_value = getattr(engagement, deadline_field, None)
        if deadline_value is None:
            return False

        now = datetime.now(timezone.utc)
        if deadline_value.tzinfo is None:
            deadline_value = deadline_value.replace(tzinfo=timezone.utc)

        return now > deadline_value
