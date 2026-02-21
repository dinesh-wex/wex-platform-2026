'use client';

import React from 'react';

interface FeaturePillProps {
  icon: React.ReactNode;
  label: string;
}

export default function FeaturePill({ icon, label }: FeaturePillProps) {
  return (
    <div className="bg-white/10 backdrop-blur-sm border border-white/10 rounded-lg py-2 px-3 flex items-center gap-2 text-white/90 text-xs font-medium">
      {icon} <span>{label}</span>
    </div>
  );
}
