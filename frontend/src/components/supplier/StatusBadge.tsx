"use client";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

type ColorScheme = {
  bg: string;
  text: string;
};

const statusColors: Record<string, ColorScheme> = {
  // ---- Action needed (amber/yellow) ----
  deal_ping_sent: { bg: "bg-amber-50", text: "text-amber-700" },
  tour_requested: { bg: "bg-amber-50", text: "text-amber-700" },
  tour_rescheduled: { bg: "bg-amber-50", text: "text-amber-700" },
  agreement_sent: { bg: "bg-amber-50", text: "text-amber-700" },

  // ---- Success / active (green) ----
  active: { bg: "bg-emerald-50", text: "text-emerald-700" },
  deal_ping_accepted: { bg: "bg-emerald-50", text: "text-emerald-700" },
  tour_confirmed: { bg: "bg-emerald-50", text: "text-emerald-700" },
  agreement_signed: { bg: "bg-emerald-50", text: "text-emerald-700" },
  buyer_confirmed: { bg: "bg-emerald-50", text: "text-emerald-700" },

  // ---- In progress (blue) ----
  matched: { bg: "bg-blue-50", text: "text-blue-700" },
  buyer_reviewing: { bg: "bg-blue-50", text: "text-blue-700" },
  buyer_accepted: { bg: "bg-blue-50", text: "text-blue-700" },
  contact_captured: { bg: "bg-blue-50", text: "text-blue-700" },
  guarantee_signed: { bg: "bg-blue-50", text: "text-blue-700" },
  address_revealed: { bg: "bg-blue-50", text: "text-blue-700" },
  instant_book_requested: { bg: "bg-blue-50", text: "text-blue-700" },
  tour_completed: { bg: "bg-blue-50", text: "text-blue-700" },
  onboarding: { bg: "bg-blue-50", text: "text-blue-700" },

  // ---- Completed (gray) ----
  completed: { bg: "bg-slate-100", text: "text-slate-700" },

  // ---- Negative (red) ----
  declined_by_buyer: { bg: "bg-red-50", text: "text-red-700" },
  declined_by_supplier: { bg: "bg-red-50", text: "text-red-700" },
  cancelled: { bg: "bg-red-50", text: "text-red-700" },
  expired: { bg: "bg-red-50", text: "text-red-700" },
  deal_ping_expired: { bg: "bg-red-50", text: "text-red-700" },
  deal_ping_declined: { bg: "bg-red-50", text: "text-red-700" },

  // ---- Non-engagement statuses (backward compat) ----
  in_network: { bg: "bg-emerald-50", text: "text-emerald-700" },
  live: { bg: "bg-emerald-50", text: "text-emerald-700" },
  deposited: { bg: "bg-emerald-50", text: "text-emerald-700" },
  in_network_paused: { bg: "bg-amber-50", text: "text-amber-700" },
  paused: { bg: "bg-amber-50", text: "text-amber-700" },
  pending: { bg: "bg-blue-50", text: "text-blue-700" },
  invited: { bg: "bg-blue-50", text: "text-blue-700" },
  scheduled: { bg: "bg-blue-50", text: "text-blue-700" },
  failed: { bg: "bg-red-50", text: "text-red-700" },
};

const defaultColor: ColorScheme = { bg: "bg-slate-100", text: "text-slate-700" };

const displayNames: Record<string, string> = {
  deal_ping_sent: "New Inquiry",
  deal_ping_accepted: "Inquiry Accepted",
  deal_ping_expired: "Inquiry Expired",
  deal_ping_declined: "Inquiry Declined",
  matched: "Matched",
  buyer_reviewing: "Buyer Reviewing",
  buyer_accepted: "Buyer Accepted",
  contact_captured: "Contact Captured",
  guarantee_signed: "Guarantee Signed",
  address_revealed: "Address Revealed",
  tour_requested: "Tour Requested",
  tour_confirmed: "Tour Confirmed",
  tour_rescheduled: "Tour Rescheduled",
  instant_book_requested: "Instant Book Requested",
  tour_completed: "Tour Completed",
  buyer_confirmed: "Buyer Confirmed",
  agreement_sent: "Agreement Sent",
  agreement_signed: "Agreement Signed",
  onboarding: "Onboarding",
  active: "Active",
  completed: "Completed",
  declined_by_buyer: "Declined by Buyer",
  declined_by_supplier: "Declined by Supplier",
  cancelled: "Cancelled",
  expired: "Expired",
  // Non-engagement
  in_network: "In Network",
  in_network_paused: "Paused",
};

function formatStatus(status: string): string {
  if (!status) return "Unknown";
  if (displayNames[status]) return displayNames[status];
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const color = statusColors[status] ?? defaultColor;

  const sizeClasses =
    size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${color.bg} ${color.text} ${sizeClasses}`}
    >
      {formatStatus(status)}
    </span>
  );
}
