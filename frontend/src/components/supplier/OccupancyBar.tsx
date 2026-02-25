"use client";

import { motion } from "framer-motion";

interface OccupancyBarProps {
  rentedSqft: number;
  availableSqft: number;
  className?: string;
}

function formatSqft(n: number): string {
  return n.toLocaleString();
}

export default function OccupancyBar({
  rentedSqft,
  availableSqft,
  className = "",
}: OccupancyBarProps) {
  const totalSqft = rentedSqft + availableSqft;
  const pct = totalSqft > 0 ? Math.round((rentedSqft / totalSqft) * 100) : 0;

  let label: string;
  if (totalSqft === 0) {
    label = "Set your available space";
  } else if (pct === 100) {
    label = "Fully occupied";
  } else if (rentedSqft === 0) {
    label = "Finding tenants\u2026";
  } else {
    label = `${formatSqft(rentedSqft)} sqft rented \u00B7 ${formatSqft(availableSqft)} sqft available`;
  }

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full bg-emerald-500"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        </div>
        <span className="shrink-0 text-xs font-medium text-slate-600">
          {pct}%
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{label}</p>
    </div>
  );
}
