'use client';

import React from 'react';
import { motion } from 'framer-motion';

interface ToggleProps {
  active: boolean;
  onToggle: () => void;
  label?: string;
  description?: string;
  badge?: string;
}

export default function Toggle({
  active,
  onToggle,
  label,
  description,
  badge,
}: ToggleProps) {
  return (
    <div
      onClick={onToggle}
      className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 cursor-pointer hover:shadow-md transition-shadow"
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-slate-900">{label}</h3>
            {badge && (
              <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                {badge}
              </span>
            )}
          </div>
          {description && (
            <p className="text-slate-500 text-sm mt-0.5">{description}</p>
          )}
        </div>
        <div
          className={`w-14 h-8 flex items-center rounded-full p-1 transition-colors ${
            active ? 'bg-emerald-500' : 'bg-slate-200'
          }`}
        >
          <motion.div
            layout
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            className={`w-6 h-6 rounded-full shadow-md ${
              active ? 'bg-white ml-auto' : 'bg-white'
            }`}
          />
        </div>
      </div>
    </div>
  );
}
