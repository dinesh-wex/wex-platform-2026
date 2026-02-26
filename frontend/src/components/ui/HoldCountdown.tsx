"use client";

import { useState, useEffect } from "react";

interface HoldCountdownProps {
  holdExpiresAt: string | null | undefined;
  format?: "held_for" | "expires_in" | "held_until";
  className?: string;
}

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function HoldCountdown({
  holdExpiresAt,
  format = "held_for",
  className = "",
}: HoldCountdownProps) {
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

  useEffect(() => {
    if (!holdExpiresAt) return;

    function calcRemaining() {
      const expiresMs = new Date(holdExpiresAt!).getTime();
      const nowMs = Date.now();
      return Math.max(0, Math.floor((expiresMs - nowMs) / 1000));
    }

    setSecondsLeft(calcRemaining());

    const interval = setInterval(() => {
      const remaining = calcRemaining();
      setSecondsLeft(remaining);
      if (remaining <= 0) {
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [holdExpiresAt]);

  if (!holdExpiresAt) return null;
  if (secondsLeft === null) return null;

  const fourHoursInSeconds = 4 * 60 * 60;
  const isUrgent = secondsLeft > 0 && secondsLeft < fourHoursInSeconds;
  const isExpired = secondsLeft <= 0;

  const colorClass = isExpired
    ? "text-red-500"
    : isUrgent
    ? "text-red-500"
    : "text-slate-300";

  if (isExpired) {
    return (
      <span className={`text-sm font-medium text-red-500 ${className}`}>
        Hold expired
      </span>
    );
  }

  const duration = formatDuration(secondsLeft);

  if (format === "held_for") {
    return (
      <span className={`text-sm font-medium ${colorClass} ${className}`}>
        <span role="img" aria-label="lock">🔒</span> Held for {duration}
      </span>
    );
  }

  if (format === "expires_in") {
    return (
      <span className={`text-sm font-medium ${colorClass} ${className}`}>
        <span role="img" aria-label="lock">🔒</span> Hold expires in {duration}
      </span>
    );
  }

  // held_until
  return (
    <span className={`text-sm font-medium ${colorClass} ${className}`}>
      <span role="img" aria-label="lock">🔒</span> Space held until {formatDate(holdExpiresAt)}
    </span>
  );
}
