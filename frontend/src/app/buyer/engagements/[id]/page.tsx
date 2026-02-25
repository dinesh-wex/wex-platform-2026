"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { demoEngagements } from "@/lib/supplier-demo-data";
import type { Engagement, EngagementEvent, EngagementStatus } from "@/types/supplier";
import StatusBadge from "@/components/supplier/StatusBadge";
import Timeline from "@/components/supplier/Timeline";

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// States where buyer can take action
const TOUR_OUTCOME_STATUSES: EngagementStatus[] = ["tour_completed"];
const AGREEMENT_SIGN_STATUSES: EngagementStatus[] = ["agreement_sent"];
const ONBOARDING_STATUSES: EngagementStatus[] = ["onboarding"];
const PRE_TOUR_STATUSES: EngagementStatus[] = [
  "address_revealed",
  "guarantee_signed",
];

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

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  if (!engagement) {
    return <div className="p-8 text-center text-gray-500">Engagement not found.</div>;
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => router.push("/buyer/engagements")}
          className="text-sm text-blue-600 hover:underline mb-2 inline-block"
        >
          ← Back to engagements
        </button>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">
            {engagement.warehouse?.name || `Engagement ${engagementId.slice(0, 8)}`}
          </h1>
          <StatusBadge status={engagement.status} />
        </div>
        {engagement.warehouse?.address && (
          <p className="text-gray-500 mt-1">{engagement.warehouse.address}</p>
        )}
      </div>

      {/* Key details */}
      <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
        <h2 className="font-semibold mb-3">Engagement Details</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Status</span>
            <div className="font-medium">{formatStatus(engagement.status)}</div>
          </div>
          <div>
            <span className="text-gray-500">Space</span>
            <div className="font-medium">
              {engagement.sqft ? `${engagement.sqft.toLocaleString()} sq ft` : "—"}
            </div>
          </div>
          <div>
            <span className="text-gray-500">Monthly Rate</span>
            <div className="font-medium">
              {engagement.monthlyBuyerTotal
                ? `$${engagement.monthlyBuyerTotal.toLocaleString()}/mo`
                : "—"}
            </div>
          </div>
          <div>
            <span className="text-gray-500">Path</span>
            <div className="font-medium">
              {engagement.path ? formatStatus(engagement.path) : "Not selected"}
            </div>
          </div>
          {engagement.leaseStartDate && (
            <div>
              <span className="text-gray-500">Lease Start</span>
              <div className="font-medium">{engagement.leaseStartDate}</div>
            </div>
          )}
          {engagement.leaseEndDate && (
            <div>
              <span className="text-gray-500">Lease End</span>
              <div className="font-medium">{engagement.leaseEndDate}</div>
            </div>
          )}
        </div>
      </div>

      {/* Action panel — varies by status */}
      {TOUR_OUTCOME_STATUSES.includes(engagement.status) && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-5 mb-6">
          <h2 className="font-semibold mb-2">Tour Complete — What&apos;s Next?</h2>
          <p className="text-sm text-gray-600 mb-4">
            You&apos;ve completed the tour. Would you like to proceed with this space?
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => handleTourOutcome("confirmed")}
              disabled={actionLoading}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              Yes, Proceed
            </button>
            <button
              onClick={() => handleTourOutcome("passed")}
              disabled={actionLoading}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 disabled:opacity-50"
            >
              Pass
            </button>
          </div>
        </div>
      )}

      {AGREEMENT_SIGN_STATUSES.includes(engagement.status) && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 mb-6">
          <h2 className="font-semibold mb-2">Agreement Ready for Signing</h2>
          <p className="text-sm text-gray-600 mb-4">
            Review and sign the lease agreement to proceed.
          </p>
          <Link
            href={`/buyer/engagements/${engagementId}/agree`}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 inline-block"
          >
            Review & Sign Agreement
          </Link>
        </div>
      )}

      {ONBOARDING_STATUSES.includes(engagement.status) && (
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-5 mb-6">
          <h2 className="font-semibold mb-2">Onboarding</h2>
          <p className="text-sm text-gray-600 mb-4">
            Complete these steps to activate your lease.
          </p>
          <div className="space-y-2 mb-4">
            <div className="flex items-center gap-2">
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  engagement.insuranceUploaded
                    ? "bg-green-500 text-white"
                    : "bg-gray-200 text-gray-500"
                }`}
              >
                {engagement.insuranceUploaded ? "✓" : "1"}
              </span>
              <span>Insurance Documentation</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  engagement.companyDocsUploaded
                    ? "bg-green-500 text-white"
                    : "bg-gray-200 text-gray-500"
                }`}
              >
                {engagement.companyDocsUploaded ? "✓" : "2"}
              </span>
              <span>Company Documents</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  engagement.paymentMethodAdded
                    ? "bg-green-500 text-white"
                    : "bg-gray-200 text-gray-500"
                }`}
              >
                {engagement.paymentMethodAdded ? "✓" : "3"}
              </span>
              <span>Payment Method</span>
            </div>
          </div>
          <Link
            href={`/buyer/engagements/${engagementId}/onboard`}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 inline-block"
          >
            Complete Onboarding
          </Link>
        </div>
      )}

      {PRE_TOUR_STATUSES.includes(engagement.status) && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-5 mb-6">
          <h2 className="font-semibold mb-2">Choose Your Path</h2>
          <p className="text-sm text-gray-600 mb-4">
            Schedule a tour or book instantly if eligible.
          </p>
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
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
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
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Instant Book
            </button>
          </div>
        </div>
      )}

      {/* Active lease info */}
      {engagement.status === "active" && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-5 mb-6">
          <h2 className="font-semibold mb-2">Active Lease</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Monthly Payment</span>
              <div className="font-medium text-lg">
                ${engagement.monthlyBuyerTotal?.toLocaleString() || "—"}/mo
              </div>
            </div>
            <div>
              <span className="text-gray-500">Lease Period</span>
              <div className="font-medium">
                {engagement.leaseStartDate || "—"} → {engagement.leaseEndDate || "Ongoing"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Decline button for eligible states */}
      {!["completed", "declined_by_buyer", "declined_by_supplier", "expired", "active", "deal_ping_expired", "deal_ping_declined"].includes(
        engagement.status
      ) && (
        <div className="mb-6">
          <button
            onClick={handleDecline}
            disabled={actionLoading}
            className="text-sm text-red-600 hover:text-red-800 disabled:opacity-50"
          >
            Decline this engagement
          </button>
        </div>
      )}

      {/* Timeline */}
      {timeline.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-5">
          <h2 className="font-semibold mb-3">Timeline</h2>
          <Timeline events={timeline.map((e) => ({
            id: e.id,
            type: e.eventType,
            description: `${e.eventType.replace(/_/g, " ")}${e.actor ? ` (${e.actor})` : ""}`,
            timestamp: e.createdAt,
            completed: true,
            actor: e.actor,
          }))} />
        </div>
      )}
    </div>
  );
}
