'use client';

import React from 'react';
import CountUp from 'react-countup';

interface StickyScoreboardProps {
  revenue: number;
  previousRevenue: number;
}

export default function StickyScoreboard({
  revenue,
  previousRevenue,
}: StickyScoreboardProps) {
  return (
    <div className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200 px-6 py-4 flex justify-between items-center shadow-sm">
      <span className="text-slate-500 font-medium">Est Additional Annual Income</span>
      <span className="text-3xl font-bold text-emerald-600 font-mono">
        $<CountUp start={previousRevenue} end={revenue} duration={1} separator="," />
      </span>
    </div>
  );
}
