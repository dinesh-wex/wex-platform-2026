'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Building2 } from 'lucide-react';

interface PhaseRejectionProps {
  address: string;
  onTryAgain: () => void;
}

export default function PhaseRejection({ address, onTryAgain }: PhaseRejectionProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
      className="min-h-[calc(100vh-8rem)] flex flex-col justify-center items-center px-6 bg-white"
    >
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.2, duration: 0.6 }}
        className="max-w-lg w-full text-center"
      >
        {/* Icon */}
        <div className="inline-flex items-center justify-center w-16 h-16 bg-slate-100 rounded-2xl mb-8">
          <Building2 className="w-8 h-8 text-slate-500" />
        </div>

        {/* Headline */}
        <h1 className="text-3xl md:text-4xl font-serif font-medium tracking-tight text-slate-900 mb-4">
          EarnCheck&#8482; is exclusively for Industrial Properties.
        </h1>

        {/* Sub-headline */}
        <p className="text-slate-500 text-base md:text-lg leading-relaxed mb-10">
          We detected that{' '}
          <span className="font-medium text-slate-700">{address}</span>{' '}
          is a residential property. Our revenue algorithms rely on commercial
          logistics data and cannot value private homes.
        </p>

        {/* Primary action */}
        <button
          onClick={onTryAgain}
          className="inline-flex items-center justify-center px-8 py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg transition-colors text-base"
        >
          Check a Commercial Address
        </button>

        {/* Safety net */}
        <p className="mt-6">
          <a
            href="mailto:support@warehouseexchange.com?subject=Commercial%20Property%20Misidentified&body=My%20property%20at%20this%20address%20is%20a%20commercial%20building%20but%20was%20flagged%20as%20residential."
            className="text-slate-400 text-sm hover:text-slate-600 transition-colors underline underline-offset-4"
          >
            Actually, this is a commercial building.
          </a>
        </p>
      </motion.div>
    </motion.div>
  );
}
