"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { demoEngagements } from "@/lib/supplier-demo-data";
import type { Engagement, EngagementEvent, EngagementStatus } from "@/types/supplier";
import HoldCountdown from "@/components/ui/HoldCountdown";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */
function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/* ------------------------------------------------------------------ */
/*  Status configuration for buyer-facing detail view                  */
/* ------------------------------------------------------------------ */
const STATUS_CONFIG: Record<string, { badge: string; icon: string; description: string; color: string }> = {
  tour_requested: {
    badge: "Awaiting tour confirmation",
    icon: "\u23F3",
    description: "We're coordinating with the property operator to confirm your tour. You'll be notified within 12 hours.",
    color: "bg-blue-50 border-blue-200 text-blue-800",
  },
  tour_confirmed: {
    badge: "Tour confirmed",
    icon: "\u2705",
    description: "Your tour is confirmed. Check the details below and arrive 5 minutes early.",
    color: "bg-emerald-50 border-emerald-200 text-emerald-800",
  },
  tour_rescheduled: {
    badge: "New tour time proposed",
    icon: "\uD83D\uDD04",
    description: "The property operator has proposed a new tour time. Review and respond within 24 hours to keep your hold active.",
    color: "bg-amber-50 border-amber-200 text-amber-800",
  },
  tour_completed: {
    badge: "How was your tour?",
    icon: "\uD83D\uDCAC",
    description: "Let us know if you'd like to proceed with this space. Your hold remains active while you decide.",
    color: "bg-purple-50 border-purple-200 text-purple-800",
  },
  buyer_confirmed: {
    badge: "Agreement being prepared",
    icon: "\uD83D\uDCC4",
    description: "We're preparing your lease agreement. You'll receive it by email shortly.",
    color: "bg-blue-50 border-blue-200 text-blue-800",
  },
  agreement_sent: {
    badge: "Agreement ready to sign",
    icon: "\u270D\uFE0F",
    description: "Your lease agreement is ready. Sign within 72 hours to secure your space at the locked rate.",
    color: "bg-amber-50 border-amber-200 text-amber-800",
  },
  agreement_signed: {
    badge: "Preparing for move-in",
    icon: "\uD83D\uDCE6",
    description: "Agreement signed. Complete the onboarding checklist to finalize your move-in.",
    color: "bg-emerald-50 border-emerald-200 text-emerald-800",
  },
  onboarding: {
    badge: "Complete your setup",
    icon: "\uD83D\uDCCB",
    description: "Complete the remaining onboarding steps to activate your lease.",
    color: "bg-purple-50 border-purple-200 text-purple-800",
  },
  active: {
    badge: "Active lease",
    icon: "\u2705",
    description: "Your lease is active. Contact us if you need anything.",
    color: "bg-emerald-50 border-emerald-200 text-emerald-800",
  },
  expired: {
    badge: "Hold expired",
    icon: "\u26A0\uFE0F",
    description: "Your hold on this space has expired. You can search for similar spaces.",
    color: "bg-red-50 border-red-200 text-red-800",
  },
  buyer_accepted: {
    badge: "Reservation in progress",
    icon: "\uD83D\uDD12",
    description: "Your reservation is being set up. Complete the next steps to secure your hold.",
    color: "bg-blue-50 border-blue-200 text-blue-800",
  },
  account_created: {
    badge: "Account created",
    icon: "\u2705",
    description: "Sign the occupancy guarantee to continue.",
    color: "bg-blue-50 border-blue-200 text-blue-800",
  },
  guarantee_signed: {
    badge: "Guarantee signed",
    icon: "\u2705",
    description: "Choose your path: schedule a tour or book instantly.",
    color: "bg-emerald-50 border-emerald-200 text-emerald-800",
  },
  address_revealed: {
    badge: "Address revealed",
    icon: "\uD83D\uDCCD",
    description: "You now have the property address. Schedule your tour to visit.",
    color: "bg-emerald-50 border-emerald-200 text-emerald-800",
  },
  instant_book_requested: {
    badge: "Instant book in progress",
    icon: "\u26A1",
    description: "We're confirming your instant booking with the property operator.",
    color: "bg-blue-50 border-blue-200 text-blue-800",
  },
};

// States where buyer can take action
const TOUR_OUTCOME_STATUSES: EngagementStatus[] = ["tour_completed"];
const AGREEMENT_SIGN_STATUSES: EngagementStatus[] = ["agreement_sent"];
const ONBOARDING_STATUSES: EngagementStatus[] = ["onboarding"];
const PRE_TOUR_STATUSES: EngagementStatus[] = ["address_revealed", "guarantee_signed"];
const TOUR_RESCHEDULE_STATUSES: EngagementStatus[] = ["tour_rescheduled"];

const HOLD_STATUSES: EngagementStatus[] = [
  "buyer_accepted", "account_created", "guarantee_signed", "address_revealed",
  "tour_requested", "tour_confirmed", "tour_rescheduled", "tour_completed",
];

/* ------------------------------------------------------------------ */
/*  Ask Question Modal                                                 */
/* ------------------------------------------------------------------ */
function AskQuestionSection({ engagementId }: { engagementId: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit() {
    if (!text.trim()) return;
    setLoading(true);
    try {
      await api.submitQuestion(engagementId, text);
      setSent(true);
      setText("");
    } catch {
      // fallback
      setSent(true);
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-center">
        <p className="text-emerald-700 font-medium text-sm">Question sent. We'll follow up via email.</p>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-sm text-emerald-600 hover:text-emerald-700 font-medium hover:underline"
      >
        Have a question? Ask here
      </button>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-2">Ask a Question</h3>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="w-full h-24 bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm resize-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-gray-900"
        placeholder="Type your question..."
      />
      <div className="flex gap-3 mt-3">
        <button onClick={() => setOpen(false)} className="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || loading}
          className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-semibold disabled:opacity-50"
        >
          {loading ? "Sending..." : "Send Question"}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */
export default function BuyerEngagementDetailPage() {
  const params = useParams();
  const router = useRouter();
  const engagementId = params.id as string;

  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [timeline, setTimeline] = useState<EngagementEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [eng, events] = await Promise.all([
        api.getEngagement(engagementId),
        api.getEngagementTimeline(engagementId).catch(() => []),
      ]);
      setEngagement(eng);
      setTimeline(events);
    } catch {
      const demo = demoEngagements.find((e) => e.id === engagementId);
      if (demo) setEngagement(demo);
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTourOutcome = async (outcome: "confirmed" | "passed") => {
    setActionLoading(true);
    try {
      const reason =
        outcome === "passed" ? prompt("Why are you passing?") || undefined : undefined;
      await api.submitTourOutcome(engagementId, outcome, reason);
      await loadData();
    } catch {
      alert("Failed to submit tour outcome");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDecline = async () => {
    const reason = prompt("Reason for declining?");
    if (reason === null) return;
    setActionLoading(true);
    try {
      await api.declineEngagement(engagementId, reason || "No reason provided");
      await loadData();
    } catch {
      alert("Failed to decline");
    } finally {
      setActionLoading(false);
    }
  };

  const handleAcceptReschedule = async () => {
    if (!engagement) return;
    setActionLoading(true);
    try {
      // Accept the rescheduled tour date
      const newDate = engagement.tourRescheduledDate || engagement.tourScheduledDate || "";
      if (newDate) {
        await api.confirmEngagementTourV2(engagementId, newDate);
      }
      await loadData();
    } catch {
      alert("Failed to accept new tour time");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  if (!engagement) {
    return <div className="p-8 text-center text-gray-500">Engagement not found.</div>;
  }

  const statusConfig = STATUS_CONFIG[engagement.status] || {
    badge: formatStatus(engagement.status),
    icon: "\uD83D\uDCCB",
    description: "",
    color: "bg-gray-50 border-gray-200 text-gray-800",
  };

  const showHold = HOLD_STATUSES.includes(engagement.status) && engagement.hold_expires_at;
  const monthlyTotal = engagement.monthlyBuyerTotal || 0;
  const termMonths = engagement.termMonths || engagement.term_months || 0;
  const totalValue = monthlyTotal * termMonths;
  const rateSqft = engagement.buyerRateSqft || 0;

  return (
    <div className="max-w-3xl mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => router.push("/buyer/engagements")}
          className="text-sm text-emerald-600 hover:underline mb-3 inline-block"
        >
          &larr; Back to engagements
        </button>
        <h1 className="text-2xl font-bold text-gray-900">
          {engagement.warehouse?.name || `Engagement ${engagementId.slice(0, 8)}`}
        </h1>
        {engagement.warehouse?.city && (
          <p className="text-gray-500 mt-1 text-sm">
            {engagement.warehouse.city}{engagement.warehouse.state ? `, ${engagement.warehouse.state}` : ""}
          </p>
        )}
      </div>

      {/* ============================================================ */}
      {/*  SECTION 1: STATUS                                            */}
      {/* ============================================================ */}
      <div className={`rounded-xl border p-5 mb-6 ${statusConfig.color}`}>
        <div className="flex items-start gap-3">
          <span className="text-2xl">{statusConfig.icon}</span>
          <div>
            <h2 className="font-semibold text-lg">{statusConfig.badge}</h2>
            {statusConfig.description && (
              <p className="text-sm mt-1 opacity-80">{statusConfig.description}</p>
            )}
            {showHold && (
              <div className="mt-3">
                <HoldCountdown holdExpiresAt={engagement.hold_expires_at} format="expires_in" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/*  ACTION CARDS — state-specific                                */}
      {/* ============================================================ */}

      {/* Tour Rescheduled — accept or suggest different time */}
      {TOUR_RESCHEDULE_STATUSES.includes(engagement.status) && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-3 mb-4">
            <span className="text-2xl">{"\uD83D\uDD04"}</span>
            <div>
              <h3 className="font-semibold text-gray-900">New tour time proposed</h3>
              {engagement.tourRescheduledDate && (
                <p className="text-sm text-gray-600 mt-1">
                  Proposed: {new Date(engagement.tourRescheduledDate).toLocaleDateString("en-US", {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                  {engagement.tourRescheduledTime ? ` at ${engagement.tourRescheduledTime}` : ""}
                </p>
              )}
              {showHold && (
                <div className="mt-2">
                  <HoldCountdown holdExpiresAt={engagement.hold_expires_at} format="expires_in" />
                </div>
              )}
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleAcceptReschedule}
              disabled={actionLoading}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-sm font-semibold"
            >
              Accept New Time
            </button>
            <button
              onClick={() => {
                const newDate = prompt("Suggest a different date (YYYY-MM-DD):");
                if (!newDate) return;
                setActionLoading(true);
                api.rescheduleEngagementTour(engagementId, newDate, "Buyer suggested different time")
                  .then(() => loadData())
                  .catch(() => alert("Failed to suggest new time"))
                  .finally(() => setActionLoading(false));
              }}
              disabled={actionLoading}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 text-sm font-semibold"
            >
              Suggest Different Time
            </button>
          </div>
        </div>
      )}

      {/* Tour Completed — post-tour decision */}
      {TOUR_OUTCOME_STATUSES.includes(engagement.status) && (
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-3 mb-4">
            <span className="text-2xl">{"\uD83D\uDCAC"}</span>
            <div>
              <h3 className="font-semibold text-gray-900">How was your tour?</h3>
              {showHold && (
                <div className="mt-2">
                  <HoldCountdown holdExpiresAt={engagement.hold_expires_at} format="expires_in" />
                </div>
              )}
              {monthlyTotal > 0 && (
                <p className="text-sm text-gray-600 mt-1">
                  Rate locked: {formatCurrency(monthlyTotal)}/mo &middot; {termMonths} months
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => handleTourOutcome("confirmed")}
              disabled={actionLoading}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-sm font-semibold flex items-center gap-1.5"
            >
              <span>{"\u2713"}</span> Yes, I want this space
            </button>
            <button
              onClick={() => {
                // Open question flow
                alert("A WEx specialist will reach out to you shortly.");
              }}
              disabled={actionLoading}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 text-sm font-semibold flex items-center gap-1.5"
            >
              <span>?</span> I have questions
            </button>
            <button
              onClick={() => handleTourOutcome("passed")}
              disabled={actionLoading}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 text-sm font-semibold flex items-center gap-1.5"
            >
              <span>{"\u2717"}</span> Pass on this space
            </button>
          </div>
        </div>
      )}

      {/* Agreement Sign */}
      {AGREEMENT_SIGN_STATUSES.includes(engagement.status) && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-6">
          <h3 className="font-semibold text-gray-900 mb-2">Agreement Ready for Signing</h3>
          <p className="text-sm text-gray-600 mb-4">
            Review and sign the lease agreement to proceed. Sign within 72 hours to secure your space.
          </p>
          <Link
            href={`/buyer/engagements/${engagementId}/agree`}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 inline-block text-sm font-semibold"
          >
            Review &amp; Sign Agreement
          </Link>
        </div>
      )}

      {/* Onboarding */}
      {ONBOARDING_STATUSES.includes(engagement.status) && (
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-5 mb-6">
          <h3 className="font-semibold text-gray-900 mb-2">Complete Your Setup</h3>
          <p className="text-sm text-gray-600 mb-4">
            Complete these steps to activate your lease.
          </p>
          <div className="space-y-2 mb-4">
            {[
              { done: engagement.insuranceUploaded, label: "Insurance Documentation" },
              { done: engagement.companyDocsUploaded, label: "Company Documents" },
              { done: engagement.paymentMethodAdded, label: "Payment Method" },
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-2">
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                    item.done ? "bg-emerald-500 text-white" : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {item.done ? "\u2713" : String(i + 1)}
                </span>
                <span className={`text-sm ${item.done ? "text-gray-500 line-through" : "text-gray-900"}`}>{item.label}</span>
              </div>
            ))}
          </div>
          <Link
            href={`/buyer/engagements/${engagementId}/onboard`}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 inline-block text-sm font-semibold"
          >
            Continue Setup
          </Link>
        </div>
      )}

      {/* Pre-tour — choose path */}
      {PRE_TOUR_STATUSES.includes(engagement.status) && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 mb-6">
          <h3 className="font-semibold text-gray-900 mb-2">Choose Your Path</h3>
          <p className="text-sm text-gray-600 mb-4">Schedule a tour or book instantly if eligible.</p>
          <div className="flex gap-3">
            <button
              onClick={async () => {
                setActionLoading(true);
                try {
                  await api.requestTour(engagementId);
                  await loadData();
                } catch {
                  alert("Failed to request tour");
                } finally {
                  setActionLoading(false);
                }
              }}
              disabled={actionLoading}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-sm font-semibold"
            >
              Schedule Tour
            </button>
            <button
              onClick={async () => {
                setActionLoading(true);
                try {
                  await api.confirmInstantBook(engagementId);
                  await loadData();
                } catch {
                  alert("Failed to instant book");
                } finally {
                  setActionLoading(false);
                }
              }}
              disabled={actionLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-semibold"
            >
              Instant Book
            </button>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/*  SECTION 2: YOUR LOCKED TERMS                                 */}
      {/* ============================================================ */}
      {(rateSqft > 0 || monthlyTotal > 0) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">Your Locked Terms</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {rateSqft > 0 && (
              <div>
                <p className="text-xs text-gray-500">Rate</p>
                <p className="text-lg font-bold text-gray-900">${rateSqft.toFixed(2)}<span className="text-xs text-gray-400 font-normal">/sqft/mo</span></p>
              </div>
            )}
            {monthlyTotal > 0 && (
              <div>
                <p className="text-xs text-gray-500">Monthly</p>
                <p className="text-lg font-bold text-emerald-600">{formatCurrency(monthlyTotal)}</p>
              </div>
            )}
            {termMonths > 0 && (
              <div>
                <p className="text-xs text-gray-500">Term</p>
                <p className="text-lg font-bold text-gray-900">{termMonths} months</p>
              </div>
            )}
            {totalValue > 0 && (
              <div>
                <p className="text-xs text-gray-500">Total</p>
                <p className="text-lg font-bold text-gray-900">{formatCurrency(totalValue)}</p>
              </div>
            )}
          </div>
          {showHold && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <HoldCountdown holdExpiresAt={engagement.hold_expires_at} format="expires_in" />
            </div>
          )}
        </div>
      )}

      {/* ============================================================ */}
      {/*  SECTION 3: PROPERTY DETAILS                                  */}
      {/* ============================================================ */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
        <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">Property Details</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
          {engagement.sqft && (
            <div>
              <p className="text-gray-500">Space</p>
              <p className="font-medium text-gray-900">{engagement.sqft.toLocaleString()} sqft</p>
            </div>
          )}
          {engagement.use_type && (
            <div>
              <p className="text-gray-500">Use Type</p>
              <p className="font-medium text-gray-900">{engagement.use_type}</p>
            </div>
          )}
          {engagement.path && (
            <div>
              <p className="text-gray-500">Path</p>
              <p className="font-medium text-gray-900">{formatStatus(engagement.path)}</p>
            </div>
          )}
          {engagement.leaseStartDate && (
            <div>
              <p className="text-gray-500">Lease Start</p>
              <p className="font-medium text-gray-900">{engagement.leaseStartDate}</p>
            </div>
          )}
          {engagement.leaseEndDate && (
            <div>
              <p className="text-gray-500">Lease End</p>
              <p className="font-medium text-gray-900">{engagement.leaseEndDate}</p>
            </div>
          )}
        </div>

        {/* Address — only post-guarantee */}
        {engagement.warehouse?.address && engagement.guaranteeSignedAt && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <p className="text-gray-500 text-sm">Address</p>
            <p className="font-medium text-gray-900">{engagement.warehouse.address}</p>
            {engagement.warehouse.city && (
              <p className="text-sm text-gray-600">
                {engagement.warehouse.city}{engagement.warehouse.state ? `, ${engagement.warehouse.state}` : ""}
                {engagement.warehouse.zip_code ? ` ${engagement.warehouse.zip_code}` : ""}
              </p>
            )}
            <a
              href={`https://maps.google.com/?q=${encodeURIComponent(
                `${engagement.warehouse.address}, ${engagement.warehouse.city || ""} ${engagement.warehouse.state || ""}`
              )}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-emerald-600 hover:underline mt-1 inline-block"
            >
              Open in Maps &rarr;
            </a>
          </div>
        )}
      </div>

      {/* ============================================================ */}
      {/*  SECTION 4: TIMELINE                                          */}
      {/* ============================================================ */}
      {timeline.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">Timeline</h2>
          <div className="space-y-4">
            {timeline.map((event, i) => (
              <div key={event.id} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className={`w-2.5 h-2.5 rounded-full ${i === 0 ? "bg-emerald-500" : "bg-gray-300"}`} />
                  {i < timeline.length - 1 && <div className="w-px flex-1 bg-gray-200 mt-1" />}
                </div>
                <div className="pb-4">
                  <p className="text-sm font-medium text-gray-900">
                    {event.eventType.replace(/_/g, " ")}
                    {event.actor ? ` (${event.actor})` : ""}
                  </p>
                  <p className="text-xs text-gray-400">
                    {new Date(event.createdAt).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/*  SECTION 5: QUESTIONS                                         */}
      {/* ============================================================ */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
        <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">Questions</h2>
        <AskQuestionSection engagementId={engagementId} />
      </div>

      {/* Active lease info */}
      {engagement.status === "active" && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 mb-6">
          <h3 className="font-semibold text-gray-900 mb-2">Active Lease</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-500">Monthly Payment</p>
              <p className="font-medium text-lg">{formatCurrency(monthlyTotal)}/mo</p>
            </div>
            <div>
              <p className="text-gray-500">Lease Period</p>
              <p className="font-medium">
                {engagement.leaseStartDate || "\u2014"} &rarr; {engagement.leaseEndDate || "Ongoing"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Decline button for eligible states */}
      {!["completed", "declined_by_buyer", "declined_by_supplier", "expired", "active", "deal_ping_expired", "deal_ping_declined"].includes(
        engagement.status
      ) && (
        <div className="mb-6 text-center">
          <button
            onClick={handleDecline}
            disabled={actionLoading}
            className="text-sm text-red-500 hover:text-red-700 disabled:opacity-50"
          >
            Decline this engagement
          </button>
        </div>
      )}
    </div>
  );
}
