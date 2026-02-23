'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';
import { BuildingData, RevenueEstimate, TruthCore } from './types';

interface Phase2Props {
  truthCore: TruthCore;
  setTruthCore: React.Dispatch<React.SetStateAction<TruthCore>>;
  buildingData: BuildingData | null;
  setBuildingData: React.Dispatch<React.SetStateAction<BuildingData | null>>;
  setRevenueEstimate: React.Dispatch<React.SetStateAction<RevenueEstimate | null>>;
  onComplete: () => void;
  onRejected: (address: string) => void;
  onFailed: () => void;
}

const PROCESSING_STEPS = [
  'Locating Satellite Imagery...',
  'Scanning Building Footprint...',
  'Analyzing Industrial Zoning...',
  'Benchmarking Comparable Leases...',
  'Calculating Submarket Demand...',
  'Modeling Tenant Absorption Rate...',
  'Finalizing Revenue Estimate...',
];

const STEP_INTERVAL_MS = 2500;

export default function Phase2Processing({
  truthCore,
  setTruthCore,
  buildingData,
  setBuildingData,
  setRevenueEstimate,
  onComplete,
  onRejected,
  onFailed,
}: Phase2Props) {
  const [text, setText] = useState(PROCESSING_STEPS[0]);
  const [dataReady, setDataReady] = useState(false);
  const [animDone, setAnimDone] = useState(false);
  const [progress, setProgress] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    // 1. Cycle through processing text (animation runs immediately)
    const timers: NodeJS.Timeout[] = [];
    PROCESSING_STEPS.forEach((msg, i) => {
      if (i > 0) {
        timers.push(setTimeout(() => { if (!cancelled) setText(msg); }, i * STEP_INTERVAL_MS));
      }
    });

    // 2. Minimum animation time: all steps + 1s buffer after last step
    const totalAnimTime = (PROCESSING_STEPS.length - 1) * STEP_INTERVAL_MS + 1500;
    const animTimer = setTimeout(() => { if (!cancelled) setAnimDone(true); }, totalAnimTime);
    timers.push(animTimer);

    // 3. Fetch building data + revenue estimate in parallel
    const fetchData = async () => {
      let resolvedBuilding = buildingData;

      // If no building data yet, do the lookup now
      if (!resolvedBuilding && truthCore.address) {
        try {
          const sessionId = sessionStorage.getItem('wex_smoke_session_id') || undefined;
          const { isTestSession } = await import('@/lib/analytics');
          const results = await api.warehouseLookup(truthCore.address, sessionId, isTestSession(), controller.signal);
          if (cancelled) return;
          if (results && results.length > 0) {
            const bld = results[0];

            // Check for non-commercial rejection signal
            if (bld.not_commercial) {
              onRejected(bld.address || truthCore.address);
              return;
            }

            resolvedBuilding = {
              id: bld.id,
              address: bld.address,
              city: bld.city,
              state: bld.state,
              zip: bld.zip,
              building_size_sqft: bld.building_size_sqft,
              lot_size_acres: bld.lot_size_acres,
              year_built: bld.year_built,
              construction_type: bld.construction_type,
              zoning: bld.zoning,
              primary_image_url: bld.primary_image_url,
              image_urls: bld.image_urls || [],
              truth_core: bld.truth_core,
              clear_height_ft: bld.truth_core?.clear_height_ft as number | undefined,
              dock_doors_receiving: bld.truth_core?.dock_doors_receiving as number | undefined,
              drive_in_bays: bld.truth_core?.drive_in_bays as number | undefined,
              parking_spaces: bld.truth_core?.parking_spaces as number | undefined,
              has_office_space: bld.truth_core?.has_office_space as boolean | undefined,
              has_sprinkler: bld.truth_core?.has_sprinkler as boolean | undefined,
              power_supply: bld.truth_core?.power_supply as string | undefined,
              nnn_rates: bld.nnn_rates || null,
            };
          }
        } catch (err) {
          // If aborted by cleanup, exit silently
          if (cancelled || (err instanceof DOMException && err.name === 'AbortError')) return;
          // Backend unavailable or other error — will show apology below
        }
      }

      if (cancelled) return;

      // No data found — show apology instead of fake demo data
      if (!resolvedBuilding) {
        setFailed(true);
        return;
      }

      // Set building data and update truth core with resolved info
      setBuildingData(resolvedBuilding);
      setTruthCore((prev) => ({
        ...prev,
        address: resolvedBuilding!.address || prev.address,
        sqft: resolvedBuilding!.building_size_sqft || prev.sqft,
      }));

      // Fetch revenue estimate — use pre-fetched NNN rates if available (saves ~10s)
      const sqft = resolvedBuilding.building_size_sqft || truthCore.sqft;
      const prefetchedRates = resolvedBuilding.nnn_rates;

      if (prefetchedRates) {
        // Rates were fetched in parallel with property search — no extra API call
        const low = prefetchedRates.nnn_low;
        const high = prefetchedRates.nnn_high;
        if (!cancelled) setRevenueEstimate({
          low_rate: low,
          high_rate: high,
          low_monthly: Math.round(sqft * low),
          high_monthly: Math.round(sqft * high),
          low_annual: Math.round(sqft * low) * 12,
          high_annual: Math.round(sqft * high) * 12,
          rate_location: prefetchedRates.rate_location,
        });
      } else {
        // Fallback: separate API call for rates
        try {
          const result = await api.spaceEstimate({
            sqft,
            city: resolvedBuilding.city,
            state: resolvedBuilding.state,
            zip: resolvedBuilding.zip,
          });
          if (!cancelled) setRevenueEstimate({
            low_rate: result.low_rate,
            high_rate: result.high_rate,
            low_monthly: result.low_monthly,
            high_monthly: result.high_monthly,
            low_annual: result.low_annual,
            high_annual: result.high_annual,
            rate_location: result.rate_location,
          });
        } catch {
          // Fallback: client-side estimate
          const rates = resolvedBuilding.state === 'CA' ? [0.85, 1.10] : [0.65, 0.90];
          if (!cancelled) setRevenueEstimate({
            low_rate: rates[0],
            high_rate: rates[1],
            low_monthly: Math.round(sqft * rates[0]),
            high_monthly: Math.round(sqft * rates[1]),
            low_annual: Math.round(sqft * rates[0]) * 12,
            high_annual: Math.round(sqft * rates[1]) * 12,
          });
        }
      }

      if (!cancelled) setDataReady(true);
    };

    fetchData();

    // 4. Progress bar — fill to 100% over 90 seconds
    const PROGRESS_DURATION_MS = 90000;
    const PROGRESS_TICK_MS = 200;
    const progressTimer = setInterval(() => {
      if (cancelled) return;
      setProgress((prev) => {
        const next = prev + (100 / (PROGRESS_DURATION_MS / PROGRESS_TICK_MS));
        return next >= 100 ? 100 : next;
      });
    }, PROGRESS_TICK_MS);
    timers.push(progressTimer as unknown as NodeJS.Timeout);

    return () => {
      cancelled = true;
      controller.abort();
      timers.forEach(clearTimeout);
      clearInterval(progressTimer);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Advance only when BOTH animation is done AND data is ready
  useEffect(() => {
    if (dataReady && animDone) {
      onComplete();
    }
  }, [dataReady, animDone, onComplete]);

  // --- Apology screen when lookup fails ---
  if (failed) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.5 }}
        className="min-h-[calc(100vh-8rem)] flex flex-col items-center justify-center bg-black relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 opacity-80" />
        <div className="z-10 text-center max-w-md px-6">
          <div className="w-16 h-16 rounded-full bg-slate-700/50 flex items-center justify-center mx-auto mb-6">
            <span className="text-3xl">🏗️</span>
          </div>
          <h2 className="text-white text-2xl md:text-3xl font-bold mb-3">
            We&apos;re sorry
          </h2>
          <p className="text-slate-300 text-base md:text-lg mb-8">
            We couldn&apos;t find details for this property right now. This can happen when our data sources are temporarily slow. Please try again.
          </p>
          <button
            onClick={onFailed}
            className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-3 px-8 rounded-xl shadow-lg transition-all"
          >
            Try Again
          </button>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
      className="min-h-[calc(100vh-8rem)] flex flex-col items-center bg-black relative overflow-hidden"
    >
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 opacity-80" />

      {/* === TOP: Headline + Subtext === */}
      <div className="z-10 text-center max-w-lg px-6 pt-20 md:pt-28">
        <motion.h1
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.6 }}
          className="text-white text-3xl md:text-5xl font-bold tracking-tight mb-3"
        >
          In less than 1 minute...
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 0.6 }}
          className="text-slate-300 text-lg md:text-xl font-light"
        >
          ...you will see what your unused space is worth.
        </motion.p>
      </div>

      {/* === Progress bar (fixed width matching subtitle) === */}
      <div className="z-10 mt-12" style={{ width: '380px', maxWidth: '90vw' }}>
        <div className="h-1.5 w-full rounded-full bg-white/20 overflow-hidden">
          <div
            className="h-full rounded-full bg-white transition-all duration-200 ease-linear"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* === MIDDLE: Spinner + Status Updates === */}
      <div className="z-10 flex-1 flex flex-col justify-center items-center px-6">
        {/* Spinner */}
        <div className="w-16 h-16 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-6" />

        {/* Cycling status text */}
        <motion.p
          key={text}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3 }}
          className="text-emerald-400 text-base md:text-lg font-medium tracking-wide"
        >
          {text}
        </motion.p>
      </div>

      {/* === BOTTOM: Trust micro-copy === */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2, duration: 0.8 }}
        className="z-10 text-slate-500 text-xs md:text-sm text-center px-6 pb-10"
      >
        Please do not refresh. We are finalizing your EarnCheck™ report.
      </motion.p>
    </motion.div>
  );
}
