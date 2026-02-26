"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  MessageSquare,
  Box,
  Settings,
  Truck,
  Check,
  Loader2,
  Clock,
  Zap,
  Map,
  Filter,
  Grid,
  Building2,
  ArrowUpRight,
  Calendar,
  Infinity,
  Shield,
  MapPin,
  AlertTriangle,
  Search,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Engagement, EngagementStatus } from "@/types/supplier";
import { demoEngagements } from "@/lib/supplier-demo-data";
import HoldCountdown from "@/components/ui/HoldCountdown";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface BuyerIntent {
  location: string;
  useType: string;
  goodsType: string;
  sqft: number;
  timing: string;
  duration: string;
  amenities: string[];
}

interface GridWarehouse {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  available_sqft: number;
  supplier_rate: number;
  image_url: string | null;
  use_type?: string;
}

const USE_TYPE_LABELS: Record<string, string> = {
  storage: "Storage",
  light_ops: "Light Operations",
  distribution: "Distribution",
};

/* Timing: hybrid calendar picker + "Immediately" shortcut (see Step 5) */

const GOODS_TYPE_OPTIONS: Record<string, { label: string; icon: React.ReactNode; useTypes: string[] }[]> = {
  storage: [
    { label: "General Merchandise", icon: <Box size={24} />, useTypes: ["storage", "light_ops", "distribution"] },
    { label: "Food & Beverage", icon: <Box size={24} />, useTypes: ["storage", "distribution"] },
    { label: "Chemicals / Hazmat", icon: <Box size={24} />, useTypes: ["storage"] },
    { label: "High-Value / Sensitive", icon: <Box size={24} />, useTypes: ["storage"] },
    { label: "Electronics", icon: <Box size={24} />, useTypes: ["storage", "light_ops", "distribution"] },
    { label: "Raw Materials", icon: <Box size={24} />, useTypes: ["storage"] },
  ],
  light_ops: [
    { label: "General Merchandise", icon: <Box size={24} />, useTypes: ["storage", "light_ops", "distribution"] },
    { label: "Electronics", icon: <Box size={24} />, useTypes: ["storage", "light_ops", "distribution"] },
    { label: "Food & Beverage", icon: <Box size={24} />, useTypes: ["storage", "distribution"] },
    { label: "High-Value / Sensitive", icon: <Box size={24} />, useTypes: ["storage"] },
  ],
  distribution: [
    { label: "General Merchandise", icon: <Box size={24} />, useTypes: ["storage", "light_ops", "distribution"] },
    { label: "Food & Beverage", icon: <Box size={24} />, useTypes: ["storage", "distribution"] },
    { label: "Electronics", icon: <Box size={24} />, useTypes: ["storage", "light_ops", "distribution"] },
    { label: "Raw Materials", icon: <Box size={24} />, useTypes: ["storage"] },
  ],
};

/* Duration: interactive 1–36 month slider + "Flexible" shortcut (see Step 5) */

const DEALBREAKER_OPTIONS = [
  "Office Space",
  "Dock Doors",
  "High Power",
  "Climate Control",
  "24/7 Access",
  "Sprinkler System",
  "Parking",
];

/* ================================================================== */
/*  Phase 6A: STATUS CONFIG for buyer dashboard                        */
/* ================================================================== */
const STATUS_CONFIG: Record<string, { badge: string; icon: string; supporting: string; cta?: string }> = {
  tour_requested: { badge: "Awaiting tour confirmation", icon: "\u23F3", supporting: "We'll notify you within 12 hours.", cta: "View Details" },
  tour_confirmed: { badge: "Tour confirmed", icon: "\u2705", supporting: "", cta: "Get Directions" },
  tour_rescheduled: { badge: "New tour time proposed", icon: "\uD83D\uDD04", supporting: "Review the new time \u2014 respond within 24 hours", cta: "Review" },
  tour_completed: { badge: "How was your tour?", icon: "\uD83D\uDCAC", supporting: "Let us know to keep your hold active", cta: "Respond" },
  buyer_confirmed: { badge: "Agreement being prepared", icon: "\uD83D\uDCC4", supporting: "You'll receive it by email shortly", cta: "View Details" },
  agreement_sent: { badge: "Agreement ready to sign", icon: "\u270D\uFE0F", supporting: "Sign within 72 hours to secure your space", cta: "Sign Now" },
  agreement_signed: { badge: "Preparing for move-in", icon: "\uD83D\uDCE6", supporting: "Complete your onboarding checklist", cta: "Continue Setup" },
  onboarding: { badge: "Complete your setup", icon: "\uD83D\uDCCB", supporting: "", cta: "Continue Setup" },
  active: { badge: "Active lease", icon: "\u2705", supporting: "", cta: "View Details" },
  expired: { badge: "Hold expired", icon: "\u26A0\uFE0F", supporting: "This space is no longer held.", cta: "Search Again" },
  // Additional statuses
  buyer_accepted: { badge: "Reservation in progress", icon: "\uD83D\uDD12", supporting: "Setting up your hold...", cta: "View Details" },
  account_created: { badge: "Account created", icon: "\u2705", supporting: "Sign the guarantee to continue", cta: "Continue" },
  guarantee_signed: { badge: "Guarantee signed", icon: "\u2705", supporting: "Schedule your tour or book instantly", cta: "Continue" },
  address_revealed: { badge: "Address revealed", icon: "\uD83D\uDCCD", supporting: "Schedule your tour", cta: "Schedule Tour" },
  instant_book_requested: { badge: "Instant book in progress", icon: "\u26A1", supporting: "We're confirming your booking", cta: "View Details" },
};

const ACTION_STATUSES: EngagementStatus[] = ["agreement_sent", "tour_rescheduled", "tour_completed", "onboarding"];

const HOLD_STATUSES: EngagementStatus[] = [
  "buyer_accepted", "account_created", "guarantee_signed", "address_revealed",
  "tour_requested", "tour_confirmed", "tour_rescheduled", "tour_completed",
];

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ================================================================== */
/*  Phase 6A: BUYER DASHBOARD COMPONENT                                */
/* ================================================================== */
function BuyerDashboard({ engagements }: { engagements: Engagement[] }) {
  const router = useRouter();

  // Sort by urgency
  const sorted = useMemo(() => {
    const urgencyRank = (e: Engagement): number => {
      if (ACTION_STATUSES.includes(e.status)) return 0;
      // Hold expiring within 12 hours
      if (e.hold_expires_at) {
        const expiresMs = new Date(e.hold_expires_at).getTime();
        const hoursLeft = (expiresMs - Date.now()) / (1000 * 60 * 60);
        if (hoursLeft > 0 && hoursLeft < 12) return 1;
      }
      if (e.status === "active") return 2;
      return 3;
    };
    return [...engagements].sort((a, b) => urgencyRank(a) - urgencyRank(b));
  }, [engagements]);

  const actionNeeded = sorted.filter(e => ACTION_STATUSES.includes(e.status));

  function getStatusConfig(status: string) {
    return STATUS_CONFIG[status] || { badge: formatStatus(status), icon: "\uD83D\uDCCB", supporting: "", cta: "View Details" };
  }

  function handleCardClick(eng: Engagement) {
    if (eng.status === "expired") {
      router.push("/search");
    } else {
      router.push(`/buyer/engagements/${eng.id}`);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">
                W<span className="text-emerald-600">Ex</span>
              </h1>
              <span className="text-slate-300">|</span>
              <span className="text-sm font-medium text-slate-600">My Dashboard</span>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href="/search"
                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-semibold transition-colors"
              >
                <Search className="w-4 h-4" />
                Find More Space
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ACTION NEEDED section */}
        {actionNeeded.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <h2 className="text-sm font-bold text-amber-700 uppercase tracking-wider">Action Needed</h2>
            </div>
            <div className="space-y-3">
              {actionNeeded.map((eng) => {
                const config = getStatusConfig(eng.status);
                return (
                  <motion.div
                    key={`action-${eng.id}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    onClick={() => handleCardClick(eng)}
                    className="bg-amber-50 border-2 border-amber-200 rounded-xl p-5 cursor-pointer hover:border-amber-400 transition-all"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg">{config.icon}</span>
                          <span className="font-semibold text-slate-900">{config.badge}</span>
                        </div>
                        <p className="text-sm text-slate-600 mb-1">
                          {eng.warehouse?.name || eng.warehouse?.address || `Property ${eng.warehouseId?.slice(0, 8) || ""}`}
                        </p>
                        {eng.sqft && (
                          <p className="text-xs text-slate-500">
                            {eng.sqft.toLocaleString()} sqft
                            {eng.monthlyBuyerTotal ? ` \u00B7 $${eng.monthlyBuyerTotal.toLocaleString()}/mo` : ""}
                          </p>
                        )}
                        {config.supporting && (
                          <p className="text-xs text-amber-700 mt-2">{config.supporting}</p>
                        )}
                      </div>
                      {config.cta && (
                        <button className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-semibold shrink-0 transition-colors">
                          {config.cta}
                        </button>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        )}

        {/* ALL ENGAGEMENTS */}
        <div>
          <h2 className="text-lg font-bold text-slate-900 mb-4">Your Spaces</h2>
          <div className="space-y-3">
            {sorted.map((eng, i) => {
              const config = getStatusConfig(eng.status);
              const showHold = HOLD_STATUSES.includes(eng.status) && eng.hold_expires_at;
              return (
                <motion.div
                  key={eng.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  onClick={() => handleCardClick(eng)}
                  className="bg-white border border-slate-200 rounded-xl p-5 cursor-pointer hover:border-emerald-300 hover:shadow-sm transition-all"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      {/* Status badge */}
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-base">{config.icon}</span>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
                          {config.badge}
                        </span>
                      </div>

                      {/* Property info */}
                      <h3 className="font-semibold text-slate-900 truncate">
                        {eng.warehouse?.name || eng.warehouse?.address || `Property ${eng.warehouseId?.slice(0, 8) || ""}`}
                      </h3>
                      {eng.warehouse?.city && (
                        <p className="text-sm text-slate-500 flex items-center gap-1 mt-0.5">
                          <MapPin className="w-3 h-3" />
                          {eng.warehouse.city}{eng.warehouse.state ? `, ${eng.warehouse.state}` : ""}
                        </p>
                      )}

                      {/* Details row */}
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                        {eng.sqft && <span>{eng.sqft.toLocaleString()} sqft</span>}
                        {eng.use_type && <span>{eng.use_type}</span>}
                        {eng.monthlyBuyerTotal && <span className="font-semibold text-slate-700">${eng.monthlyBuyerTotal.toLocaleString()}/mo</span>}
                      </div>

                      {/* Supporting text */}
                      {config.supporting && (
                        <p className="text-xs text-slate-400 mt-2">{config.supporting}</p>
                      )}

                      {/* Hold countdown */}
                      {showHold && (
                        <div className="mt-2">
                          <HoldCountdown holdExpiresAt={eng.hold_expires_at} format="expires_in" />
                        </div>
                      )}
                    </div>

                    {/* CTA */}
                    <div className="shrink-0 flex flex-col items-end gap-2">
                      {config.cta && (
                        <span className="text-sm font-semibold text-emerald-600 hover:text-emerald-700 flex items-center gap-1">
                          {config.cta} <ArrowRight className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Guarantee footer */}
        <div className="mt-8 text-sm text-slate-500 flex items-center justify-center gap-1.5">
          <Shield className="w-4 h-4 text-emerald-600" />
          All WEx deals include Occupancy Guarantee. Rates are all-in, no hidden fees.
        </div>
      </main>
    </div>
  );
}

/* ================================================================== */
/*  EMPTY STATE — no engagements                                       */
/* ================================================================== */
function BuyerEmptyState() {
  return (
    <div className="max-w-2xl mx-auto text-center py-16">
      <h2 className="text-2xl font-bold text-slate-900 mb-3">Find your next warehouse space.</h2>
      <p className="text-slate-500 mb-6">
        Tell us what you need and we&apos;ll match you to available spaces in your market &mdash;
        with rates locked the moment you reserve.
      </p>
      <Link href="/search" className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition-colors">
        Find Space <ArrowRight className="w-4 h-4" />
      </Link>
      <div className="mt-8 text-sm text-slate-500 flex items-center justify-center gap-1.5">
        <Shield className="w-4 h-4 text-emerald-600" />
        All WEx deals include Occupancy Guarantee. Rates are all-in, no hidden fees.
      </div>
    </div>
  );
}

/* ================================================================== */
/*  TOP-LEVEL: THE EDITORIAL HYBRID FLOW                               */
/*  "Concierge" (Daylight Agent) vs "Collection" (Editorial Grid)      */
/*  Phase 6A: Checks for engagements first, shows dashboard if any     */
/* ================================================================== */
export default function BuyerEditorialFlow() {
  const [viewMode, setViewMode] = useState<"agent" | "grid" | "dashboard">("agent");
  const [step, setStep] = useState(1);
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [engagementsLoading, setEngagementsLoading] = useState(true);
  const [engagementsChecked, setEngagementsChecked] = useState(false);

  // SHARED STATE — persists between Agent and Grid modes
  const [intent, setIntent] = useState<BuyerIntent>({
    location: "",
    useType: "",
    goodsType: "",
    sqft: 5000,
    timing: "",
    duration: "",
    amenities: [],
  });

  // Check for existing engagements on mount
  useEffect(() => {
    async function checkEngagements() {
      try {
        const data = await api.getEngagements();
        const engList = Array.isArray(data) ? data : [];
        if (engList.length > 0) {
          setEngagements(engList);
          setViewMode("dashboard");
        }
      } catch {
        // No engagements or not logged in — show search flow
      } finally {
        setEngagementsLoading(false);
        setEngagementsChecked(true);
      }
    }
    checkEngagements();
  }, []);

  // Show loading while checking engagements
  if (engagementsLoading && !engagementsChecked) {
    return (
      <div className="h-screen w-full bg-slate-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    );
  }

  // Dashboard mode — show deal tracker
  if (viewMode === "dashboard" && engagements.length > 0) {
    return <BuyerDashboard engagements={engagements} />;
  }

  return (
    <div className="h-screen w-full bg-slate-50 text-slate-900 overflow-hidden relative font-sans selection:bg-black selection:text-white">
      {/* ═══════════════════════════════════════════════
          GLOBAL HEADER — The Mode Toggle
          ═══════════════════════════════════════════════ */}
      <div className="absolute top-0 left-0 right-0 z-50 p-6 flex justify-between items-center pointer-events-none">
        <div className="font-bold text-xl tracking-tighter pointer-events-auto text-slate-900">
          W<span className="text-emerald-600">Ex</span>
        </div>

        <button
          onClick={() => setViewMode(viewMode === "agent" ? "grid" : "agent")}
          className="pointer-events-auto bg-white/80 backdrop-blur-md border border-slate-200 text-slate-900 px-5 py-2.5 rounded-full flex items-center gap-2 hover:bg-white transition-all text-sm font-bold shadow-sm"
        >
          {viewMode === "agent" ? (
            <>
              <Grid size={16} />
              Browse Collection
            </>
          ) : (
            <>
              <MessageSquare size={16} />
              Back to Agent
            </>
          )}
        </button>
      </div>

      {/* ═══════════════════════════════════════════════
          THE TWO MODES
          ═══════════════════════════════════════════════ */}
      <AnimatePresence mode="wait">
        {viewMode === "agent" && (
          <motion.div
            key="agent-view"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="h-full w-full"
          >
            <AgentFlow
              step={step}
              setStep={setStep}
              intent={intent}
              setIntent={setIntent}
            />
          </motion.div>
        )}

        {viewMode === "grid" && (
          <motion.div
            key="grid-view"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="h-full w-full bg-white overflow-y-auto"
          >
            <EditorialGrid intent={intent} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ================================================================== */
/*  MODE A: THE DAYLIGHT AGENT (Concierge)                             */
/*  Bright, sunlit, Swiss-style — white mist overlay, dark text        */
/* ================================================================== */
function AgentFlow({
  step,
  setStep,
  intent,
  setIntent,
}: {
  step: number;
  setStep: React.Dispatch<React.SetStateAction<number>>;
  intent: BuyerIntent;
  setIntent: React.Dispatch<React.SetStateAction<BuyerIntent>>;
}) {
  const router = useRouter();
  const [idleTimer, setIdleTimer] = useState(0);
  const [, setShowSMSPrompt] = useState(false);
  const [findingMatches, setFindingMatches] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [isImmediate, setIsImmediate] = useState(false);
  const [durationMonths, setDurationMonths] = useState(6);
  const [isFlexible, setIsFlexible] = useState(false);

  // When user reaches Step 5, sync slider default into intent so "Next Step" is enabled
  useEffect(() => {
    if (step === 5 && !intent.duration) {
      setIntent((prev) => ({ ...prev, duration: `${durationMonths} Months` }));
    }
  }, [step, intent.duration, durationMonths, setIntent]);

  useEffect(() => {
    const timer = setInterval(() => {
      setIdleTimer((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (idleTimer > 15 && step < 8) {
      setShowSMSPrompt(true);
    }
  }, [idleTimer, step]);

  const resetIdle = useCallback(() => {
    setIdleTimer(0);
    setShowSMSPrompt(false);
  }, []);

  const nextStep = useCallback(() => {
    resetIdle();
    setStep((s) => s + 1);
  }, [resetIdle, setStep]);


  async function handleFindMatches() {
    setFindingMatches(true);
    resetIdle();

    // Save buyer need summary to localStorage (used as fallback by options page)
    const buyerNeed = {
      location: intent.location,
      size_sqft: `${intent.sqft.toLocaleString()} sqft`,
      use_type: USE_TYPE_LABELS[intent.useType] || intent.useType,
      goods_type: intent.goodsType || "Not specified",
      timing: intent.timing,
      duration: intent.duration || "Not specified",
      requirements: intent.amenities.join(", ") || "None specified",
      sqft_raw: String(intent.sqft),
    };
    localStorage.setItem("wex_buyer_need", JSON.stringify(buyerNeed));

    // Parse duration to months — slider gives exact values like "8 Months", or "Flexible"
    let parsedDuration = 6;
    const durationMatch = intent.duration.match(/^(\d+)\s*Month/i);
    if (durationMatch) {
      parsedDuration = parseInt(durationMatch[1]);
    } else if (intent.duration === "Flexible") {
      parsedDuration = 0; // signal to backend: no preference
    }

    // Call anonymous search — no account required
    const requirements = {
      location: intent.location,
      use_type: intent.useType,
      goods_type: intent.goodsType || undefined,
      size_sqft: intent.sqft,
      timing: intent.timing,
      duration_months: parsedDuration,
      deal_breakers: intent.amenities,
    };

    try {
      const result = await api.anonymousSearch(requirements);
      localStorage.setItem("wex_search_session", JSON.stringify(result));
      router.push(`/buyer/options?session=${result.session_token}`);
    } catch {
      // Fallback: navigate with local data only
      router.push(`/buyer/options?session=local`);
    }
  }

  // Get goods options filtered by selected use type
  const availableGoods = GOODS_TYPE_OPTIONS[intent.useType] || GOODS_TYPE_OPTIONS.storage;

  // Step labels and summaries for progress stepper
  const STEP_LABELS = ["Location", "Use Type", "Goods", "Size", "Timeline", "Must-Haves", "Review"];
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function stepSummary(stepIdx: number): string {
    switch (stepIdx) {
      case 0: return intent.location || "Location";
      case 1: return USE_TYPE_LABELS[intent.useType] || intent.useType || "Use Type";
      case 2: return intent.goodsType || "Goods";
      case 3: return intent.sqft ? `${intent.sqft.toLocaleString()} sqft` : "Size";
      case 4: {
        const parts = [];
        if (intent.timing) parts.push(intent.timing);
        if (intent.duration) parts.push(intent.duration);
        return parts.length > 0 ? parts.join(" \u00B7 ") : "Timeline";
      }
      case 5: return intent.amenities.length > 0 ? intent.amenities.slice(0, 2).join(", ") + (intent.amenities.length > 2 ? "\u2026" : "") : "Must-Haves";
      default: return STEP_LABELS[stepIdx] || "";
    }
  }

  return (
    <div className="h-full w-full relative" onClick={resetIdle}>
      {/* Daylight Cinematic Background */}
      <div className="absolute inset-0 z-0">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-100 via-white to-slate-50" />
        {/* White mist overlay for bright airy feel */}
        <div className="absolute inset-0 bg-white/30 backdrop-blur-[1px]" />
        <div className="absolute inset-0 bg-gradient-to-t from-white via-transparent to-white/50" />
        {/* Subtle warm radial glow */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-emerald-100/40 via-transparent to-transparent" />
      </div>

      {/* Breadcrumb — simple text below header */}
      {step >= 2 && (
        <div className="absolute top-[76px] left-0 right-0 z-40 flex justify-center px-6">
          <div className="bg-white rounded-full px-5 py-1.5 shadow-sm border border-slate-100 flex items-center gap-3">
            <button
              type="button"
              onClick={() => { resetIdle(); setStep((s) => Math.max(1, s - 1)); }}
              className="text-xs text-slate-400 hover:text-slate-700 transition-colors"
            >
              &#8592; Back
            </button>

            {step > 1 && intent.location && (
              <>
                <span className="text-slate-200">&#124;</span>
                <button type="button" onClick={() => { resetIdle(); setStep(1); }} className="text-xs text-slate-500 hover:text-emerald-600 transition-colors">
                  {intent.location}
                </button>
              </>
            )}
            {step > 2 && intent.useType && (
              <>
                <span className="text-slate-200">&#8250;</span>
                <button type="button" onClick={() => { resetIdle(); setStep(2); }} className="text-xs text-slate-500 hover:text-emerald-600 transition-colors">
                  {USE_TYPE_LABELS[intent.useType] || intent.useType}
                </button>
              </>
            )}
            {step > 3 && intent.goodsType && (
              <>
                <span className="text-slate-200">&#8250;</span>
                <button type="button" onClick={() => { resetIdle(); setStep(3); }} className="text-xs text-slate-500 hover:text-emerald-600 transition-colors">
                  {intent.goodsType}
                </button>
              </>
            )}
            {step > 4 && intent.sqft && (
              <>
                <span className="text-slate-200">&#8250;</span>
                <button type="button" onClick={() => { resetIdle(); setStep(4); }} className="text-xs text-slate-500 hover:text-emerald-600 transition-colors">
                  {intent.sqft.toLocaleString()} sqft
                </button>
              </>
            )}
            {step > 5 && intent.timing && (
              <>
                <span className="text-slate-200">&#8250;</span>
                <button type="button" onClick={() => { resetIdle(); setStep(5); }} className="text-xs text-slate-500 hover:text-emerald-600 transition-colors">
                  {intent.timing}
                </button>
              </>
            )}
            {step > 6 && intent.amenities.length > 0 && (
              <>
                <span className="text-slate-200">&#8250;</span>
                <button type="button" onClick={() => { resetIdle(); setStep(6); }} className="text-xs text-slate-500 hover:text-emerald-600 transition-colors">
                  {intent.amenities.length} features
                </button>
              </>
            )}

            <span className="text-slate-200">&#8250;</span>
            <span className="text-xs font-semibold text-emerald-600">{STEP_LABELS[step - 1]}</span>
          </div>
        </div>
      )}

      {/* Agent Content */}
      <div className="relative z-10 h-full flex flex-col justify-center items-center px-6 max-w-5xl mx-auto">
        <AnimatePresence mode="wait">
          {/* SCREEN 1: LOCATION */}
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="w-full text-center"
            >
              <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-slate-900 mb-6 drop-shadow-sm">
                Find warehouse space.
              </h1>
              <p className="text-xl md:text-2xl text-slate-500 font-medium mb-12 max-w-2xl mx-auto">
                Short-term or long-term. Matched in hours, not months.
              </p>

              {/* Solid White Card Input */}
              <div className="max-w-xl mx-auto relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-slate-200 to-slate-300 rounded-2xl blur opacity-40 group-hover:opacity-70 transition duration-500" />
                <div className="relative flex items-center bg-white border border-slate-200 rounded-2xl p-2 shadow-xl">
                  <input
                    autoFocus
                    type="text"
                    placeholder="City, state, zip code, or neighborhood..."
                    className="w-full bg-transparent text-xl md:text-2xl text-slate-900 placeholder:text-slate-400 px-6 py-4 outline-none font-medium"
                    value={intent.location}
                    onChange={(e) => setIntent({ ...intent, location: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && intent.location.trim()) nextStep();
                    }}
                  />
                  <button
                    onClick={() => intent.location.trim() && nextStep()}
                    className="bg-slate-900 text-white p-4 rounded-xl hover:bg-black transition-colors shadow-md"
                  >
                    <ArrowRight size={24} />
                  </button>
                </div>
              </div>

              <motion.a
                href="/buyer?login=true"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.5 }}
                className="inline-block text-slate-400 text-xs mt-8 hover:text-slate-900 transition-colors underline underline-offset-4"
              >
                Returning Buyer? Log in
              </motion.a>
            </motion.div>
          )}

          {/* SCREEN 2: USE TYPE */}
          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.05 }}
              className="w-full"
            >
              <h2 className="text-3xl md:text-5xl font-bold text-center mb-12 text-slate-900">
                What will you be doing in the space?
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
                <UsageCard icon={<Box size={32} />} title="Storage" desc="Passive storage, inventory holding." onClick={() => { setIntent({ ...intent, useType: "storage" }); nextStep(); }} />
                <UsageCard icon={<Settings size={32} />} title="Light Ops" desc="Assembly, kitting, or pick & pack." onClick={() => { setIntent({ ...intent, useType: "light_ops" }); nextStep(); }} />
                <UsageCard icon={<Truck size={32} />} title="Distribution" desc="High-volume shipping & receiving." onClick={() => { setIntent({ ...intent, useType: "distribution" }); nextStep(); }} />
              </div>
            </motion.div>
          )}

          {/* SCREEN 3: WHAT GOODS? (NEW) */}
          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.05 }}
              className="w-full"
            >
              <h2 className="text-3xl md:text-5xl font-bold text-center mb-4 text-slate-900">
                What are you storing?
              </h2>
              <p className="text-slate-500 text-center mb-12 text-lg">
                This helps us match you with properly equipped spaces.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl mx-auto">
                {availableGoods.map((g) => (
                  <div
                    key={g.label}
                    onClick={() => { setIntent({ ...intent, goodsType: g.label }); nextStep(); }}
                    className="group bg-white border border-slate-200 hover:border-emerald-500 hover:shadow-lg p-6 rounded-2xl cursor-pointer transition-all duration-300 flex items-center gap-4"
                  >
                    <div className="text-slate-400 group-hover:text-emerald-600 transition-colors flex-shrink-0">
                      {g.icon}
                    </div>
                    <h3 className="text-lg font-bold text-slate-900">{g.label}</h3>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* SCREEN 4: SIZE (enhanced with live match count) */}
          {step === 4 && (
            <motion.div
              key="step4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="w-full text-center max-w-2xl mx-auto"
            >
              <h2 className="text-3xl md:text-5xl font-bold mb-8 text-slate-900">Roughly how much space?</h2>
              <div className="bg-white border border-slate-200 rounded-3xl p-10 md:p-12 shadow-xl">
                <p className="text-3xl md:text-4xl font-light text-slate-700 mb-12">
                  &ldquo;I need around{" "}
                  <span className="text-emerald-600 font-bold border-b-2 border-emerald-500/50">
                    {intent.sqft.toLocaleString()}
                  </span>{" "}
                  sqft.&rdquo;
                </p>
                <input type="range" min="1000" max="50000" step="1000" value={intent.sqft} onChange={(e) => setIntent({ ...intent, sqft: Number(e.target.value) })} className="w-full h-3 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-600" />
                <div className="flex justify-between text-slate-400 mt-4 text-sm uppercase tracking-widest">
                  <span>1,000 sqft</span>
                  <span>50,000+ sqft</span>
                </div>

                <div className="mt-6">
                  <button onClick={nextStep} className="bg-slate-900 text-white px-8 py-3 rounded-full font-bold hover:bg-black transition-colors">Next Step</button>
                </div>
              </div>
            </motion.div>
          )}

          {/* SCREEN 5: TIMING + DURATION — Hybrid calendar / slider design */}
          {step === 5 && (
            <motion.div key="step5" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="w-full max-w-4xl mx-auto">
              <div className="text-center mb-12">
                <h2 className="text-3xl md:text-5xl font-bold text-slate-900 mb-2">Target Timeline</h2>
                <p className="text-slate-500 text-base">Precision helps us clear the best rates.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-12">

                {/* ── LEFT: START DATE ── */}
                <div>
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                    <Calendar size={16} /> Move-in Date
                  </h3>
                  <div className="space-y-4">
                    {/* "Immediately" shortcut */}
                    <button
                      onClick={() => {
                        resetIdle();
                        setIsImmediate(true);
                        setStartDate("");
                        setIntent({ ...intent, timing: "Immediately" });
                      }}
                      className={`w-full flex items-center justify-between p-4 rounded-xl border-2 transition-all ${
                        isImmediate
                          ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                          : "border-slate-200 hover:border-slate-400 bg-white"
                      }`}
                    >
                      <span className="font-bold flex items-center gap-2"><Zap size={18} /> Immediately</span>
                      {isImmediate && <div className="w-3 h-3 bg-emerald-500 rounded-full" />}
                    </button>

                    <div className="relative flex items-center justify-center">
                      <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200" /></div>
                      <span className="relative bg-slate-50 px-3 text-slate-400 text-xs font-bold uppercase tracking-widest">or</span>
                    </div>

                    {/* Calendar date picker */}
                    <div className={`relative p-4 rounded-xl border-2 transition-all ${
                      !isImmediate && startDate ? "border-emerald-500 bg-white ring-1 ring-emerald-500" : "border-slate-200 bg-white"
                    }`}>
                      <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Select a move-in date</label>
                      <input
                        type="date"
                        value={startDate}
                        min={new Date().toISOString().split("T")[0]}
                        onChange={(e) => {
                          resetIdle();
                          setStartDate(e.target.value);
                          setIsImmediate(false);
                          const d = new Date(e.target.value);
                          setIntent({ ...intent, timing: d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) });
                        }}
                        className="w-full bg-transparent font-bold text-lg text-slate-900 outline-none cursor-pointer"
                      />
                    </div>
                  </div>
                </div>

                {/* ── RIGHT: DURATION SLIDER ── */}
                <div>
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                    <Clock size={16} /> Term Length
                  </h3>

                  {/* Slider card */}
                  <div className={`bg-white rounded-2xl border-2 p-8 text-center transition-all ${
                    isFlexible ? "border-slate-200 opacity-50" : "border-emerald-500 shadow-lg"
                  }`}>
                    <motion.div
                      key={isFlexible ? "flex" : durationMonths}
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: "spring", stiffness: 300, damping: 20 }}
                      className="text-5xl font-bold text-slate-900 mb-2"
                    >
                      {isFlexible ? (
                        <span className="text-slate-400">Flexible</span>
                      ) : (
                        <>{durationMonths} <span className="text-lg text-slate-400 font-medium">{durationMonths === 1 ? "Month" : "Months"}</span></>
                      )}
                    </motion.div>

                    <input
                      type="range"
                      min="1"
                      max="36"
                      value={durationMonths}
                      onChange={(e) => {
                        resetIdle();
                        const v = parseInt(e.target.value);
                        setDurationMonths(v);
                        setIsFlexible(false);
                        setIntent({ ...intent, duration: `${v} Months` });
                      }}
                      disabled={isFlexible}
                      className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-600 mt-4"
                    />
                    <div className="flex justify-between text-xs text-slate-400 font-bold mt-2">
                      <span>1 Mo</span>
                      <span>12 Mo</span>
                      <span>24 Mo</span>
                      <span>36 Mo</span>
                    </div>
                  </div>

                  {/* "Flexible" shortcut */}
                  <button
                    onClick={() => {
                      resetIdle();
                      setIsFlexible(!isFlexible);
                      setIntent({ ...intent, duration: !isFlexible ? "Flexible" : `${durationMonths} Months` });
                    }}
                    className={`mt-4 w-full flex items-center justify-center gap-2 p-3 rounded-xl border-2 font-bold text-sm transition-all ${
                      isFlexible
                        ? "bg-slate-800 text-white border-slate-800"
                        : "bg-white text-slate-500 border-slate-200 hover:border-slate-400"
                    }`}
                  >
                    <Infinity size={16} /> I&apos;m Flexible
                  </button>
                </div>

              </div>

              {/* Continue button — enabled when both timing and duration are set */}
              <div className="text-center mt-10">
                <button
                  onClick={() => { if (intent.timing && intent.duration) nextStep(); }}
                  disabled={!intent.timing || !intent.duration}
                  className="bg-slate-900 text-white px-8 py-3 rounded-full font-bold hover:bg-black transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next Step
                </button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 6: DEAL-BREAKERS (skippable) */}
          {step === 6 && (
            <motion.div key="step6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="w-full text-center max-w-3xl mx-auto">
              <h2 className="text-3xl md:text-5xl font-bold mb-4 text-slate-900">Any deal-breakers?</h2>
              <p className="text-slate-500 mb-12">Select absolute must-haves for your space.</p>
              <div className="flex flex-wrap justify-center gap-4 mb-10">
                {DEALBREAKER_OPTIONS.map((item) => (
                  <AmenityPill key={item} label={item} selected={intent.amenities.includes(item)} onClick={() => { resetIdle(); const n = intent.amenities.includes(item) ? intent.amenities.filter((a) => a !== item) : [...intent.amenities, item]; setIntent({ ...intent, amenities: n }); }} />
                ))}
              </div>
              <div className="flex flex-col items-center gap-4">
                <button
                  onClick={nextStep}
                  className="bg-slate-900 text-white px-8 py-3 rounded-full font-bold hover:bg-black transition-colors"
                >
                  {intent.amenities.length > 0 ? "Next Step" : "Next Step"}
                </button>
                <button
                  onClick={() => { setIntent({ ...intent, amenities: [] }); nextStep(); }}
                  className="text-slate-400 text-sm hover:text-slate-600 transition-colors underline underline-offset-4"
                >
                  Skip — no deal-breakers
                </button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 7: FIND MY MATCHES (CTA) */}
          {step === 7 && (
            <motion.div
              key="step7"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="w-full text-center max-w-2xl mx-auto"
            >
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <h2 className="text-3xl md:text-5xl font-bold mb-6 text-slate-900">
                  Ready to see your matches?
                </h2>
                <p className="text-slate-500 text-lg mb-4 max-w-lg mx-auto">
                  We&apos;ll search our network for {intent.sqft.toLocaleString()} sqft of{" "}
                  <span className="text-slate-700 font-medium">{USE_TYPE_LABELS[intent.useType] || intent.useType}</span>{" "}
                  space in <span className="text-slate-700 font-medium">{intent.location}</span>.
                </p>
                {intent.goodsType && (
                  <p className="text-slate-400 text-sm mb-2">
                    Goods: {intent.goodsType} &middot; {intent.timing} &middot; {intent.duration}
                  </p>
                )}
                {intent.amenities.length > 0 && (
                  <p className="text-slate-400 text-sm mb-8">
                    Must-haves: {intent.amenities.join(", ")}
                  </p>
                )}
                {!intent.amenities.length && !intent.goodsType && <div className="mb-8" />}
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
              >
                <button
                  onClick={handleFindMatches}
                  disabled={findingMatches}
                  className="bg-emerald-600 text-white px-12 py-5 rounded-full text-xl font-bold hover:bg-emerald-700 shadow-2xl transition-all disabled:opacity-70 flex items-center gap-3 mx-auto"
                >
                  {findingMatches ? (
                    <><Loader2 size={24} className="animate-spin" />Finding Matches...</>
                  ) : (
                    <><Zap size={24} />Find My Matches</>
                  )}
                </button>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* PROGRESS DOTS */}
      {step <= 7 && (
        <div className="fixed top-20 left-0 right-0 flex justify-center z-40 pointer-events-none">
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4, 5, 6, 7].map((s) => (
              <div key={s} className={`h-1.5 rounded-full transition-all duration-500 ${s === step ? "w-8 bg-emerald-600" : s < step ? "w-1.5 bg-emerald-600/50" : "w-1.5 bg-slate-300"}`} />
            ))}
          </div>
        </div>
      )}

      {/* PERSISTENT "PREFER TO TEXT?" LINK */}
      <div className="fixed bottom-6 left-0 right-0 flex justify-center z-50 pointer-events-none">
        <motion.a
          href="sms:+18005551234"
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 2 }}
          className="pointer-events-auto text-slate-400 text-sm hover:text-slate-600 transition-colors"
        >
          Prefer to text? SMS us at (800) 555-1234
        </motion.a>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  MODE B: THE EDITORIAL GRID (Collection View)                       */
/*  White bg, magazine masonry layout, curated collection header        */
/* ================================================================== */

// Card layout patterns for the magazine grid
const CARD_LAYOUTS = [
  "md:col-span-2 aspect-[16/9]",   // Hero wide
  "aspect-[4/5]",                    // Tall
  "aspect-square",                   // Square
  "aspect-square",                   // Square
  "aspect-[4/5]",                    // Tall
  "md:col-span-2 aspect-[16/9]",   // Hero wide
  "aspect-[3/4]",                    // Tall-ish
  "aspect-square",                   // Square
];

function EditorialGrid({
  intent,
}: {
  intent: BuyerIntent;
}) {
  const router = useRouter();
  const [warehouses, setWarehouses] = useState<GridWarehouse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showMapPanel, setShowMapPanel] = useState(false);

  // Load warehouses from API + localStorage
  useEffect(() => {
    loadWarehouses();
  }, []);

  async function loadWarehouses() {
    setLoading(true);
    let results: GridWarehouse[] = [];

    // Try API
    try {
      const data = await api.getWarehouses({ status: "active" });
      const raw = Array.isArray(data) ? data : data.warehouses || [];
      results = raw.map((w: any) => ({
        id: w.id,
        name: w.name || w.owner_name || `${w.city || ""} Warehouse`,
        address: w.address || "",
        city: w.city || "",
        state: w.state || "",
        available_sqft: w.available_sqft || w.total_sqft || 0,
        supplier_rate: w.supplier_rate ?? w.supplier_rate_per_sqft ?? 0,
        image_url: w.image_url || w.primary_image_url || null,
        use_type: w.truth_core?.use_type || w.truth_core?.activity_tier || "",
      }));
    } catch { /* ignore */ }

    // Merge localStorage activated warehouses
    try {
      const stored = localStorage.getItem("wex_activated_warehouses");
      if (stored) {
        const local = JSON.parse(stored);
        const apiIds = new Set(results.map((w) => w.id));
        const localMapped: GridWarehouse[] = local
          .filter((w: any) => !apiIds.has(w.id))
          .map((w: any) => ({
            id: w.id,
            name: w.name || "Activated Warehouse",
            address: w.address || "",
            city: w.city || "",
            state: w.state || "",
            available_sqft: w.available_sqft || w.total_sqft || 0,
            supplier_rate: w.supplier_rate || 0,
            image_url: w.image_url || w.primary_image_url || null,
            use_type: w.truth_core?.use_type || "",
          }));
        results = [...results, ...localMapped];
      }
    } catch { /* ignore */ }

    // If still empty, add demo data
    if (results.length === 0) {
      results = [
        { id: "demo-1", name: "Phoenix Distribution Hub", address: "2115 S 11th Ave", city: "Phoenix", state: "AZ", available_sqft: 32000, supplier_rate: 0.75, image_url: null, use_type: "Distribution" },
        { id: "demo-2", name: "Scottsdale Flex", address: "8700 E Frank Lloyd Wright Blvd", city: "Scottsdale", state: "AZ", available_sqft: 8500, supplier_rate: 0.95, image_url: null, use_type: "Light Ops" },
        { id: "demo-3", name: "Mesa Logistics Park", address: "1455 S Power Rd", city: "Mesa", state: "AZ", available_sqft: 45000, supplier_rate: 0.68, image_url: null, use_type: "Storage" },
        { id: "demo-4", name: "Gardena Distribution", address: "15000 S Broadway", city: "Gardena", state: "CA", available_sqft: 22000, supplier_rate: 1.05, image_url: null, use_type: "Distribution" },
        { id: "demo-5", name: "North Charleston Warehouse", address: "4500 Dorchester Rd", city: "North Charleston", state: "SC", available_sqft: 55000, supplier_rate: 0.62, image_url: null, use_type: "Storage" },
      ];
    }

    setWarehouses(results);
    setLoading(false);
  }

  // Filter warehouses by location text
  const filtered = warehouses.filter((w) => {
    const locMatch =
      !intent.location.trim() ||
      `${w.city} ${w.state} ${w.address}`.toLowerCase().includes(intent.location.toLowerCase());
    const useMatch =
      !intent.useType ||
      (w.use_type || "").toLowerCase().includes(USE_TYPE_LABELS[intent.useType]?.toLowerCase() || intent.useType);
    return locMatch && useMatch;
  });

  async function handleSelectWarehouse(w: GridWarehouse) {
    const buyerRate = Math.ceil(w.supplier_rate * 1.20 * 1.06 * 100) / 100;
    const buyerNeed = {
      location: `${w.city}, ${w.state}`,
      size_sqft: `${w.available_sqft.toLocaleString()} sqft`,
      use_type: w.use_type || "Storage",
      timing: intent.timing || "Flexible",
      budget: `$${buyerRate.toFixed(2)}/sqft ($${Math.round(buyerRate * w.available_sqft).toLocaleString()}/mo)`,
      requirements: intent.amenities.join(", ") || "None specified",
      sqft_raw: String(w.available_sqft),
    };
    localStorage.setItem("wex_buyer_need", JSON.stringify(buyerNeed));

    // Call anonymous search — no account needed
    try {
      const result = await api.anonymousSearch({
        location: `${w.city}, ${w.state}`,
        use_type: w.use_type || undefined,
        size_sqft: w.available_sqft,
        timing: intent.timing || undefined,
        duration_months: 6,
      });
      localStorage.setItem("wex_search_session", JSON.stringify(result));
      router.push(`/buyer/options?session=${result.session_token}`);
    } catch {
      router.push(`/buyer/options?session=local`);
    }
  }

  // Warehouse placeholder gradient colors for cards without images
  const GRADIENTS = [
    "from-slate-200 to-slate-300",
    "from-emerald-100 to-emerald-200",
    "from-amber-100 to-amber-200",
    "from-sky-100 to-sky-200",
    "from-rose-100 to-rose-200",
    "from-violet-100 to-violet-200",
  ];

  return (
    <div className="min-h-screen pt-24 px-6 md:px-12 pb-24 max-w-7xl mx-auto">

      {/* 1. THE CONTEXT HEADER */}
      <div className="flex flex-col md:flex-row justify-between items-end mb-12 border-b border-slate-100 pb-8">
        <div>
          <p className="text-slate-400 text-xs font-bold uppercase tracking-widest mb-2">Curated Collection</p>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-slate-900">
            {filtered.length} Space{filtered.length !== 1 ? "s" : ""} in {intent.location || "All Locations"}
          </h1>
        </div>

        <div className="flex items-center gap-4 mt-6 md:mt-0">
          <button className="flex items-center gap-2 text-sm font-bold border-b border-slate-200 pb-1 hover:border-black transition-colors text-slate-700">
            <Filter size={16} /> Filter
          </button>
          <button
            onClick={() => setShowMapPanel(!showMapPanel)}
            className="flex items-center gap-2 text-sm font-bold border-b border-slate-200 pb-1 hover:border-black transition-colors text-slate-700"
          >
            <Map size={16} /> View Map
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
        </div>
      )}

      {/* Empty State */}
      {!loading && filtered.length === 0 && (
        <div className="text-center py-24">
          <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-4" />
          <p className="text-lg text-slate-500 font-medium">No spaces match your search.</p>
          <p className="text-sm text-slate-400 mt-2">Try a different location or adjust your filters.</p>
        </div>
      )}

      {/* 2. THE MAGAZINE GRID (DENT Studio Style) */}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-16">
          {filtered.map((w, i) => {
            const buyerRate = Math.ceil(w.supplier_rate * 1.20 * 1.06 * 100) / 100;
            const monthly = Math.round(buyerRate * w.available_sqft);
            const layout = CARD_LAYOUTS[i % CARD_LAYOUTS.length];
            const isHero = layout.includes("col-span-2");
            const gradient = GRADIENTS[i % GRADIENTS.length];

            return (
              <div
                key={w.id}
                className={`group cursor-pointer ${isHero ? "md:col-span-2" : ""}`}
                onClick={() => handleSelectWarehouse(w)}
              >
                {/* The Image */}
                <div className={`relative overflow-hidden rounded-lg mb-4 bg-slate-100 ${layout.replace("md:col-span-2 ", "")}`}>
                  {w.image_url ? (
                    <img
                      src={w.image_url}
                      alt={w.name}
                      className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-700"
                    />
                  ) : (
                    <div className={`w-full h-full bg-gradient-to-br ${gradient} flex items-center justify-center group-hover:scale-105 transition-transform duration-700`}>
                      <Building2 size={isHero ? 48 : 32} className="text-slate-400/50" />
                    </div>
                  )}

                  {/* Badges */}
                  {i === 0 && (
                    <div className="absolute top-4 left-4 bg-white text-black text-[10px] font-bold px-2.5 py-1 uppercase tracking-widest rounded-sm shadow-sm">
                      Instant Book
                    </div>
                  )}
                  {w.use_type && (
                    <div className="absolute top-4 right-4 bg-black/70 backdrop-blur-sm text-white text-[10px] font-bold px-2.5 py-1 uppercase tracking-widest rounded-sm">
                      {w.use_type}
                    </div>
                  )}

                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-500 flex items-center justify-center">
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                      <ArrowUpRight size={32} className="text-white drop-shadow-lg" />
                    </div>
                  </div>
                </div>

                {/* The Info */}
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className={`font-bold mb-1 group-hover:text-emerald-600 transition-colors ${isHero ? "text-2xl" : "text-lg"}`}>
                      {w.name}
                    </h3>
                    <p className="text-slate-500 text-sm">
                      {w.city}, {w.state} • {w.available_sqft.toLocaleString()} sqft
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0 ml-4">
                    <p className={`font-mono font-bold text-slate-900 ${isHero ? "text-xl" : "text-lg"}`}>
                      ${monthly.toLocaleString()}
                    </p>
                    <p className="text-xs text-slate-400">/ mo</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 3. THE FLOATING MAP BUTTON (Secondary) */}
      <div className="fixed bottom-8 right-8 z-40">
        <button
          onClick={() => setShowMapPanel(!showMapPanel)}
          className="bg-black text-white px-6 py-4 rounded-full font-bold shadow-2xl hover:scale-105 transition-transform flex items-center gap-2"
        >
          <Map size={18} /> Map View
        </button>
      </div>

      {/* 4. SLIDE-UP MAP PANEL (Optional) */}
      <AnimatePresence>
        {showMapPanel && (
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed inset-x-0 bottom-0 top-20 z-50 bg-white border-t border-slate-200 shadow-2xl rounded-t-3xl overflow-hidden"
          >
            <div className="relative h-full">
              {/* Map header */}
              <div className="absolute top-0 left-0 right-0 z-10 p-4 flex justify-between items-center bg-white/90 backdrop-blur-md border-b border-slate-100">
                <div>
                  <p className="text-xs text-slate-400 font-bold uppercase tracking-widest">Map View</p>
                  <p className="text-sm text-slate-700 font-medium">
                    {filtered.length} space{filtered.length !== 1 ? "s" : ""} near {intent.location || "you"}
                  </p>
                </div>
                <button
                  onClick={() => setShowMapPanel(false)}
                  className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full transition-colors"
                >
                  <ArrowRight size={16} className="rotate-90 text-slate-600" />
                </button>
              </div>

              {/* Map placeholder */}
              <div className="h-full bg-slate-50 flex items-center justify-center">
                <div className="absolute inset-0 opacity-20" style={{ backgroundImage: "linear-gradient(rgba(0,0,0,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.04) 1px, transparent 1px)", backgroundSize: "40px 40px" }} />

                {/* Pins on map */}
                {filtered.slice(0, 8).map((w, i) => {
                  const top = 25 + ((i * 37 + 13) % 50);
                  const left = 15 + ((i * 53 + 29) % 65);
                  const buyerRate = Math.ceil(w.supplier_rate * 1.20 * 1.06 * 100) / 100;
                  const monthly = Math.round(buyerRate * w.available_sqft);
                  return (
                    <div
                      key={w.id}
                      className="absolute z-10 group cursor-pointer"
                      style={{ top: `${top}%`, left: `${left}%` }}
                      onClick={() => handleSelectWarehouse(w)}
                    >
                      <div className="bg-black text-white text-xs font-bold px-3 py-1.5 rounded-full shadow-lg whitespace-nowrap hover:bg-emerald-600 transition-colors">
                        ${monthly.toLocaleString()}/mo
                      </div>
                      {/* Tooltip */}
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-white text-slate-900 text-xs px-3 py-2 rounded-lg border border-slate-200 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity shadow-xl pointer-events-none">
                        <p className="font-bold">{w.name}</p>
                        <p className="text-slate-500">{w.available_sqft.toLocaleString()} sqft • {w.city}</p>
                      </div>
                    </div>
                  );
                })}

                <p className="text-slate-300 text-sm font-medium">Interactive map coming soon</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ================================================================== */
/*  SHARED SUB-COMPONENTS (Light Theme)                                */
/* ================================================================== */

function UsageCard({
  icon,
  title,
  desc,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className="group bg-white border border-slate-200 hover:border-emerald-500 hover:shadow-lg p-8 rounded-2xl cursor-pointer transition-all duration-300"
    >
      <div className="text-slate-400 group-hover:text-emerald-600 mb-4 transition-colors">
        {icon}
      </div>
      <h3 className="text-2xl font-bold mb-2 text-slate-900">{title}</h3>
      <p className="text-slate-500 text-sm">{desc}</p>
    </div>
  );
}

function AmenityPill({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-6 py-3 rounded-full border text-sm font-bold transition-all ${
        selected
          ? "bg-emerald-50 border-emerald-500 text-emerald-700"
          : "bg-white border-slate-200 text-slate-500 hover:border-slate-400"
      }`}
    >
      {selected && <Check size={14} className="inline mr-2 -mt-0.5" />}
      {label}
    </button>
  );
}
