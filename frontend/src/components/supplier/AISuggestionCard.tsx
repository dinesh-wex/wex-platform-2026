"use client";

import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";
import { AISuggestion } from "@/types/supplier";

/** Fix "1 properties" → "1 property", "1 warehouses" → "1 warehouse", etc. */
function fixPluralization(text: string): string {
  return text.replace(/\b1\s+(properties|warehouses|facilities|buildings|listings)\b/gi, (_match, word) => {
    const singular: Record<string, string> = {
      properties: "property",
      warehouses: "warehouse",
      facilities: "facility",
      buildings: "building",
      listings: "listing",
    };
    return `1 ${singular[word.toLowerCase()] || word}`;
  });
}

interface AISuggestionCardProps {
  suggestion: AISuggestion;
  onAction?: () => void;
  onDismiss?: () => void;
}

export default function AISuggestionCard({
  suggestion,
  onAction,
}: AISuggestionCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="relative overflow-hidden rounded-xl bg-gradient-to-br from-emerald-50 via-white to-teal-50/60 border border-emerald-100 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
      onClick={onAction}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter") onAction?.(); }}
    >
      <div className="p-5">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0 rounded-lg bg-emerald-100/80 p-2">
            <TrendingUp className="h-4 w-4 text-emerald-600" />
          </div>

          <div className="min-w-0 flex-1">
            <h4 className="text-sm font-semibold text-slate-900">
              {fixPluralization(suggestion.title)}
            </h4>
            <p className="mt-1 text-sm text-slate-600 leading-relaxed">
              {fixPluralization(suggestion.description)}
            </p>

            <button
              type="button"
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors"
              onClick={(e) => { e.stopPropagation(); onAction?.(); }}
            >
              {suggestion.action_label || "Take Action"}
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
