"""Engagement status messages — shared by SMS orchestrator and voice handlers.

Maps engagement status strings to buyer-friendly messages.
Update messages here; both channels pick up changes automatically.
"""

STATUS_MESSAGES = {
    "deal_ping_sent": "Your request has been sent to the property owner. You should hear back soon.",
    "deal_ping_accepted": "The owner accepted your request. We're setting things up.",
    "deal_ping_expired": "The original request expired. Want me to find alternatives?",
    "account_created": "Your account is set up. We're coordinating with the property owner.",
    "guarantee_signed": "All set, your guarantee is signed and you should have the address.",
    "guarantee_pending": "Your guarantee link was sent. Tap it to unlock the property address.",
    "tour_requested": "Tour's been requested. You should have a confirmation coming soon.",
    "tour_confirmed": "Tour confirmed for {date}. You're all set!",
    "tour_completed": "Glad you toured! Let me know if you'd like to move forward or see other options.",
    "agreement_sent": "Lease agreement was sent to your email, check your inbox.",
    "agreement_signed": "Your lease is signed! You should be all set.",
    "hold_placed": "A hold has been placed on the space for you. We're finalizing details.",
    "onboarding": "Your onboarding is in progress. You should hear from us shortly.",
    "move_in_scheduled": "Move-in is scheduled! You should have the details in your email.",
    "active": "Your lease is active. Let me know if you need anything.",
    "declined_by_supplier": "Unfortunately the owner went another direction. Want me to find alternatives?",
    "cancelled": "That one was cancelled. Want to start a new search?",
}

# Catch-all for any status not in the dict above
DEFAULT_STATUS_MESSAGE = "Your booking is in progress. Let me check on the details and get back to you."

# Fallback when tour_confirmed but no date is stored
TOUR_CONFIRMED_NO_DATE = "Tour is confirmed. Check your email for the details."

# Terminal statuses — excluded from "recent engagement" lookups
TERMINAL_STATUSES = frozenset({
    "cancelled", "declined_by_supplier", "deal_ping_expired",
})
