"""Unit tests for the EngagementStateMachine."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from wex_platform.domain.enums import EngagementActor, EngagementStatus
from wex_platform.services.engagement_state_machine import (
    BUYER_DECLINE_STATES,
    CANCELLABLE_STATES,
    MAX_TOUR_RESCHEDULES,
    SUPPLIER_DECLINE_STATES,
    TERMINAL_STATES,
    TRANSITION_MAP,
    EngagementStateMachine,
    InvalidTransitionError,
)

S = EngagementStatus
A = EngagementActor


@pytest.fixture
def sm():
    return EngagementStateMachine()


def _make_engagement(**kwargs):
    """Create a simple namespace that acts like an engagement object."""
    defaults = {
        "status": S.DEAL_PING_SENT.value,
        "deal_ping_expires_at": None,
        "tour_reschedule_count": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Test every valid transition in the transition map
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """Every transition defined in TRANSITION_MAP should succeed for allowed actors."""

    @pytest.mark.parametrize(
        "from_status,to_status,actor",
        [
            (from_s, to_s, actor)
            for from_s, targets in TRANSITION_MAP.items()
            for to_s, actors in targets.items()
            for actor in actors
        ],
    )
    def test_all_valid_transitions(self, sm, from_status, to_status, actor):
        result = sm.validate_transition(from_status, to_status, actor)
        assert result is True


class TestHappyPathTourFlow:
    """Walk through the full tour path happy path."""

    def test_full_tour_path(self, sm):
        transitions = [
            (S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED, A.SUPPLIER),
            (S.DEAL_PING_ACCEPTED, S.MATCHED, A.SYSTEM),
            (S.MATCHED, S.BUYER_REVIEWING, A.SYSTEM),
            (S.BUYER_REVIEWING, S.BUYER_ACCEPTED, A.BUYER),
            (S.BUYER_ACCEPTED, S.CONTACT_CAPTURED, A.BUYER),
            (S.CONTACT_CAPTURED, S.GUARANTEE_SIGNED, A.BUYER),
            (S.GUARANTEE_SIGNED, S.ADDRESS_REVEALED, A.SYSTEM),
            (S.ADDRESS_REVEALED, S.TOUR_REQUESTED, A.BUYER),
            (S.TOUR_REQUESTED, S.TOUR_CONFIRMED, A.SUPPLIER),
            (S.TOUR_CONFIRMED, S.TOUR_COMPLETED, A.SYSTEM),
            (S.TOUR_COMPLETED, S.BUYER_CONFIRMED, A.BUYER),
            (S.BUYER_CONFIRMED, S.AGREEMENT_SENT, A.SYSTEM),
            (S.AGREEMENT_SENT, S.AGREEMENT_SIGNED, A.SYSTEM),
            (S.AGREEMENT_SIGNED, S.ONBOARDING, A.SYSTEM),
            (S.ONBOARDING, S.ACTIVE, A.SYSTEM),
            (S.ACTIVE, S.COMPLETED, A.SYSTEM),
        ]
        for from_s, to_s, actor in transitions:
            assert sm.validate_transition(from_s, to_s, actor) is True


class TestHappyPathInstantBookFlow:
    """Walk through the full instant book happy path."""

    def test_full_instant_book_path(self, sm):
        transitions = [
            (S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED, A.SUPPLIER),
            (S.DEAL_PING_ACCEPTED, S.MATCHED, A.SYSTEM),
            (S.MATCHED, S.BUYER_REVIEWING, A.BUYER),
            (S.BUYER_REVIEWING, S.BUYER_ACCEPTED, A.BUYER),
            (S.BUYER_ACCEPTED, S.CONTACT_CAPTURED, A.BUYER),
            (S.CONTACT_CAPTURED, S.GUARANTEE_SIGNED, A.BUYER),
            (S.GUARANTEE_SIGNED, S.INSTANT_BOOK_REQUESTED, A.BUYER),
            (S.INSTANT_BOOK_REQUESTED, S.BUYER_CONFIRMED, A.SYSTEM),
            (S.BUYER_CONFIRMED, S.AGREEMENT_SENT, A.SYSTEM),
            (S.AGREEMENT_SENT, S.AGREEMENT_SIGNED, A.SYSTEM),
            (S.AGREEMENT_SIGNED, S.ONBOARDING, A.SYSTEM),
            (S.ONBOARDING, S.ACTIVE, A.SYSTEM),
            (S.ACTIVE, S.COMPLETED, A.SYSTEM),
        ]
        for from_s, to_s, actor in transitions:
            assert sm.validate_transition(from_s, to_s, actor) is True


# ---------------------------------------------------------------------------
# Test invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_cannot_skip_states(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.DEAL_PING_SENT, S.MATCHED, A.SYSTEM)

    def test_cannot_go_backwards(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.BUYER_ACCEPTED, S.BUYER_REVIEWING, A.BUYER)

    def test_terminal_state_no_transitions(self, sm):
        for terminal in [S.COMPLETED, S.DECLINED_BY_BUYER, S.DECLINED_BY_SUPPLIER, S.EXPIRED]:
            with pytest.raises(InvalidTransitionError):
                sm.validate_transition(terminal, S.ACTIVE, A.SYSTEM)

    def test_deal_ping_expired_is_terminal(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.DEAL_PING_EXPIRED, S.MATCHED, A.SYSTEM)

    def test_deal_ping_declined_is_terminal(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.DEAL_PING_DECLINED, S.MATCHED, A.SYSTEM)


# ---------------------------------------------------------------------------
# Test wrong actor rejections
# ---------------------------------------------------------------------------


class TestWrongActor:
    def test_buyer_cannot_accept_deal_ping(self, sm):
        with pytest.raises(InvalidTransitionError, match="not permitted"):
            sm.validate_transition(S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED, A.BUYER)

    def test_supplier_cannot_accept_match_for_buyer(self, sm):
        with pytest.raises(InvalidTransitionError, match="not permitted"):
            sm.validate_transition(S.BUYER_REVIEWING, S.BUYER_ACCEPTED, A.SUPPLIER)

    def test_buyer_cannot_confirm_tour(self, sm):
        with pytest.raises(InvalidTransitionError, match="not permitted"):
            sm.validate_transition(S.TOUR_REQUESTED, S.TOUR_CONFIRMED, A.BUYER)

    def test_supplier_cannot_capture_contact(self, sm):
        with pytest.raises(InvalidTransitionError, match="not permitted"):
            sm.validate_transition(S.BUYER_ACCEPTED, S.CONTACT_CAPTURED, A.SUPPLIER)

    def test_system_cannot_decline_deal_ping(self, sm):
        with pytest.raises(InvalidTransitionError, match="not permitted"):
            sm.validate_transition(S.DEAL_PING_SENT, S.DEAL_PING_DECLINED, A.SYSTEM)


# ---------------------------------------------------------------------------
# Test buyer/supplier decline from eligible states
# ---------------------------------------------------------------------------


class TestDeclines:
    @pytest.mark.parametrize("state", list(BUYER_DECLINE_STATES))
    def test_buyer_can_decline_from_eligible_states(self, sm, state):
        assert sm.validate_transition(state, S.DECLINED_BY_BUYER, A.BUYER) is True

    @pytest.mark.parametrize("state", list(SUPPLIER_DECLINE_STATES))
    def test_supplier_can_decline_from_eligible_states(self, sm, state):
        assert sm.validate_transition(state, S.DECLINED_BY_SUPPLIER, A.SUPPLIER) is True

    def test_supplier_cannot_decline_at_buyer_accepted(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.BUYER_ACCEPTED, S.DECLINED_BY_SUPPLIER, A.SUPPLIER)

    def test_buyer_cannot_decline_during_deal_ping(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.DEAL_PING_SENT, S.DECLINED_BY_BUYER, A.BUYER)


# ---------------------------------------------------------------------------
# Test admin override
# ---------------------------------------------------------------------------


class TestAdminOverride:
    def test_admin_can_force_any_non_terminal_transition(self, sm):
        assert sm.validate_transition(S.TOUR_REQUESTED, S.ACTIVE, A.ADMIN) is True

    def test_admin_cannot_transition_from_terminal(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.COMPLETED, S.ACTIVE, A.ADMIN)


# ---------------------------------------------------------------------------
# Test deadline expiry blocking
# ---------------------------------------------------------------------------


class TestDeadlineExpiry:
    def test_expired_deal_ping_blocks_acceptance(self, sm):
        engagement = _make_engagement(
            deal_ping_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with pytest.raises(InvalidTransitionError, match="Deadline has passed"):
            sm.validate_transition(
                S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED, A.SUPPLIER, engagement=engagement
            )

    def test_expired_deal_ping_allows_expiry_transition(self, sm):
        engagement = _make_engagement(
            deal_ping_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert sm.validate_transition(
            S.DEAL_PING_SENT, S.DEAL_PING_EXPIRED, A.SYSTEM, engagement=engagement
        ) is True

    def test_valid_deadline_allows_acceptance(self, sm):
        engagement = _make_engagement(
            deal_ping_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )
        assert sm.validate_transition(
            S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED, A.SUPPLIER, engagement=engagement
        ) is True

    def test_no_deadline_set_allows_transition(self, sm):
        engagement = _make_engagement(deal_ping_expires_at=None)
        assert sm.validate_transition(
            S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED, A.SUPPLIER, engagement=engagement
        ) is True


# ---------------------------------------------------------------------------
# Test tour reschedule limit
# ---------------------------------------------------------------------------


class TestTourRescheduleLimit:
    def test_reschedule_allowed_under_limit(self, sm):
        engagement = _make_engagement(tour_reschedule_count=1)
        assert sm.validate_transition(
            S.TOUR_CONFIRMED, S.TOUR_RESCHEDULED, A.BUYER, engagement=engagement
        ) is True

    def test_reschedule_blocked_at_limit(self, sm):
        engagement = _make_engagement(tour_reschedule_count=MAX_TOUR_RESCHEDULES)
        with pytest.raises(InvalidTransitionError, match="reschedule limit"):
            sm.validate_transition(
                S.TOUR_CONFIRMED, S.TOUR_RESCHEDULED, A.BUYER, engagement=engagement
            )

    def test_reschedule_blocked_above_limit(self, sm):
        engagement = _make_engagement(tour_reschedule_count=5)
        with pytest.raises(InvalidTransitionError, match="reschedule limit"):
            sm.validate_transition(
                S.TOUR_REQUESTED, S.TOUR_RESCHEDULED, A.SUPPLIER, engagement=engagement
            )


# ---------------------------------------------------------------------------
# Test instant book reversion
# ---------------------------------------------------------------------------


class TestInstantBookReversion:
    def test_instant_book_can_revert_to_address_revealed(self, sm):
        assert sm.validate_transition(
            S.INSTANT_BOOK_REQUESTED, S.ADDRESS_REVEALED, A.SYSTEM
        ) is True


# ---------------------------------------------------------------------------
# Test get_allowed_transitions
# ---------------------------------------------------------------------------


class TestGetAllowedTransitions:
    def test_deal_ping_sent_supplier(self, sm):
        allowed = sm.get_allowed_transitions(S.DEAL_PING_SENT, A.SUPPLIER)
        assert S.DEAL_PING_ACCEPTED in allowed
        assert S.DEAL_PING_DECLINED in allowed
        assert S.DEAL_PING_EXPIRED not in allowed

    def test_deal_ping_sent_system(self, sm):
        allowed = sm.get_allowed_transitions(S.DEAL_PING_SENT, A.SYSTEM)
        assert S.DEAL_PING_EXPIRED in allowed
        assert S.DEAL_PING_ACCEPTED not in allowed

    def test_buyer_reviewing_buyer(self, sm):
        allowed = sm.get_allowed_transitions(S.BUYER_REVIEWING, A.BUYER)
        assert S.BUYER_ACCEPTED in allowed
        assert S.DECLINED_BY_BUYER in allowed

    def test_tour_requested_supplier_includes_decline(self, sm):
        allowed = sm.get_allowed_transitions(S.TOUR_REQUESTED, A.SUPPLIER)
        assert S.TOUR_CONFIRMED in allowed
        assert S.TOUR_RESCHEDULED in allowed
        assert S.DECLINED_BY_SUPPLIER in allowed

    def test_terminal_state_no_transitions(self, sm):
        allowed = sm.get_allowed_transitions(S.COMPLETED, A.SYSTEM)
        assert allowed == []

    def test_admin_gets_all_from_non_terminal(self, sm):
        allowed = sm.get_allowed_transitions(S.TOUR_REQUESTED, A.ADMIN)
        assert len(allowed) > 5  # admin can go anywhere


# ---------------------------------------------------------------------------
# Test check_deadline
# ---------------------------------------------------------------------------


class TestCheckDeadline:
    def test_no_deadline_field_returns_false(self, sm):
        engagement = _make_engagement(status=S.MATCHED.value)
        assert sm.check_deadline(engagement) is False

    def test_no_deadline_value_returns_false(self, sm):
        engagement = _make_engagement(
            status=S.DEAL_PING_SENT.value,
            deal_ping_expires_at=None,
        )
        assert sm.check_deadline(engagement) is False

    def test_deadline_not_passed_returns_false(self, sm):
        engagement = _make_engagement(
            status=S.DEAL_PING_SENT.value,
            deal_ping_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )
        assert sm.check_deadline(engagement) is False

    def test_deadline_passed_returns_true(self, sm):
        engagement = _make_engagement(
            status=S.DEAL_PING_SENT.value,
            deal_ping_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert sm.check_deadline(engagement) is True

    def test_naive_datetime_treated_as_utc(self, sm):
        engagement = _make_engagement(
            status=S.DEAL_PING_SENT.value,
            deal_ping_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
        )
        assert sm.check_deadline(engagement) is True


# ---------------------------------------------------------------------------
# Cancellation tests
# ---------------------------------------------------------------------------


class TestCancellation:
    """Test CANCELLED transitions from any non-terminal state."""

    @pytest.mark.parametrize("state", list(CANCELLABLE_STATES))
    def test_admin_can_cancel_from_any_cancellable_state(self, sm, state):
        assert sm.validate_transition(state, S.CANCELLED, A.ADMIN) is True

    @pytest.mark.parametrize("state", list(TERMINAL_STATES))
    def test_cannot_cancel_from_terminal_state(self, sm, state):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(state, S.CANCELLED, A.BUYER)

    def test_buyer_cannot_cancel(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.ACTIVE, S.CANCELLED, A.BUYER)

    def test_supplier_cannot_cancel(self, sm):
        with pytest.raises(InvalidTransitionError):
            sm.validate_transition(S.ACTIVE, S.CANCELLED, A.SUPPLIER)

    def test_system_can_cancel(self, sm):
        assert sm.validate_transition(S.ACTIVE, S.CANCELLED, A.SYSTEM) is True

    def test_cancelled_is_terminal(self, sm):
        assert S.CANCELLED in TERMINAL_STATES

    def test_cancelled_in_allowed_transitions_for_admin(self, sm):
        allowed = sm.get_allowed_transitions(S.ACTIVE, A.ADMIN)
        assert S.CANCELLED in allowed
