"use client";

import { motion } from "framer-motion";
import { ActionItem } from "@/types/supplier";

interface ActionCardProps {
  action: ActionItem;
  onAction?: () => void;
}

const urgencyBorderColor: Record<ActionItem["urgency"], string> = {
  high: "border-l-red-500",
  medium: "border-l-amber-500",
  low: "border-l-blue-500",
};

function formatDeadline(deadline: string): string {
  const now = new Date();
  const due = new Date(deadline);
  const diffMs = due.getTime() - now.getTime();
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));

  if (diffHours <= 0) return "Due now";
  if (diffHours < 1) return "Due in less than 1 hour";
  if (diffHours < 24) return `Due in ${diffHours} hour${diffHours === 1 ? "" : "s"}`;

  const diffDays = Math.round(diffHours / 24);
  if (diffDays === 0) return "Due today";
  if (diffDays === 1) return "Due tomorrow";
  return `Due in ${diffDays} days`;
}

export default function ActionCard({ action, onAction }: ActionCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`flex items-center justify-between gap-4 rounded-lg border-l-4 bg-white p-4 shadow-sm transition-shadow hover:shadow-md ${urgencyBorderColor[action.urgency]}`}
    >
      <div className="min-w-0 flex-1">
        <h4 className="font-bold text-slate-900">{action.title}</h4>
        <p className="mt-0.5 text-sm text-slate-600">{action.description}</p>
        {action.deadline && (
          <p className="mt-1 text-xs font-medium text-slate-500">
            {formatDeadline(action.deadline)}
          </p>
        )}
      </div>

      <button
        onClick={onAction}
        className="shrink-0 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-600"
      >
        {action.action_label}
      </button>
    </motion.div>
  );
}
