'use client';

import React from 'react';
import { motion } from 'framer-motion';

interface SelectionCardProps {
  selected: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  desc: string;
  badge?: string;
}

export default function SelectionCard({
  selected,
  onClick,
  icon,
  title,
  desc,
  badge,
}: SelectionCardProps) {
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className={`relative p-5 rounded-xl border-2 cursor-pointer transition-all ${
        selected
          ? 'border-emerald-500 bg-emerald-50'
          : 'border-slate-100 hover:border-slate-200 bg-white'
      }`}
    >
      {badge && (
        <div className="absolute -top-3 -right-3 bg-emerald-500 text-white text-xs font-bold px-2 py-1 rounded-full shadow-sm">
          {badge}
        </div>
      )}
      <div
        className={`mb-3 ${selected ? 'text-emerald-600' : 'text-slate-400'}`}
      >
        {icon}
      </div>
      <div className="font-bold text-slate-900">{title}</div>
      <div className="text-xs text-slate-500 mt-1 leading-relaxed">{desc}</div>
    </motion.div>
  );
}
