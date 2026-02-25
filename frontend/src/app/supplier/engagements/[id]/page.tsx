"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { ArrowLeft, Calendar, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import {
  demoEngagements,
  demoAgreement,
  demoPendingAgreement,
  demoOnboardingComplete,
  demoOnboardingPartial,
  demoPaymentRecords,
} from "@/lib/supplier-demo-data";
import {
  DECLINE_REASONS,
  type Engagement,
  type EngagementStatus,
  type EngagementAgreement,
  type OnboardingStatus,
  type PaymentRecord,
  type DeclineReason,
} from "@/types/supplier";
import StatusBadge from "@/components/supplier/StatusBadge";
import Timeline from "@/components/supplier/Timeline";

// =============================================================================
// Currency / formatting helpers
// =============================================================================

function fmtCurrency(value: number): string {
  return "$" + value.toLocaleString("en-US", { minimumFractionDigits: 0 });
}

function fmtRate(value: number): string {
  return "$" + value.toFixed(2);
}

function shortId(id: string): string {
  const match = id.match(/(\d+)/);
  return match ? match[1] : id;
}

function formatTourDate(date?: string, time?: string): string {
  if (!date) return "";
  const d = new Date(date + "T00:00:00");
  const dateStr = d.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  return time ? `${dateStr} at ${time}` : dateStr;
}

// Buyer info revealed after tour completion or instant book confirmation
const POST_TOUR_STATUSES: EngagementStatus[] = [
  "tour_completed",
  "buyer_confirmed",
  "agreement_sent",
  "agreement_signed",
  "onboarding",
  "active",
  "completed",
];

// =============================================================================
// Step Indicator (spec-compliant tour path)
// =============================================================================

const TOUR_STEPS: { status: EngagementStatus; label: string }[] = [
  { status: "deal_ping_sent", label: "Inquiry" },
  { status: "deal_ping_accepted", label: "Accepted" },
  { status: "guarantee_signed", label: "Guarantee" },
  { status: "tour_requested", label: "Tour Requested" },
  { status: "tour_confirmed", label: "Tour Confirmed" },
  { status: "tour_completed", label: "Tour Done" },
  { status: "buyer_confirmed", label: "Buyer Confirmed" },
  { status: "agreement_sent", label: "Agreement" },
  { status: "agreement_signed", label: "Signed" },
  { status: "onboarding", label: "Onboarding" },
  { status: "active", label: "Active" },
];

const INSTANT_BOOK_STEPS: { status: EngagementStatus; label: string }[] = [
  { status: "deal_ping_sent", label: "Inquiry" },
  { status: "deal_ping_accepted", label: "Accepted" },
  { status: "guarantee_signed", label: "Guarantee" },
  { status: "instant_book_requested", label: "Instant Book" },
  { status: "buyer_confirmed", label: "Buyer Confirmed" },
  { status: "agreement_sent", label: "Agreement" },
  { status: "agreement_signed", label: "Signed" },
  { status: "onboarding", label: "Onboarding" },
  { status: "active", label: "Active" },
];

// Terminal statuses that don't show step indicator
const TERMINAL_STATUSES: EngagementStatus[] = [
  "declined_by_buyer",
  "declined_by_supplier",
  "expired",
  "deal_ping_expired",
  "deal_ping_declined",
  "completed",
];

function StepIndicator({ engagement }: { engagement: Engagement }) {
  if (TERMINAL_STATUSES.includes(engagement.status)) return null;

  const steps = engagement.path === "instant_book" ? INSTANT_BOOK_STEPS : TOUR_STEPS;
  const currentIdx = steps.findIndex((s) => s.status === engagement.status);

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-2">
      {steps.map((step, idx) => {
        const isCompleted = idx < currentIdx;
        const isCurrent = idx === currentIdx;

        return (
          <div key={step.status} className="flex items-center shrink-0">
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                isCompleted
                  ? "bg-emerald-50 text-emerald-700"
                  : isCurrent
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-100 text-slate-400"
              }`}
            >
              {isCompleted && (
                <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
                  <path
                    d="M2.5 6L5 8.5L9.5 3.5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
              {step.label}
            </div>
            {idx < steps.length - 1 && (
              <div
                className={`w-4 h-0.5 mx-0.5 ${
                  idx < currentIdx ? "bg-emerald-300" : "bg-slate-200"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// =============================================================================
// Decline Reason Dropdown
// =============================================================================

function DeclineDropdown({
  open,
  onSelect,
  onClose,
}: {
  open: boolean;
  onSelect: (reason: DeclineReason) => void;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.15 }}
        className="absolute top-full left-0 mt-1 z-50 w-72 bg-white rounded-xl shadow-lg border border-slate-200 py-1"
      >
        <p className="px-3 py-2 text-xs font-medium text-slate-400 uppercase tracking-wide">
          Select a reason
        </p>
        {DECLINE_REASONS.map((reason) => (
          <button
            key={reason}
            onClick={() => onSelect(reason)}
            className="w-full text-left px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 transition-colors"
          >
            {reason}
          </button>
        ))}
      </motion.div>
    </>
  );
}

// =============================================================================
// Propose New Time Panel
// =============================================================================

function ProposeTimePanel({
  open,
  onSubmit,
  onCancel,
}: {
  open: boolean;
  onSubmit: (date: string, time: string) => void;
  onCancel: () => void;
}) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");

  if (!open) return null;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="overflow-hidden"
    >
      <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
        <p className="text-sm font-medium text-slate-700">Propose New Time</p>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <label className="text-xs text-slate-500 mb-1 block">Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none"
            />
          </div>
          <div className="flex-1">
            <label className="text-xs text-slate-500 mb-1 block">Time</label>
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              if (date && time) onSubmit(date, time);
            }}
            disabled={!date || !time}
            className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            Submit Proposal
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// =============================================================================
// Main Page
// =============================================================================

export default function EngagementDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [agreement, setAgreement] = useState<EngagementAgreement | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null);
  const [paymentRecords, setPaymentRecords] = useState<PaymentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [proposeTimeOpen, setProposeTimeOpen] = useState(false);

  // ---- Fetch engagement + Inc2 data ----
  useEffect(() => {
    let cancelled = false;

    async function load() {
      let eng: Engagement | null = null;
      try {
        eng = await api.getEngagement(id);
      } catch {
        eng = demoEngagements.find((e) => e.id === id) ?? null;
      }
      if (cancelled) return;
      setEngagement(eng);

      if (eng) {
        // Load agreement data for relevant statuses
        const agreementStatuses: EngagementStatus[] = [
          'buyer_confirmed', 'agreement_sent', 'agreement_signed', 'onboarding', 'active', 'completed',
        ];
        if (agreementStatuses.includes(eng.status)) {
          try {
            const agr = await api.getAgreement(id);
            if (!cancelled) setAgreement(agr);
          } catch {
            if (!cancelled) {
              // Pick matching demo agreement
              const demo = eng.id === 'eng-1234' ? demoAgreement
                : eng.id === 'eng-1280' ? demoPendingAgreement
                : demoAgreement;
              setAgreement(demo);
            }
          }
        }

        // Load onboarding data
        const onboardingStatuses: EngagementStatus[] = ['onboarding', 'active', 'completed'];
        if (onboardingStatuses.includes(eng.status)) {
          try {
            const ob = await api.getOnboardingStatus(id);
            if (!cancelled) setOnboarding(ob);
          } catch {
            if (!cancelled) {
              setOnboarding(
                eng.status === 'onboarding' ? demoOnboardingPartial : demoOnboardingComplete,
              );
            }
          }
        }

        // Load payment records for active/completed
        if (eng.status === 'active' || eng.status === 'completed') {
          try {
            const pr = await api.getEngagementPayments(id);
            if (!cancelled) setPaymentRecords(Array.isArray(pr) ? pr : []);
          } catch {
            if (!cancelled) {
              setPaymentRecords(demoPaymentRecords.filter((p) => p.engagementId === eng!.id));
            }
          }
        }
      }

      if (!cancelled) setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // ---- Buyer info revealed? ----
  const buyerRevealed = useMemo(
    () => engagement && POST_TOUR_STATUSES.includes(engagement.status),
    [engagement],
  );

  // ---- Action handlers ----
  const handleAccept = useCallback(async () => {
    if (!engagement) return;
    const originalStatus = engagement.status;
    setActionLoading(true);
    setEngagement((prev) =>
      prev ? { ...prev, status: "deal_ping_accepted" as EngagementStatus } : prev,
    );
    try {
      await api.acceptDealPing(id);
    } catch {
      setEngagement((prev) =>
        prev ? { ...prev, status: originalStatus } : prev,
      );
    } finally {
      setActionLoading(false);
    }
  }, [engagement, id]);

  const handleDecline = useCallback(
    async (reason: DeclineReason) => {
      if (!engagement) return;
      const originalStatus = engagement.status;
      setDeclineOpen(false);
      setActionLoading(true);
      setEngagement((prev) =>
        prev ? { ...prev, status: "declined_by_supplier" as EngagementStatus } : prev,
      );
      try {
        await api.declineDealPing(id, reason);
      } catch {
        setEngagement((prev) =>
          prev ? { ...prev, status: originalStatus } : prev,
        );
      } finally {
        setActionLoading(false);
      }
    },
    [engagement, id],
  );

  const handleConfirmTour = useCallback(async () => {
    if (!engagement) return;
    setActionLoading(true);
    setEngagement((prev) =>
      prev
        ? {
            ...prev,
            status: "tour_confirmed" as EngagementStatus,
            tour_confirmed: true,
          }
        : prev,
    );
    try {
      await api.confirmEngagementTourV2(id, engagement.tourScheduledDate ?? engagement.tour_date ?? '');
    } catch {
      setEngagement((prev) =>
        prev
          ? {
              ...prev,
              status: "tour_requested" as EngagementStatus,
              tour_confirmed: false,
            }
          : prev,
      );
    } finally {
      setActionLoading(false);
    }
  }, [engagement, id]);

  const handleProposeTime = useCallback(
    async (date: string, time: string) => {
      if (!engagement) return;
      setActionLoading(true);
      setProposeTimeOpen(false);
      try {
        await api.rescheduleEngagementTour(id, date, 'Supplier proposed new time');
        setEngagement((prev) =>
          prev
            ? { ...prev, tour_date: date, tour_time: time, tourScheduledDate: date }
            : prev,
        );
      } catch {
        // Silent fail for demo
      } finally {
        setActionLoading(false);
      }
    },
    [engagement, id],
  );

  // ---- Loading ----
  if (loading) {
    return (
      <div className="bg-slate-50 min-h-screen p-6 lg:p-10">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="h-6 w-48 bg-slate-200 rounded animate-pulse" />
          <div className="bg-white rounded-xl h-64 animate-pulse border border-slate-100" />
          <div className="bg-white rounded-xl h-80 animate-pulse border border-slate-100" />
        </div>
      </div>
    );
  }

  // ---- Not found ----
  if (!engagement) {
    return (
      <div className="bg-slate-50 min-h-screen p-6 lg:p-10">
        <div className="max-w-4xl mx-auto text-center py-20">
          <p className="text-slate-400 text-sm mb-4">
            Engagement not found.
          </p>
          <Link
            href="/supplier/engagements"
            className="text-emerald-600 hover:text-emerald-700 text-sm font-medium"
          >
            Back to Engagements
          </Link>
        </div>
      </div>
    );
  }

  // Determine which action panel to show
  const showDealPingActions = engagement.status === "deal_ping_sent";
  const showTourConfirmActions = engagement.status === "tour_requested" || engagement.status === "tour_rescheduled";
  const showTourInfo = engagement.status === "tour_confirmed";
  const showAgreementAction = engagement.status === "agreement_sent";
  const showAnyActions = showDealPingActions || showTourConfirmActions || showAgreementAction;

  return (
    <div className="bg-slate-50 min-h-screen">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-10 py-8 lg:py-10">
        {/* ================================================================
            Header
            ================================================================ */}
        <div className="mb-6">
          <Link
            href="/supplier/engagements"
            className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Engagements
          </Link>

          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">
              Engagement #{shortId(engagement.id)}
            </h1>
            <StatusBadge status={engagement.status} />
          </div>

          {engagement.path && (
            <p className="text-xs text-slate-400 mt-1 uppercase tracking-wide">
              {engagement.path === "instant_book" ? "Instant Book Path" : "Tour Path"} &middot; {engagement.tier === "tier_1" ? "Tier 1" : "Tier 2"}
            </p>
          )}
        </div>

        {/* ================================================================
            Summary Cards
            ================================================================ */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* Property & Deal Info */}
          <div className="bg-white rounded-xl border border-slate-100 p-5 space-y-3">
            <h2 className="text-sm font-semibold text-slate-900">
              Deal Summary
            </h2>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">Property</span>
                <Link
                  href={`/supplier/properties/${engagement.property_id}`}
                  className="text-emerald-600 hover:text-emerald-700 font-medium text-right max-w-[60%] truncate"
                >
                  {engagement.property_address}
                </Link>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Square Footage</span>
                <span className="text-slate-900 font-medium">
                  {engagement.sqft.toLocaleString()} sqft
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Use Type</span>
                <span className="text-slate-900 font-medium capitalize">
                  {engagement.use_type}
                </span>
              </div>
              {engagement.matchScore > 0 && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Match Score</span>
                  <span className="text-slate-900 font-medium">
                    {engagement.matchScore}%
                  </span>
                </div>
              )}
              <div className="border-t border-slate-100 pt-2 flex justify-between">
                <span className="text-slate-500">Your Rate</span>
                <span className="text-slate-900 font-medium">
                  {fmtRate(engagement.supplier_rate)}/sqft
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Monthly Payout</span>
                <span className="text-slate-900 font-semibold">
                  {fmtCurrency(engagement.monthly_payout)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Term</span>
                <span className="text-slate-900 font-medium">
                  {engagement.term_months} months
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Total Value</span>
                <span className="text-emerald-700 font-semibold">
                  {fmtCurrency(engagement.total_value)}
                </span>
              </div>
            </div>

            {/* Step indicator */}
            <div className="pt-2">
              <StepIndicator engagement={engagement} />
            </div>
          </div>

          {/* Buyer Info Panel */}
          <div className="bg-white rounded-xl border border-slate-100 p-5 space-y-3">
            <h2 className="text-sm font-semibold text-slate-900">
              Buyer Information
            </h2>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">Use Type</span>
                <span className="text-slate-900 font-medium capitalize">
                  {engagement.buyer_use_type}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Sqft Needed</span>
                <span className="text-slate-900 font-medium">
                  {engagement.sqft.toLocaleString()} sqft
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Term</span>
                <span className="text-slate-900 font-medium">
                  {engagement.term_months} months
                </span>
              </div>
              {engagement.buyer_goods_type && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Goods Type</span>
                  <span className="text-slate-900 font-medium">
                    {engagement.buyer_goods_type}
                  </span>
                </div>
              )}

              <div className="border-t border-slate-100 pt-2 flex justify-between">
                <span className="text-slate-500">Company</span>
                <span
                  className={`font-medium ${
                    buyerRevealed ? "text-slate-900" : "text-slate-400 italic"
                  }`}
                >
                  {buyerRevealed && (engagement.buyerCompanyName || engagement.buyer_company)
                    ? (engagement.buyerCompanyName || engagement.buyer_company)
                    : "Hidden until tour"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Contact</span>
                <span
                  className={`font-medium ${
                    buyerRevealed ? "text-slate-900" : "text-slate-400 italic"
                  }`}
                >
                  {buyerRevealed ? (engagement.buyerEmail || "Available") : "Via WEx only"}
                </span>
              </div>
            </div>

            {/* Tour info */}
            {(engagement.tour_date || engagement.tourScheduledDate) && (
              <div className="pt-2 border-t border-slate-100">
                <div className="flex items-center gap-2 text-sm">
                  <Calendar className="w-4 h-4 text-slate-400" />
                  <span className="text-slate-700">
                    Tour: {formatTourDate(engagement.tourScheduledDate || engagement.tour_date, engagement.tour_time)}
                  </span>
                  {engagement.tour_confirmed || engagement.status === "tour_confirmed" ? (
                    <span className="text-emerald-600 font-medium text-xs">
                      Confirmed
                    </span>
                  ) : (
                    <span className="text-amber-600 font-medium text-xs">
                      Pending
                    </span>
                  )}
                </div>
                {engagement.tourRescheduleCount > 0 && (
                  <p className="text-xs text-slate-400 mt-1">
                    Rescheduled {engagement.tourRescheduleCount} time{engagement.tourRescheduleCount > 1 ? "s" : ""}
                  </p>
                )}
              </div>
            )}

            {/* Decline info */}
            {(engagement.status === "declined_by_buyer" || engagement.status === "declined_by_supplier") && engagement.declineReason && (
              <div className="pt-2 border-t border-slate-100">
                <p className="text-sm text-red-600">
                  Declined by {engagement.declinedBy}: {engagement.declineReason}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ================================================================
            Contextual Actions
            ================================================================ */}
        {showAnyActions && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-4">
              Actions
            </h2>

            {/* Deal Ping actions */}
            {showDealPingActions && (
              <div className="flex flex-wrap gap-3 relative">
                <button
                  onClick={handleAccept}
                  disabled={actionLoading}
                  className="px-5 py-2.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg transition-colors"
                >
                  Accept
                </button>
                <div className="relative">
                  <button
                    onClick={() => setDeclineOpen((prev) => !prev)}
                    disabled={actionLoading}
                    className="inline-flex items-center gap-1.5 px-5 py-2.5 text-sm font-medium text-red-600 border border-red-200 hover:bg-red-50 disabled:opacity-50 rounded-lg transition-colors"
                  >
                    Decline
                    <ChevronDown className="w-3.5 h-3.5" />
                  </button>
                  <AnimatePresence>
                    <DeclineDropdown
                      open={declineOpen}
                      onSelect={handleDecline}
                      onClose={() => setDeclineOpen(false)}
                    />
                  </AnimatePresence>
                </div>
              </div>
            )}

            {/* Tour Requested / Rescheduled actions */}
            {showTourConfirmActions && (
              <div>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={handleConfirmTour}
                    disabled={actionLoading}
                    className="px-5 py-2.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg transition-colors"
                  >
                    Confirm Tour
                  </button>
                  <button
                    onClick={() => setProposeTimeOpen((prev) => !prev)}
                    disabled={actionLoading}
                    className="px-5 py-2.5 text-sm font-medium text-slate-700 border border-slate-200 hover:bg-slate-50 disabled:opacity-50 rounded-lg transition-colors"
                  >
                    Propose New Time
                  </button>
                </div>
                <AnimatePresence>
                  <ProposeTimePanel
                    open={proposeTimeOpen}
                    onSubmit={handleProposeTime}
                    onCancel={() => setProposeTimeOpen(false)}
                  />
                </AnimatePresence>
              </div>
            )}

            {/* Agreement Sent action */}
            {showAgreementAction && (
              <button
                onClick={async () => {
                  setActionLoading(true);
                  try {
                    await api.signAgreement(id, 'supplier');
                    setEngagement((prev) =>
                      prev ? { ...prev, status: 'agreement_signed' as EngagementStatus } : prev,
                    );
                    setAgreement((prev) =>
                      prev ? { ...prev, status: 'fully_signed', supplierSignedAt: new Date().toISOString() } : prev,
                    );
                  } catch {
                    // demo fallback
                    setEngagement((prev) =>
                      prev ? { ...prev, status: 'agreement_signed' as EngagementStatus } : prev,
                    );
                  } finally {
                    setActionLoading(false);
                  }
                }}
                disabled={actionLoading}
                className="px-5 py-2.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg transition-colors"
              >
                Review & Sign Agreement
              </button>
            )}
          </div>
        )}

        {/* Tour confirmed info panel (no actions, just info) */}
        {showTourInfo && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-2">
              Tour Confirmed
            </h2>
            <p className="text-sm text-slate-600">
              The tour is confirmed for {formatTourDate(engagement.tourScheduledDate || engagement.tour_date, engagement.tour_time)}.
              No action needed until the tour takes place.
            </p>
          </div>
        )}

        {/* ================================================================
            Inc2: Tour Completed — Awaiting buyer decision
            ================================================================ */}
        {engagement.status === "tour_completed" && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-2">
              Tour Completed
            </h2>
            <p className="text-sm text-slate-600">
              The buyer toured the property{engagement.tourCompletedAt ? ` on ${new Date(engagement.tourCompletedAt).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}` : ""}. Awaiting buyer decision (confirm or pass).
            </p>
          </div>
        )}

        {/* ================================================================
            Inc2: Agreement Section
            ================================================================ */}
        {agreement && ["buyer_confirmed", "agreement_sent", "agreement_signed", "onboarding", "active", "completed"].includes(engagement.status) && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-900">
                Lease Agreement
              </h2>
              <StatusBadge
                status={
                  agreement.status === "fully_signed" ? "agreement_signed"
                    : agreement.status === "pending" ? "agreement_sent"
                    : agreement.status
                }
                size="sm"
              />
            </div>

            {/* Agreement terms preview */}
            <div className="bg-slate-50 rounded-lg p-4 mb-4 max-h-48 overflow-y-auto">
              <pre className="text-xs text-slate-600 whitespace-pre-wrap font-sans leading-relaxed">
                {agreement.termsText.slice(0, 800)}{agreement.termsText.length > 800 ? "..." : ""}
              </pre>
            </div>

            {/* Signature status */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${agreement.buyerSignedAt ? "bg-emerald-500" : "bg-slate-300"}`} />
                <span className="text-slate-600">
                  Buyer: {agreement.buyerSignedAt ? `Signed ${new Date(agreement.buyerSignedAt).toLocaleDateString()}` : "Not yet signed"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${agreement.supplierSignedAt ? "bg-emerald-500" : "bg-slate-300"}`} />
                <span className="text-slate-600">
                  Supplier: {agreement.supplierSignedAt ? `Signed ${new Date(agreement.supplierSignedAt).toLocaleDateString()}` : "Not yet signed"}
                </span>
              </div>
            </div>

            {/* Financial terms */}
            <div className="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 gap-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">Your Rate</span>
                <span className="text-slate-900 font-medium">${agreement.supplierRateSqft?.toFixed(2)}/sqft</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Monthly Payout</span>
                <span className="text-slate-900 font-semibold">${agreement.monthlySupplierPayout?.toLocaleString()}</span>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================
            Inc2: Onboarding Section
            ================================================================ */}
        {onboarding && ["onboarding", "active", "completed"].includes(engagement.status) && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-4">
              Onboarding
            </h2>

            {/* Progress bar */}
            {(() => {
              const done = [onboarding.insuranceUploaded, onboarding.companyDocsUploaded, onboarding.paymentMethodAdded].filter(Boolean).length;
              const pct = Math.round((done / 3) * 100);
              return (
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-slate-500 mb-1">
                    <span>{done}/3 completed</span>
                    <span>{pct}%</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2">
                    <div
                      className="bg-emerald-500 h-2 rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })()}

            {/* Checklist */}
            <div className="space-y-3">
              {[
                { label: "Insurance uploaded", done: onboarding.insuranceUploaded },
                { label: "Company docs uploaded", done: onboarding.companyDocsUploaded },
                { label: "Payment method added", done: onboarding.paymentMethodAdded },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-2 text-sm">
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center ${item.done ? "bg-emerald-100" : "bg-slate-100"}`}>
                    {item.done ? (
                      <svg className="w-3 h-3 text-emerald-600" viewBox="0 0 12 12" fill="none">
                        <path d="M2.5 6L5 8.5L9.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : (
                      <div className="w-2 h-2 rounded-full bg-slate-300" />
                    )}
                  </div>
                  <span className={item.done ? "text-slate-700" : "text-slate-400"}>{item.label}</span>
                </div>
              ))}
            </div>

            {onboarding.completedAt && (
              <p className="text-xs text-emerald-600 mt-3">
                Onboarding completed {new Date(onboarding.completedAt).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
              </p>
            )}
          </div>
        )}

        {/* ================================================================
            Inc2: Active Lease Details
            ================================================================ */}
        {engagement.status === "active" && engagement.leaseStartDate && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-4">
              Active Lease
            </h2>
            <div className="grid grid-cols-2 gap-3 text-sm mb-4">
              <div className="flex justify-between">
                <span className="text-slate-500">Lease Start</span>
                <span className="text-slate-900 font-medium">
                  {new Date(engagement.leaseStartDate + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                </span>
              </div>
              {engagement.leaseEndDate && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Lease End</span>
                  <span className="text-slate-900 font-medium">
                    {new Date(engagement.leaseEndDate + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-500">Monthly Payout</span>
                <span className="text-emerald-700 font-semibold">{fmtCurrency(engagement.monthlySupplierPayout)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Square Footage</span>
                <span className="text-slate-900 font-medium">{engagement.sqft.toLocaleString()} sqft</span>
              </div>
            </div>

            {/* Payment history */}
            {paymentRecords.length > 0 && (
              <div className="border-t border-slate-100 pt-4">
                <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">Payment History</h3>
                <div className="space-y-2">
                  {paymentRecords.map((pr) => (
                    <div key={pr.id} className="flex items-center justify-between text-sm">
                      <span className="text-slate-600">
                        {new Date(pr.periodStart + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" })}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-slate-900 font-medium">{fmtCurrency(pr.supplierAmount ?? 0)}</span>
                        <StatusBadge status={pr.supplierStatus} size="sm" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ================================================================
            Inc2: Completed Lease Summary
            ================================================================ */}
        {engagement.status === "completed" && (
          <div className="bg-white rounded-xl border border-slate-100 p-5 mb-6">
            <h2 className="text-sm font-semibold text-slate-900 mb-4">
              Lease Summary
            </h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {engagement.leaseStartDate && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Lease Period</span>
                  <span className="text-slate-900 font-medium">
                    {new Date(engagement.leaseStartDate + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" })}
                    {engagement.leaseEndDate ? ` - ${new Date(engagement.leaseEndDate + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" })}` : ""}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-500">Total Earned</span>
                <span className="text-emerald-700 font-semibold">
                  {fmtCurrency(paymentRecords.reduce((sum, pr) => sum + (pr.supplierAmount ?? 0), 0) || engagement.total_value)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Monthly Rate</span>
                <span className="text-slate-900 font-medium">{fmtCurrency(engagement.monthlySupplierPayout)}/mo</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Duration</span>
                <span className="text-slate-900 font-medium">{engagement.term_months} months</span>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================
            Engagement Timeline
            ================================================================ */}
        <div className="bg-white rounded-xl border border-slate-100 p-5">
          <h2 className="text-sm font-semibold text-slate-900 mb-5">
            Timeline
          </h2>
          <Timeline events={engagement.timeline} />
        </div>
      </div>
    </div>
  );
}
