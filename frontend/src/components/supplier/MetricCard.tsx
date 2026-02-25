"use client";

import { motion } from "framer-motion";
import CountUp from "react-countup";

interface MetricCardProps {
  label: string;
  value: number;
  prefix?: string;
  suffix?: string;
  sublabel?: string;
  format?: "currency" | "number" | "percent";
  className?: string;
  hero?: boolean;
}

export default function MetricCard({
  label,
  value,
  prefix,
  suffix,
  sublabel,
  format = "number",
  className = "",
  hero = false,
}: MetricCardProps) {
  const countUpProps = (() => {
    switch (format) {
      case "currency":
        return {
          decimals: 0,
          prefix: prefix ?? "$",
          suffix: suffix ?? "",
          separator: ",",
        };
      case "percent":
        return {
          decimals: 0,
          prefix: prefix ?? "",
          suffix: suffix ?? "%",
          separator: ",",
        };
      default:
        return {
          decimals: 0,
          prefix: prefix ?? "",
          suffix: suffix ?? "",
          separator: ",",
        };
    }
  })();

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className={`rounded-xl shadow-sm p-6 hover:shadow-md transition-shadow ${
        hero
          ? "bg-gradient-to-br from-white to-emerald-50/40"
          : "bg-white"
      } ${className}`}
    >
      <p className="text-sm text-slate-500 uppercase tracking-wide font-medium">
        {label}
      </p>

      <p className={`font-bold mt-1 ${
        hero ? "text-5xl text-emerald-600" : "text-3xl text-slate-900"
      }`}>
        <CountUp end={value} duration={1.6} {...countUpProps} />
      </p>

      {sublabel && (
        <p className="text-xs text-slate-400 mt-1">{sublabel}</p>
      )}
    </motion.div>
  );
}
