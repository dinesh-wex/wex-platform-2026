'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import CountUp from 'react-countup';
import { Shield, Users, DollarSign } from 'lucide-react';
import { copy } from '@/config/flowCopy';
import { trackEvent } from '@/lib/analytics';
import {
  TruthCore,
  BuildingData,
  RevenueEstimate,
  ContextualMemoryEntry,
  PricingPath,
  calculateRevenue,
  getRegionalRates,
} from './types';

interface Phase5Props {
  truthCore: TruthCore;
  setTruthCore: React.Dispatch<React.SetStateAction<TruthCore>>;
  buildingData: BuildingData | null;
  revenueEstimate: RevenueEstimate | null;
  memories: ContextualMemoryEntry[];
  setMemories: React.Dispatch<React.SetStateAction<ContextualMemoryEntry[]>>;
  onNext: () => void;
}

export default function Phase5Pricing(props: Phase5Props) {
  const { truthCore, setTruthCore, buildingData, revenueEstimate, setMemories, onNext } = props;
  const fallbackRates = getRegionalRates(buildingData?.state);

  // Derive range from low_rate only — conservative estimates
  const rates = revenueEstimate
    ? {
        low: parseFloat((revenueEstimate.low_rate * 0.80).toFixed(2)),
        high: parseFloat((revenueEstimate.low_rate * 0.95).toFixed(2)),
        mid: parseFloat((revenueEstimate.low_rate * 0.85).toFixed(2)),
      }
    : fallbackRates;

  const [prevRevenue, setPrevRevenue] = useState(calculateRevenue(truthCore));
  const [rateInput, setRateInput] = useState(
    truthCore.rateAsk > 0 ? truthCore.rateAsk.toFixed(2) : rates.mid.toFixed(2)
  );

  // Always initialize to the conservative mid-point (low_rate * 0.85) on entry
  useEffect(() => {
    setTruthCore((prev) => ({ ...prev, rateAsk: rates.mid }));
    setRateInput(rates.mid.toFixed(2));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const revenue = calculateRevenue(truthCore);

  function addMemory(category: string, content: string, icon: string) {
    const entry: ContextualMemoryEntry = {
      id: `mem-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category,
      content,
      icon,
      source: 'activation_wizard',
      timestamp: new Date().toISOString(),
    };
    setMemories((prev) => [...prev, entry]);
  }

  function selectPath(path: PricingPath) {
    setPrevRevenue(revenue);
    setTruthCore((prev) => ({ ...prev, pricingPath: path }));
    const label = path === 'set_rate' ? 'Automated Income (Set Rate)' : 'Manual Mode (15% commission)';
    addMemory('Pricing', `Pricing path: ${label}`, '💰');
    trackEvent('selected_pricing_model', {
      model: path === 'set_rate' ? 'fixed_rate' : 'negotiate',
      sqft: truthCore.sqft,
      rateAsk: truthCore.rateAsk,
      revenue,
      address: truthCore.address,
      state: buildingData?.state,
    });
  }

  function handleRateChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setRateInput(val);
    const parsed = parseFloat(val);
    if (!isNaN(parsed) && parsed > 0) {
      setPrevRevenue(revenue);
      setTruthCore((prev) => ({ ...prev, rateAsk: parsed }));
    }
  }

  function handleRateBlur() {
    const parsed = parseFloat(rateInput);
    if (!isNaN(parsed) && parsed > 0) {
      setRateInput(parsed.toFixed(2));
      addMemory('Pricing', `Supplier rate: $${parsed.toFixed(2)}/sqft/mo`, '💵');
    }
  }

  // Commission revenue (net of 15%)
  const commissionRevenue = Math.ceil((revenue * 0.85) / 100) * 100;

  function handleConfirm() {
    // Track pricing selection on confirm (catches users who accept default without clicking a card)
    trackEvent('selected_pricing_model', {
      model: truthCore.pricingPath === 'set_rate' ? 'fixed_rate' : 'negotiate',
      sqft: truthCore.sqft,
      rateAsk: truthCore.rateAsk,
      revenue,
      address: truthCore.address,
      state: buildingData?.state,
    });

    // Final pricing memory
    if (truthCore.pricingPath === 'set_rate') {
      addMemory(
        'Revenue',
        `Locked rate: $${truthCore.rateAsk.toFixed(2)}/sqft/mo → $${revenue.toLocaleString()}/yr`,
        '🔒'
      );
    } else {
      addMemory(
        'Revenue',
        `Commission model: ~$${commissionRevenue.toLocaleString()}/yr (net of 15%)`,
        '🔒'
      );
    }
    onNext();
  }

  return (
    <motion.div
      initial={{ y: 50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: -50, opacity: 0 }}
      transition={{ duration: 0.5 }}
      className="min-h-screen bg-slate-50 pb-24"
    >
      {/* Sticky Scoreboard */}
      <div className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200 px-6 py-4 flex justify-between items-center shadow-sm">
        <span className="text-slate-500 font-medium">Est Additional Annual Income</span>
        <span className="text-3xl font-bold text-emerald-600 font-mono">
          $
          <CountUp
            start={prevRevenue}
            end={truthCore.pricingPath === 'commission' ? commissionRevenue : revenue}
            duration={1}
            separator=","
          />
        </span>
      </div>

      <div className="max-w-3xl mx-auto px-6 mt-12">
        <motion.h2
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="text-3xl font-serif text-slate-900 mb-3"
        >
          {copy.phase5.title}
        </motion.h2>
        {copy.phase5.subtext && <p className="text-slate-500 mb-8">{copy.phase5.subtext}</p>}

        {/* Pricing Path Cards — Asymmetric */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8"
        >
          {/* Hero Card: Automated Income (75%) */}
          <motion.div
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            onClick={() => selectPath('set_rate')}
            className={`md:col-span-3 relative p-6 rounded-2xl border-2 cursor-pointer transition-all ${
              truthCore.pricingPath === 'set_rate'
                ? 'border-emerald-500 bg-white shadow-lg'
                : 'border-slate-100 bg-white hover:border-slate-200'
            }`}
          >
            {/* Recommended badge */}
            <div className="absolute -top-3 left-6 bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded-full shadow-sm">
              {copy.phase5.optionA.badge}
            </div>

            <div className="flex items-start gap-4 mt-2">
              <div
                className={`p-3 rounded-xl ${
                  truthCore.pricingPath === 'set_rate'
                    ? 'bg-emerald-100 text-emerald-600'
                    : 'bg-slate-100 text-slate-400'
                }`}
              >
                <Shield size={24} />
              </div>
              <div className="flex-1">
                <h3 className="text-xl font-bold text-slate-900">
                  {copy.phase5.optionA.title}
                </h3>
                <div className="text-slate-500 text-sm mt-1 space-y-0.5">
                  {copy.phase5.optionA.desc.split('\n').map((line, i) => (
                    <p key={i}>{line}</p>
                  ))}
                </div>
                {copy.phase5.optionA.checklist.length > 0 && (
                  <ul className="text-sm text-slate-600 mt-3 space-y-1">
                    {copy.phase5.optionA.checklist.map((item, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="text-emerald-500">✓</span> {item}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </motion.div>

          {/* Decoy Card: Manual Mode (25%) */}
          <motion.div
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            onClick={() => selectPath('commission')}
            className={`md:col-span-1 p-5 rounded-2xl border cursor-pointer transition-all ${
              truthCore.pricingPath === 'commission'
                ? 'border-slate-400 bg-white shadow-md'
                : 'border-slate-100 bg-slate-50 hover:border-slate-200'
            }`}
          >
            <div
              className={`p-2 rounded-lg mb-3 w-fit ${
                truthCore.pricingPath === 'commission'
                  ? 'bg-slate-200 text-slate-600'
                  : 'bg-slate-100 text-slate-400'
              }`}
            >
              <Users size={20} />
            </div>
            <h3 className="font-bold text-slate-700 text-sm">{copy.phase5.optionB.title}</h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              {copy.phase5.optionB.desc}
            </p>
          </motion.div>
        </motion.div>

        {/* Rate Input (only for set_rate path) */}
        {truthCore.pricingPath === 'set_rate' && (
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 mb-8"
          >
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              {copy.phase5.rateTitle}
            </h3>
            {copy.phase5.rateSubtext && (
              <p className="text-slate-500 text-sm mb-2">{copy.phase5.rateSubtext}</p>
            )}

            {/* Suggested range */}
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-4">
              <div className="flex items-center gap-2 mb-1">
                <DollarSign size={16} className="text-emerald-600" />
                <span className="text-sm font-semibold text-emerald-800">
                  Market Range
                </span>
              </div>
              <p className="text-emerald-700 text-sm">
                Similar spaces in{' '}
                <strong>{revenueEstimate?.rate_location || buildingData?.state || 'your area'}</strong> go for{' '}
                <strong>
                  ${rates.low.toFixed(2)}–${rates.high.toFixed(2)}/sqft/mo
                </strong>
                . Most owners choose around{' '}
                <strong>${rates.mid.toFixed(2)}/sqft</strong>.
              </p>
            </div>

            {/* Rate input */}
            <div className="flex items-center gap-3">
              <div className="relative flex-1 max-w-xs">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 font-medium">
                  $
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0.10"
                  max="5.00"
                  value={rateInput}
                  onChange={handleRateChange}
                  onBlur={handleRateBlur}
                  className="w-full pl-8 pr-24 py-3 border border-slate-200 rounded-xl text-xl font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                />
                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm">
                  /sqft/mo
                </span>
              </div>
              <div className="text-sm text-slate-500">
                = <strong className="text-emerald-600">${revenue.toLocaleString()}</strong>/yr
              </div>
            </div>
          </motion.div>
        )}

        {/* Commission info */}
        {truthCore.pricingPath === 'commission' && (
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 mb-8"
          >
            <p className="text-slate-600 text-sm">
              You&apos;ll review each tenant opportunity and set terms per deal.
              WEx takes a <strong>15% commission</strong> on completed deals.
            </p>
            <p className="text-slate-500 text-sm mt-2">
              Projected net revenue:{' '}
              <strong className="text-emerald-600">
                ~${commissionRevenue.toLocaleString()}/yr
              </strong>{' '}
              (after commission)
            </p>
          </motion.div>
        )}

        {/* Confirm button */}
        <motion.button
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          onClick={handleConfirm}
          className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold text-lg hover:bg-slate-800 transition-colors"
        >
          {copy.phase5.cta(truthCore.pricingPath)}
        </motion.button>
      </div>
    </motion.div>
  );
}
