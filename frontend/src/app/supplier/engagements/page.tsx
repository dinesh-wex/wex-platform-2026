"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { demoEngagements } from "@/lib/supplier-demo-data";
import type { Engagement, EngagementStatus } from "@/types/supplier";
import TabBar from "@/components/supplier/TabBar";
import StatusBadge from "@/components/supplier/StatusBadge";

// =============================================================================
// Tab filter definitions (24-status spec)
// =============================================================================

type TabKey = "action_needed" | "active" | "in_progress" | "past";

const ACTION_NEEDED_STATUSES: EngagementStatus[] = [
  "deal_ping_sent",
  "tour_requested",
  "tour_rescheduled",
  "agreement_sent",
];

const ACTIVE_STATUSES: EngagementStatus[] = ["active"];

const IN_PROGRESS_STATUSES: EngagementStatus[] = [
  "deal_ping_accepted",
  "matched",
  "buyer_reviewing",
  "buyer_accepted",
  "account_created",
  "guarantee_signed",
  "address_revealed",
  "tour_confirmed",
  "instant_book_requested",
  "tour_completed",
  "buyer_confirmed",
  "agreement_signed",
  "onboarding",
];

const PAST_STATUSES: EngagementStatus[] = [
  "completed",
  "declined_by_buyer",
  "declined_by_supplier",
  "expired",
  "deal_ping_expired",
  "deal_ping_declined",
];

function filterByTab(engagements: Engagement[], tab: TabKey): Engagement[] {
  switch (tab) {
    case "action_needed":
      return engagements.filter((e) => ACTION_NEEDED_STATUSES.includes(e.status));
    case "active":
      return engagements.filter((e) => ACTIVE_STATUSES.includes(e.status));
    case "in_progress":
      return engagements.filter((e) => IN_PROGRESS_STATUSES.includes(e.status));
    case "past":
      return engagements.filter((e) => PAST_STATUSES.includes(e.status));
    default:
      return [];
  }
}

// =============================================================================
// Empty state messages
// =============================================================================

const EMPTY_MESSAGES: Record<TabKey, string> = {
  action_needed: "All caught up -- no actions needed right now.",
  active: "No active engagements yet. Accepted matches will appear here.",
  in_progress: "No engagements in progress.",
  past: "No past engagements.",
};

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
  // "eng-1234" => "1234", fallback to full id
  const match = id.match(/(\d+)/);
  return match ? match[1] : id;
}

function formatTourDate(date?: string, time?: string): string {
  if (!date) return "";
  const d = new Date(date + "T00:00:00");
  const dateStr = d.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
  });
  return time ? `${dateStr}, ${time}` : dateStr;
}

// =============================================================================
// Engagement Card
// =============================================================================

function EngagementCard({
  engagement,
  showActions,
  onAccept,
}: {
  engagement: Engagement;
  showActions: boolean;
  onAccept: (id: string) => void;
}) {
  const router = useRouter();

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
      onClick={() => router.push(`/supplier/engagements/${engagement.id}`)}
      className="bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow cursor-pointer border border-slate-100 p-5"
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-900">
          Engagement #{shortId(engagement.id)}
        </h3>
        <StatusBadge status={engagement.status} size="sm" />
      </div>

      {/* Property info */}
      <p className="text-sm text-slate-600 mb-2">
        {engagement.property_address.split(",")[0]} &middot;{" "}
        {engagement.sqft.toLocaleString()} sqft &middot;{" "}
        <span className="capitalize">{engagement.use_type}</span>
      </p>

      {/* Financial details */}
      <p className="text-sm text-slate-600 mb-1">
        Your Rate: {fmtRate(engagement.supplier_rate)}/sqft &middot; Monthly:{" "}
        {fmtCurrency(engagement.monthly_payout)}
      </p>
      <p className="text-sm text-slate-500 mb-3">
        Term: {engagement.term_months} months &middot; Total:{" "}
        {fmtCurrency(engagement.total_value)}
      </p>

      {/* Tour info */}
      {engagement.tour_date && (
        <p className="text-sm text-slate-600 mb-2">
          Tour: {formatTourDate(engagement.tour_date, engagement.tour_time)}
          {engagement.tour_confirmed ? (
            <span className="text-emerald-600 ml-1">-- Confirmed</span>
          ) : (
            <span className="text-amber-600 ml-1">-- Awaiting Confirmation</span>
          )}
        </p>
      )}

      {/* Next step */}
      {engagement.next_step && (
        <p className="text-xs text-slate-500 mb-3">
          Next step: {engagement.next_step}
        </p>
      )}

      {/* Action buttons (only on Action Needed tab) */}
      {showActions && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-slate-100">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAccept(engagement.id);
            }}
            className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors"
          >
            Accept
          </button>
        </div>
      )}
    </motion.div>
  );
}

// =============================================================================
// Main Page
// =============================================================================

export default function EngagementsPage() {
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>("action_needed");

  // ---- Fetch engagements ----
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await api.getEngagements();
        if (!cancelled) {
          setEngagements(Array.isArray(data) ? data : data.engagements ?? []);
        }
      } catch {
        if (!cancelled) setEngagements(demoEngagements);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // ---- Filtered list ----
  const filtered = useMemo(
    () => filterByTab(engagements, activeTab),
    [engagements, activeTab],
  );

  // ---- Tab counts ----
  const tabs = useMemo(
    () => [
      {
        key: "action_needed",
        label: "Action Needed",
        count: filterByTab(engagements, "action_needed").length,
      },
      {
        key: "active",
        label: "Active",
        count: filterByTab(engagements, "active").length,
      },
      {
        key: "in_progress",
        label: "In Progress",
        count: filterByTab(engagements, "in_progress").length,
      },
      {
        key: "past",
        label: "Past",
        count: filterByTab(engagements, "past").length,
      },
    ],
    [engagements],
  );

  // ---- Quick actions (optimistic) ----
  const handleAccept = useCallback(
    async (id: string) => {
      // Capture original status before optimistic update
      const originalStatus = engagements.find((e) => e.id === id)?.status;
      // Optimistic update
      setEngagements((prev) =>
        prev.map((e) => (e.id === id ? { ...e, status: "deal_ping_accepted" as EngagementStatus } : e)),
      );
      try {
        await api.respondToEngagement(id, { action: "accept" });
      } catch {
        // Revert on failure to original status
        if (originalStatus) {
          setEngagements((prev) =>
            prev.map((e) => (e.id === id ? { ...e, status: originalStatus } : e)),
          );
        }
      }
    },
    [engagements],
  );

  // ---- Loading skeleton ----
  if (loading) {
    return (
      <div className="bg-slate-50 min-h-screen p-6 lg:p-10">
        <div className="max-w-4xl mx-auto space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white rounded-xl h-40 animate-pulse border border-slate-100"
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-50 min-h-screen">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-10 py-8 lg:py-10">
        {/* ---- Page header ---- */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">Engagements</h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage inquiries, tours, and active leases across your portfolio.
          </p>
        </div>

        {/* ---- Tabs ---- */}
        <TabBar
          tabs={tabs}
          activeTab={activeTab}
          onChange={(key) => setActiveTab(key as TabKey)}
        />

        {/* ---- Tab content ---- */}
        <div className="mt-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              {filtered.length === 0 ? (
                <div className="text-center py-16">
                  <p className="text-slate-400 text-sm">
                    {EMPTY_MESSAGES[activeTab]}
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <AnimatePresence>
                    {filtered.map((engagement) => (
                      <EngagementCard
                        key={engagement.id}
                        engagement={engagement}
                        showActions={activeTab === "action_needed"}
                        onAccept={handleAccept}
                      />
                    ))}
                  </AnimatePresence>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
