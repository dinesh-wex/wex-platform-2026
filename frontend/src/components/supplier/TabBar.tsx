"use client";

import { useRef } from "react";
import { motion } from "framer-motion";

interface TabBarProps {
  tabs: { key: string; label: string; count?: number }[];
  activeTab: string;
  onChange: (key: string) => void;
}

export default function TabBar({ tabs, activeTab, onChange }: TabBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={scrollRef}
      className="relative flex overflow-x-auto border-b border-slate-200 scrollbar-hide"
    >
      {tabs.map((tab) => {
        const isActive = tab.key === activeTab;

        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`relative flex shrink-0 items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? "text-emerald-600"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab.label}

            {tab.count !== undefined && (
              <span
                className={`inline-flex items-center justify-center rounded-full px-1.5 text-xs font-medium ${
                  isActive
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {tab.count}
              </span>
            )}

            {isActive && (
              <motion.div
                layoutId="tab-indicator"
                className="absolute inset-x-0 -bottom-px h-0.5 bg-emerald-500"
                transition={{ type: "spring", stiffness: 500, damping: 35 }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
