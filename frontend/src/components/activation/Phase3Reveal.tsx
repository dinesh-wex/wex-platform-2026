'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import CountUp from 'react-countup';
import { TruthCore, BuildingData, RevenueEstimate, getRegionalRates } from './types';
import { copy } from '@/config/flowCopy';
import { trackEvent } from '@/lib/analytics';

interface Phase3Props {
  truthCore: TruthCore;
  setTruthCore: React.Dispatch<React.SetStateAction<TruthCore>>;
  buildingData: BuildingData | null;
  revenueEstimate: RevenueEstimate | null;
  onNext: () => void;
  onSearchAgain: () => void;
}

interface DNATag {
  label: string;
  icon: string;
}

function buildDNATags(bd: BuildingData | null, sqft: number): DNATag[] {
  const tags: DNATag[] = [];
  tags.push({ label: `${(bd?.building_size_sqft || sqft).toLocaleString()} sqft`, icon: '📐' });
  if (bd?.clear_height_ft) tags.push({ label: `${bd.clear_height_ft}' Clear`, icon: '⬆️' });
  if (bd?.year_built) tags.push({ label: `Built ${bd.year_built}`, icon: '🏗️' });
  if (bd?.drive_in_bays) tags.push({ label: `${bd.drive_in_bays} Drive-in${bd.drive_in_bays > 1 ? 's' : ''}`, icon: '🚛' });
  if (bd?.dock_doors_receiving) tags.push({ label: `${bd.dock_doors_receiving} Docks`, icon: '🚪' });
  if (bd?.has_sprinkler) tags.push({ label: 'Sprinklered', icon: '💧' });
  return tags;
}

export default function Phase3Reveal({
  truthCore,
  setTruthCore,
  buildingData,
  revenueEstimate,
  onNext,
  onSearchAgain,
}: Phase3Props) {
  const rates = getRegionalRates(buildingData?.state);
  const [prevRevenue, setPrevRevenue] = useState(0);
  const totalSqft = buildingData?.building_size_sqft || 80000;
  const defaultSqft = Math.min(totalSqft, Math.max(2000, Math.round(totalSqft * 0.4)));
  const [hasMovedSlider, setHasMovedSlider] = useState(false);
  const [showEarncheckInfo, setShowEarncheckInfo] = useState(false);

  // Extract per-sqft rate from backend estimate or regional fallback
  // Use low_rate * 0.95 for a conservative estimate
  const effectiveRate = revenueEstimate
    ? parseFloat((revenueEstimate.low_rate * 0.95).toFixed(2))
    : rates.mid;

  useEffect(() => {
    setTruthCore((prev) => ({ ...prev, sqft: defaultSqft, rateAsk: effectiveRate }));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Revenue = current slider sqft × rate × 12 months, rounded to $100
  const revenue = Math.ceil((truthCore.sqft * effectiveRate * 12) / 100) * 100;

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newSqft = Number(e.target.value);
    if (!hasMovedSlider) setHasMovedSlider(true);
    setPrevRevenue(revenue);
    setTruthCore((prev) => ({ ...prev, sqft: newSqft }));
  };

  const bgImage = buildingData?.primary_image_url || buildingData?.image_urls?.[0];
  const dnaTags = buildDNATags(buildingData, truthCore.sqft);

  // Track when estimate is viewed
  useEffect(() => {
    trackEvent('estimate_viewed', {
      revenue,
      sqft: truthCore.sqft,
      address: truthCore.address,
      totalBuildingSqft: totalSqft,
      effectiveRate: effectiveRate,
      state: buildingData?.state,
      city: buildingData?.city,
      zip: buildingData?.zip,
    });
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-[calc(100vh-8rem)] flex flex-col justify-center items-center relative bg-slate-100 overflow-hidden"
    >
      <div className="z-10 w-full max-w-lg px-4">
        {/* THE SPLIT-VIEW ASSET CARD */}
        <motion.div
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="bg-white rounded-[28px] overflow-hidden shadow-2xl"
        >
          {/* ═══════════════════════════════════════════════
              TOP 45% — THE VIEW (Pure Satellite Photo)
              No text overlay. No gradients. Just the roof.
              DNA Tags sit at bottom-left as glass pills.
              ═══════════════════════════════════════════════ */}
          <div className="relative" style={{ height: '45%', minHeight: 240 }}>
            {bgImage ? (
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: `url(${bgImage})` }}
              />
            ) : (
              <div className="absolute inset-0 bg-gradient-to-br from-slate-600 via-slate-700 to-emerald-800" />
            )}

            {/* DNA Tags — glass pills at bottom-left of photo */}
            <div className="absolute bottom-3 left-3 flex flex-wrap gap-1.5">
              {dnaTags.map((tag, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 + i * 0.1 }}
                  className="bg-black/40 backdrop-blur-md border border-white/20 px-2.5 py-1 rounded-full text-[11px] font-medium text-white flex items-center gap-1"
                >
                  <span>{tag.icon}</span> {tag.label}
                </motion.div>
              ))}
            </div>
          </div>

          {/* ═══════════════════════════════════════════════
              BOTTOM 55% — THE DEED (White Card)
              Address → Market Value → Slider → CTA
              ═══════════════════════════════════════════════ */}
          <div className="px-8 pt-6 pb-8 bg-white">
            {/* Address — black on white, high contrast */}
            <motion.h2
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="text-xl font-bold text-slate-900 leading-tight mb-1"
            >
              {truthCore.address || buildingData?.address || '123 Industrial Blvd'}
            </motion.h2>
            <div className="mb-6" />

            {/* The Money */}
            {copy.phase3.eyebrow && (
              <div className="flex items-center justify-center gap-1.5 mb-2 relative">
                <p className="text-slate-400 text-[10px] font-bold uppercase tracking-[0.2em]">
                  {copy.phase3.eyebrow}
                </p>
                <button
                  type="button"
                  onClick={() => setShowEarncheckInfo((v) => !v)}
                  className="w-4 h-4 rounded-full border border-slate-300 text-slate-400 text-[9px] font-bold leading-none flex items-center justify-center hover:bg-slate-100 transition-colors"
                  aria-label="What is EarnCheck?"
                >
                  i
                </button>
                {showEarncheckInfo && (
                  <div className="absolute top-6 left-1/2 -translate-x-1/2 z-50 w-72 bg-white rounded-lg shadow-lg border border-slate-200 p-4 text-left">
                    <p className="text-slate-700 text-xs leading-relaxed">
                      EarnCheck™ is an estimate of potential revenue based on public rental listings, local market data, and active tenant demand on the Warehouse Exchange network.
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowEarncheckInfo(false)}
                      className="mt-2 text-[10px] text-slate-400 hover:text-slate-600"
                    >
                      Close
                    </button>
                  </div>
                )}
              </div>
            )}
            <p className="text-slate-400 text-[10px] font-bold uppercase tracking-[0.2em] mb-1 text-center">
              {copy.phase3.revenueLabel}
            </p>
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.4 + dnaTags.length * 0.1, duration: 0.6 }}
              className="text-5xl font-bold text-emerald-600 mb-1 tracking-tight text-center"
            >
              $<CountUp start={prevRevenue} end={revenue} duration={2.0} separator="," delay={0.3} />
              <span className="text-lg text-slate-400 font-normal">/yr</span>
            </motion.div>

            <p className="text-emerald-700 text-sm font-semibold mb-1 text-center">
              {truthCore.sqft.toLocaleString()} sqft &times; ${effectiveRate.toFixed(2)}/sqft/mo
            </p>
            <p className="text-slate-400 text-xs mb-6 text-center">
              Slide below to adjust your available space
            </p>

            {/* Rate context — single rate, no range */}
            {revenueEstimate && (
              <p className="text-slate-400 text-xs mb-3 text-center">
                Market rate: ${effectiveRate.toFixed(2)}/sqft/mo in{' '}
                {revenueEstimate.rate_location || buildingData?.state || 'your area'}
              </p>
            )}

            {/* The Slider */}
            <div className="mb-6 px-1">
              <input
                type="range"
                min="2000"
                max={totalSqft}
                step="1000"
                value={truthCore.sqft}
                onChange={handleSliderChange}
                className="revenue-slider w-full"
              />
              <div className="flex justify-between text-slate-400 text-xs mt-2 font-medium">
                <span>2,000 sqft</span>
                <span>Adjust Utilization</span>
                <span>{totalSqft.toLocaleString()} sqft</span>
              </div>
            </div>

            {/* CTA */}
            <button
              onClick={onNext}
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white text-lg font-bold py-4 rounded-xl shadow-lg shadow-emerald-200 transition-all transform hover:-translate-y-0.5"
            >
              {copy.phase3.primaryCta}
            </button>

            <button
              onClick={onSearchAgain}
              className="w-full text-slate-400 text-xs hover:text-slate-600 font-medium mt-3"
            >
              {copy.phase3.secondaryCta}
            </button>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
