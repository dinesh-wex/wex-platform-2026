"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { demoEngagements } from "@/lib/supplier-demo-data";
import type { Engagement, EngagementStatus } from "@/types/supplier";
import StatusBadge from "@/components/supplier/StatusBadge";

// =============================================================================
// Tab filter definitions — buyer perspective
// =============================================================================

type TabKey = "active_searches" | "in_progress" | "active_leases" | "past";

const ACTIVE_SEARCH_STATUSES: EngagementStatus[] = [
  "deal_ping_sent",
  "deal_ping_accepted",
  "matched",
  "buyer_reviewing",
];

const IN_PROGRESS_STATUSES: EngagementStatus[] = [
  "buyer_accepted",
  "account_created",
  "guarantee_signed",
  "address_revealed",
  "tour_requested",
  "tour_confirmed",
  "tour_rescheduled",
  "instant_book_requested",
  "tour_completed",
  "buyer_confirmed",
  "agreement_sent",
  "agreement_signed",
  "onboarding",
];

const ACTIVE_LEASE_STATUSES: EngagementStatus[] = ["active"];

const PAST_STATUSES: EngagementStatus[] = [
  "completed",
  "declined_by_buyer",
  "declined_by_supplier",
  "expired",
  "deal_ping_expired",
  "deal_ping_declined",
];

const TABS: { key: TabKey; label: string }[] = [
  { key: "active_searches", label: "Active Searches" },
  { key: "in_progress", label: "In Progress" },
  { key: "active_leases", label: "Active Leases" },
  { key: "past", label: "Past" },
];

function getTabForStatus(status: EngagementStatus): TabKey {
  if (ACTIVE_SEARCH_STATUSES.includes(status)) return "active_searches";
  if (IN_PROGRESS_STATUSES.includes(status)) return "in_progress";
  if (ACTIVE_LEASE_STATUSES.includes(status)) return "active_leases";
  return "past";
}

function formatStatus(status: string): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function BuyerEngagementsPage() {
  const router = useRouter();
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>("in_progress");
  const [loading, setLoading] = useState(true);

  const loadEngagements = useCallback(async () => {
    try {
      const data = await api.getEngagements();
      setEngagements(data);
    } catch {
      setEngagements(demoEngagements);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEngagements();
  }, [loadEngagements]);

  const filtered = useMemo(() => {
    const statusSet =
      activeTab === "active_searches"
        ? ACTIVE_SEARCH_STATUSES
        : activeTab === "in_progress"
          ? IN_PROGRESS_STATUSES
          : activeTab === "active_leases"
            ? ACTIVE_LEASE_STATUSES
            : PAST_STATUSES;
    return engagements.filter((e) => statusSet.includes(e.status));
  }, [engagements, activeTab]);

  const counts = useMemo(() => {
    const c: Record<TabKey, number> = {
      active_searches: 0,
      in_progress: 0,
      active_leases: 0,
      past: 0,
    };
    engagements.forEach((e) => {
      const tab = getTabForStatus(e.status);
      c[tab]++;
    });
    return c;
  }, [engagements]);

  if (loading) {
    return (
      <div className="p-8 text-center text-gray-500">
        Loading engagements...
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">My Engagements</h1>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === tab.key
                ? "bg-white border border-b-white border-gray-200 text-blue-600 -mb-px"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {counts[tab.key] > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">
                {counts[tab.key]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Engagement list */}
      {filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No engagements in this tab.
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((eng) => (
            <div
              key={eng.id}
              onClick={() => router.push(`/buyer/engagements/${eng.id}`)}
              className="bg-white border border-gray-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-sm cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-semibold text-gray-900">
                      {eng.warehouse?.name || `Property ${eng.warehouseId?.slice(0, 8)}`}
                    </span>
                    <StatusBadge status={eng.status} />
                  </div>
                  <div className="text-sm text-gray-500">
                    {eng.sqft ? `${eng.sqft.toLocaleString()} sq ft` : ""}
                    {eng.buyerRateSqft ? ` · $${eng.buyerRateSqft}/sq ft` : ""}
                    {eng.monthlyBuyerTotal
                      ? ` · $${eng.monthlyBuyerTotal.toLocaleString()}/mo`
                      : ""}
                  </div>
                </div>
                <div className="text-sm text-gray-400">
                  {formatStatus(eng.status)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
