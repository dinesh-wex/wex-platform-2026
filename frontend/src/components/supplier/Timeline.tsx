"use client";

import { motion } from "framer-motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TimelineEvent {
  id: string;
  type?: string;
  description: string;
  timestamp: string;
  completed: boolean;
  metadata?: Record<string, unknown>;
  actor?: 'buyer' | 'supplier' | 'admin' | 'system';
}

interface TimelineProps {
  events: TimelineEvent[];
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(raw: string): string {
  const date = new Date(raw);
  const now = new Date();
  const sameYear = date.getFullYear() === now.getFullYear();

  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });

  // If the time is midnight exactly, treat it as a date-only event
  if (date.getHours() === 0 && date.getMinutes() === 0) {
    return dateStr;
  }

  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  return `${dateStr}, ${timeStr}`;
}

// ---------------------------------------------------------------------------
// Dot component
// ---------------------------------------------------------------------------

function Dot({ status }: { status: "completed" | "current" | "upcoming" }) {
  if (status === "completed") {
    return (
      <span className="relative z-10 block w-3 h-3 rounded-full bg-emerald-500" />
    );
  }

  if (status === "current") {
    return (
      <span className="relative z-10 flex items-center justify-center w-3 h-3">
        {/* Pulse ring */}
        <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
        <span className="relative block w-3 h-3 rounded-full bg-emerald-500" />
      </span>
    );
  }

  // Upcoming
  return (
    <span className="relative z-10 block w-3 h-3 rounded-full bg-white border-2 border-slate-300" />
  );
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

export default function Timeline({ events, className = "" }: TimelineProps) {
  // Determine the index of the first non-completed event (the "current" one)
  const currentIdx = events.findIndex((e) => !e.completed);

  return (
    <div className={`relative ${className}`}>
      {/* Vertical line */}
      <div className="absolute left-[5px] top-2 bottom-2 w-0.5 bg-slate-200" />

      <div className="space-y-6">
        {events.map((event, idx) => {
          const status: "completed" | "current" | "upcoming" =
            event.completed
              ? "completed"
              : idx === currentIdx
                ? "current"
                : "upcoming";

          return (
            <motion.div
              key={event.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{
                duration: 0.35,
                delay: idx * 0.07,
                ease: "easeOut",
              }}
              className="relative flex items-start gap-4 pl-7"
            >
              {/* Dot — positioned on the vertical line */}
              <div className="absolute left-0 top-1">
                <Dot status={status} />
              </div>

              {/* Content */}
              <div className="min-w-0 flex-1">
                <p
                  className={`text-base leading-snug ${
                    status === "upcoming"
                      ? "text-slate-400"
                      : "text-slate-900"
                  }`}
                >
                  {event.description}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <p className="text-sm text-slate-500">
                    {formatTimestamp(event.timestamp)}
                  </p>
                  {event.actor && (
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                      event.actor === 'buyer' ? 'bg-blue-50 text-blue-600' :
                      event.actor === 'supplier' ? 'bg-emerald-50 text-emerald-600' :
                      event.actor === 'admin' ? 'bg-purple-50 text-purple-600' :
                      'bg-slate-100 text-slate-500'
                    }`}>
                      {event.actor}
                    </span>
                  )}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
