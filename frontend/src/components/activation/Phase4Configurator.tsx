'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Box, Settings, MessageSquarePlus, AlertTriangle, CheckCircle2 } from 'lucide-react';
import SelectionCard from './shared/SelectionCard';
import Toggle from './shared/Toggle';
import StickyScoreboard from './shared/StickyScoreboard';
import {
  TruthCore,
  BuildingData,
  ContextualMemoryEntry,
  calculateRevenue,
  ActivityTier,
} from './types';
import { api } from '@/lib/api';
import { trackEvent } from '@/lib/analytics';
import { copy } from '@/config/flowCopy';

interface Phase4Props {
  truthCore: TruthCore;
  setTruthCore: React.Dispatch<React.SetStateAction<TruthCore>>;
  buildingData: BuildingData | null;
  memories: ContextualMemoryEntry[];
  setMemories: React.Dispatch<React.SetStateAction<ContextualMemoryEntry[]>>;
  onNext: () => void;
}

export default function Phase4Configurator({
  truthCore,
  setTruthCore,
  buildingData,
  memories,
  setMemories,
  onNext,
}: Phase4Props) {
  const [prevRevenue, setPrevRevenue] = useState(calculateRevenue(truthCore));
  const [notesExpanded, setNotesExpanded] = useState(false);

  // Track configurator entry
  useEffect(() => {
    trackEvent('configurator_started', {
      sqft: truthCore.sqft,
      address: truthCore.address,
      state: buildingData?.state,
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const revenue = calculateRevenue(truthCore);

  // Dual slider bounds
  const SLIDER_MIN = 500;
  const SLIDER_MAX = buildingData?.building_size_sqft || truthCore.sqft || 100000;

  // Flexibility badge logic
  const flexRatio = truthCore.sqft > 0 ? truthCore.minRentable / truthCore.sqft : 1;
  const isHighLiquidity = flexRatio <= 0.3;
  const isLimited = flexRatio >= 0.9;

  function addMemory(category: string, content: string, icon: string, source: ContextualMemoryEntry['source'] = 'activation_wizard') {
    const entry: ContextualMemoryEntry = {
      id: `mem-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category,
      content,
      icon,
      source,
      timestamp: new Date().toISOString(),
    };
    setMemories((prev) => [...prev, entry]);
  }

  // Dual-handle slider handlers
  const handleMinChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Math.min(Number(e.target.value), truthCore.sqft - 500);
    setTruthCore((prev) => ({ ...prev, minRentable: val }));
  }, [truthCore.sqft, setTruthCore]);

  const handleMaxChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Math.max(Number(e.target.value), truthCore.minRentable + 500);
    setPrevRevenue(revenue);
    setTruthCore((prev) => ({ ...prev, sqft: val }));
  }, [truthCore.minRentable, setTruthCore, revenue]);

  // Debounced memory writes on pointer up
  const handleMinPointerUp = useCallback(() => {
    addMemory('Capacity', `Min rentable unit: ${truthCore.minRentable.toLocaleString()} sqft`, '📏');
  }, [truthCore.minRentable]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMaxPointerUp = useCallback(() => {
    addMemory('Capacity', `Total available: ${truthCore.sqft.toLocaleString()} sqft`, '📐');
  }, [truthCore.sqft]); // eslint-disable-line react-hooks/exhaustive-deps

  // Percentage positions for the filled track
  const minPercent = ((truthCore.minRentable - SLIDER_MIN) / (SLIDER_MAX - SLIDER_MIN)) * 100;
  const maxPercent = ((truthCore.sqft - SLIDER_MIN) / (SLIDER_MAX - SLIDER_MIN)) * 100;

  function setActivity(tier: ActivityTier) {
    setPrevRevenue(revenue);
    setTruthCore((prev) => ({ ...prev, activityTier: tier }));
    const label = tier === 'storage_light_assembly' ? 'Light operations permitted' : 'Storage only';
    addMemory('Activity', label, '⚙️');
  }

  function toggleOffice() {
    setPrevRevenue(revenue);
    setTruthCore((prev) => {
      const next = !prev.hasOffice;
      addMemory('Amenities', next ? 'Office space included' : 'No office space', '🏢');
      return { ...prev, hasOffice: next };
    });
  }

  function toggleWeekend() {
    setPrevRevenue(revenue);
    setTruthCore((prev) => {
      const next = !prev.weekendAccess;
      addMemory('Access', next ? 'Weekend access available' : 'Weekday access only', '📅');
      return { ...prev, weekendAccess: next };
    });
  }

  function handleDateChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setTruthCore((prev) => ({ ...prev, availabilityStart: val }));
    if (val) {
      addMemory('Availability', `Available from ${val}`, '📆');
    }
  }

  function handleTermChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = Number(e.target.value);
    setTruthCore((prev) => ({ ...prev, minTermMonths: val }));
    addMemory('Terms', `Minimum lease term: ${val} month${val !== 1 ? 's' : ''}`, '📋');
  }

  async function handleNotesSave() {
    const text = truthCore.additionalNotes.trim();
    if (!text) return;

    try {
      if (buildingData?.id) {
        await api.sendActivationMessage({
          warehouse_id: buildingData.id,
          message: text,
          conversation_history: [],
          current_step: 1,
          extracted_fields: {},
        });
      }
    } catch {
      // Backend unavailable — store raw text as memory
    }

    addMemory('Additional Info', text, '💬', 'user_input');
  }

  const defaultDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)
    .toISOString()
    .split('T')[0];

  return (
    <motion.div
      initial={{ y: 50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: -50, opacity: 0 }}
      transition={{ duration: 0.5 }}
      className="min-h-screen bg-slate-50 pb-24"
    >
      {/* Sticky Scoreboard */}
      <StickyScoreboard revenue={revenue} previousRevenue={prevRevenue} />

      <div className="max-w-3xl mx-auto px-6 mt-12">
        <motion.h2
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="text-3xl font-serif text-slate-900 mb-2"
        >
          {copy.phase4.headline}
        </motion.h2>
        <motion.p
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.25 }}
          className="text-slate-500 mb-8"
        >
          {copy.phase4.subtext}
        </motion.p>

        {/* ═══════════════════════════════════════════════
            Card 0: Capacity — Sentence + Dual-Handle Slider
            ═══════════════════════════════════════════════ */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 mb-6"
        >
          <h3 className="text-lg font-bold mb-1 text-slate-900">
            {copy.phase4.capacityCardTitle}
          </h3>
          <p className="text-slate-400 text-sm mb-6">
            {copy.phase4.capacityCardSubtext}
          </p>

          {/* The Read-Only Sentence (updates from slider) */}
          <div className="text-lg text-slate-700 leading-relaxed mb-6 text-center">
            {copy.phase4.sentencePrefix}{' '}
            <span className="font-bold text-emerald-600">
              {truthCore.sqft.toLocaleString()}
            </span>{' '}
            {copy.phase4.sentenceSuffix}
            {copy.phase4.sentenceSuffix.includes('down to') && (
              <>
                {' '}
                <span className="font-bold text-emerald-600">
                  {truthCore.minRentable.toLocaleString()}
                </span>{' '}
                sqft.
              </>
            )}
          </div>

          {/* Dual-Handle Range Slider */}
          <div className="relative h-12 mb-2">
            {/* Track background */}
            <div className="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-3 bg-slate-200 rounded-full" />

            {/* Filled track between the two handles */}
            <div
              className="absolute top-1/2 -translate-y-1/2 h-3 bg-emerald-400 rounded-full"
              style={{
                left: `${minPercent}%`,
                width: `${maxPercent - minPercent}%`,
              }}
            />

            {/* Min handle (left knob) */}
            <input
              type="range"
              min={SLIDER_MIN}
              max={SLIDER_MAX}
              step={500}
              value={truthCore.minRentable}
              onChange={handleMinChange}
              onPointerUp={handleMinPointerUp}
              className="dual-slider dual-slider-min absolute top-0 left-0 w-full h-full"
            />

            {/* Max handle (right knob) */}
            <input
              type="range"
              min={SLIDER_MIN}
              max={SLIDER_MAX}
              step={500}
              value={truthCore.sqft}
              onChange={handleMaxChange}
              onPointerUp={handleMaxPointerUp}
              className="dual-slider dual-slider-max absolute top-0 left-0 w-full h-full"
            />
          </div>

          {/* Labels */}
          <div className="flex justify-between text-xs text-slate-400 font-medium mb-4">
            <span>Min: {truthCore.minRentable.toLocaleString()} sqft</span>
            <span>Max: {truthCore.sqft.toLocaleString()} sqft</span>
          </div>

          {/* Flexibility Feedback Badge */}
          <div>
            {isHighLiquidity && (
              <motion.div
                key="high"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="inline-flex items-center gap-2 bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1.5 rounded-full text-sm font-medium"
              >
                <CheckCircle2 size={16} />
                High Liquidity! Smaller units clear 2x faster.
              </motion.div>
            )}
            {isLimited && (
              <motion.div
                key="limited"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="inline-flex items-center gap-2 bg-amber-50 text-amber-700 border border-amber-200 px-3 py-1.5 rounded-full text-sm font-medium"
              >
                <AlertTriangle size={16} />
                Limited Tenant Pool — Harder to Match
              </motion.div>
            )}
            {!isHighLiquidity && !isLimited && (
              <motion.div
                key="good"
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="inline-flex items-center gap-2 bg-blue-50 text-blue-600 border border-blue-200 px-3 py-1.5 rounded-full text-sm font-medium"
              >
                <CheckCircle2 size={16} />
                Good Flexibility
              </motion.div>
            )}
          </div>
        </motion.div>

        {/* Step A: Activity Tier */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 mb-6"
        >
          <h3 className="text-lg font-bold mb-4 text-slate-900">
            How can tenants use the space?
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <SelectionCard
              selected={truthCore.activityTier === 'storage_only'}
              onClick={() => setActivity('storage_only')}
              icon={<Box size={24} />}
              title="Storage Only"
              desc="Passive storage. Low foot traffic."
            />
            <SelectionCard
              selected={truthCore.activityTier === 'storage_light_assembly'}
              onClick={() => setActivity('storage_light_assembly')}
              icon={<Settings size={24} />}
              title="Light Operations"
              desc="Kitting, assembly, and pick & pack."
              badge="potentially +15%"
            />
          </div>
        </motion.div>

        {/* Step B: Amenities */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="space-y-4 mb-6"
        >
          <Toggle
            active={truthCore.hasOffice}
            onToggle={toggleOffice}
            label="Include Office Space?"
            description="Attracts premium tenants."
            badge="potentially +8%"
          />
          <Toggle
            active={truthCore.weekendAccess}
            onToggle={toggleWeekend}
            label="Weekend Access?"
            description="Allow tenants to access on weekends."
            badge="potentially +2%"
          />
        </motion.div>

        {/* Step C: Availability */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.6 }}
          className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 mb-6"
        >
          <h3 className="text-lg font-bold mb-4 text-slate-900">
            When can revenue start?
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="text-sm font-medium text-slate-600 mb-2 block">
                Available From
              </label>
              <input
                type="date"
                value={truthCore.availabilityStart || defaultDate}
                onChange={handleDateChange}
                className="w-full border border-slate-200 rounded-xl px-4 py-3 text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-600 mb-2 block">
                Minimum Term:{' '}
                <span className="text-emerald-600 font-bold">
                  {truthCore.minTermMonths} month{truthCore.minTermMonths !== 1 ? 's' : ''}
                </span>
              </label>
              <input
                type="range"
                min="1"
                max="12"
                step="1"
                value={truthCore.minTermMonths}
                onChange={handleTermChange}
                className="revenue-slider w-full"
              />
              <div className="flex justify-between text-slate-400 text-xs mt-1">
                <span>1 mo</span>
                <span>12 mo</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Step D: Tell us more (AI-powered) */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.7 }}
          className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 mb-8"
        >
          <button
            onClick={() => {
              setNotesExpanded(!notesExpanded);
              setTimeout(() => textareaRef.current?.focus(), 100);
            }}
            className="flex items-center gap-2 text-slate-600 hover:text-slate-900 transition-colors w-full text-left"
          >
            <MessageSquarePlus size={20} />
            <span className="font-medium">Tell us more</span>
            <span className="text-slate-400 text-sm ml-1">(optional)</span>
            <span className={`ml-auto transition-transform ${notesExpanded ? 'rotate-180' : ''}`}>
              ▾
            </span>
          </button>

          {notesExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              transition={{ duration: 0.3 }}
              className="mt-4"
            >
              <textarea
                ref={textareaRef}
                value={truthCore.additionalNotes}
                onChange={(e) =>
                  setTruthCore((prev) => ({ ...prev, additionalNotes: e.target.value }))
                }
                placeholder="Anything else tenants should know? (cold storage, forklifts, restrictions, special features...)"
                className="w-full border border-slate-200 rounded-xl px-4 py-3 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
                rows={3}
              />
              <p className="text-xs text-slate-400 mt-2">
                This info helps match you with the right tenants
              </p>

              {/* Show saved memory pills */}
              {memories.filter((m) => m.source === 'user_input').length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {memories
                    .filter((m) => m.source === 'user_input')
                    .map((m) => (
                      <span
                        key={m.id}
                        className="bg-emerald-50 text-emerald-700 text-xs px-3 py-1 rounded-full border border-emerald-200"
                      >
                        {m.icon} {m.content.length > 50 ? m.content.slice(0, 50) + '...' : m.content}
                      </span>
                    ))}
                </div>
              )}
            </motion.div>
          )}
        </motion.div>

        {/* Next button */}
        <motion.button
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          onClick={() => {
            // Auto-save notes to memory if user typed something
            const notes = truthCore.additionalNotes?.trim();
            if (notes) {
              handleNotesSave();
            }
            trackEvent('configurator_completed', {
              sqft: truthCore.sqft,
              minRentable: truthCore.minRentable,
              activityTier: truthCore.activityTier,
              hasOffice: truthCore.hasOffice,
              weekendAccess: truthCore.weekendAccess,
              minTermMonths: truthCore.minTermMonths,
              availabilityStart: truthCore.availabilityStart,
              additionalNotes: truthCore.additionalNotes,
              address: truthCore.address,
              state: buildingData?.state,
            });
            onNext();
          }}
          className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold text-lg hover:bg-slate-800 transition-colors"
        >
          {copy.phase4.nextButton}
        </motion.button>
      </div>
    </motion.div>
  );
}
