'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, useMotionValue, useTransform } from 'framer-motion';
import CountUp from 'react-countup';
import { Check, ShieldCheck, Mail, CheckCircle } from 'lucide-react';
import ConfettiOverlay from './shared/ConfettiOverlay';
import {
  TruthCore,
  BuildingData,
  RevenueEstimate,
  ContextualMemoryEntry,
  calculateRevenue,
} from './types';
import { copy, isSmokeTest } from '@/config/flowCopy';
import { trackEvent } from '@/lib/analytics';
import { api } from '@/lib/api';

interface Phase6Props {
  truthCore: TruthCore;
  buildingData: BuildingData | null;
  revenueEstimate: RevenueEstimate | null;
  memories: ContextualMemoryEntry[];
  setMemories: React.Dispatch<React.SetStateAction<ContextualMemoryEntry[]>>;
}

interface AssetTag {
  label: string;
  type: 'dna' | 'upgrade';
}

function buildAssetTags(bd: BuildingData | null, tc: TruthCore): AssetTag[] {
  const tags: AssetTag[] = [];

  // Static DNA from building data
  if (bd?.year_built) tags.push({ label: `Built ${bd.year_built}`, type: 'dna' });
  if (bd?.clear_height_ft) tags.push({ label: `${bd.clear_height_ft}' Clear`, type: 'dna' });
  if (bd?.drive_in_bays) tags.push({ label: `${bd.drive_in_bays} Drive-in${bd.drive_in_bays > 1 ? 's' : ''}`, type: 'dna' });
  if (bd?.dock_doors_receiving) tags.push({ label: `${bd.dock_doors_receiving} Dock Doors`, type: 'dna' });
  if (bd?.has_sprinkler) tags.push({ label: 'Sprinklered', type: 'dna' });

  // Dynamic upgrades from user configuration
  if (tc.activityTier === 'storage_light_assembly') tags.push({ label: 'Light Ops Permitted', type: 'upgrade' });
  if (tc.hasOffice) tags.push({ label: 'Office Included', type: 'upgrade' });
  if (tc.weekendAccess) tags.push({ label: 'Weekend Access', type: 'upgrade' });

  return tags;
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export default function Phase6Activation(props: Phase6Props) {
  const { truthCore, buildingData, revenueEstimate, setMemories } = props;
  const router = useRouter();
  const [isActive, setIsActive] = useState(false);
  const [email, setEmail] = useState('');
  const [activating, setActivating] = useState(false);

  const [showEarncheckInfo, setShowEarncheckInfo] = useState(false);

  const revenue = calculateRevenue(truthCore);
  const assetTags = buildAssetTags(buildingData, truthCore);
  const emailValid = isValidEmail(email);

  // 3D Tilt Physics
  const x = useMotionValue(200);
  const y = useMotionValue(200);
  const rotateX = useTransform(y, [0, 400], [3, -3]);
  const rotateY = useTransform(x, [0, 400], [-3, 3]);

  const bgImage = buildingData?.primary_image_url || buildingData?.image_urls?.[0];

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

  async function handleActivate() {
    if (!emailValid) return;
    setActivating(true);

    // Build the TruthCoreCreate payload for the backend
    const payload = {
      warehouse_id: buildingData?.id || `wh-${Date.now()}`,
      min_sqft: truthCore.minRentable,
      max_sqft: truthCore.sqft,
      activity_tier: truthCore.activityTier,
      constraints: {
        weekend_access: truthCore.weekendAccess,
        pricing_path: truthCore.pricingPath,
        additional_notes: truthCore.additionalNotes || undefined,
      },
      supplier_rate_per_sqft: truthCore.rateAsk,
      supplier_rate_max: truthCore.rateAsk * 1.2,
      available_from: truthCore.availabilityStart || undefined,
      min_term_months: truthCore.minTermMonths,
      max_term_months: 12,
      has_office_space: truthCore.hasOffice,
      tour_readiness: '48_hours',
      trust_level: 0,
      activation_status: isSmokeTest ? 'pending_report' : 'on',
    };

    // Try backend API — use anonymous call to avoid leaking a previous user's session
    try {
      if (buildingData?.id) {
        await api.activateWarehouseAnon(buildingData.id, payload);
      }
    } catch {
      // Backend unavailable — continue with localStorage
    }

    // Always save to localStorage for demo mode
    const activatedWarehouse = {
      id: buildingData?.id || `wh-${Date.now()}`,
      name: buildingData?.city
        ? `${buildingData.city} Warehouse`
        : 'New Warehouse',
      address: buildingData?.address || truthCore.address,
      city: buildingData?.city || '',
      state: buildingData?.state || '',
      zip_code: buildingData?.zip || '',
      total_sqft: buildingData?.building_size_sqft || truthCore.sqft,
      available_sqft: truthCore.sqft,
      idle_sqft: truthCore.sqft,
      status: isSmokeTest ? 'pending_report' : 'active',
      supplier_rate: truthCore.rateAsk,
      pricing_path: truthCore.pricingPath,
      image_url: buildingData?.primary_image_url || null,
      image_urls: buildingData?.image_urls || [],
      clear_height: buildingData?.clear_height_ft || null,
      dock_doors: buildingData?.dock_doors_receiving || null,
      drive_in_bays: buildingData?.drive_in_bays || null,
      parking_spaces: buildingData?.parking_spaces || null,
      year_built: buildingData?.year_built || null,
      construction_type: buildingData?.construction_type || null,
      sprinklered: buildingData?.has_sprinkler ?? null,
      power_phase: buildingData?.power_supply || null,
      features: [],
      min_sqft: truthCore.minRentable,
      activation_step: 7,
      truth_core: {
        activity_tier: truthCore.activityTier,
        has_office: truthCore.hasOffice,
        weekend_access: truthCore.weekendAccess,
        pricing_path: truthCore.pricingPath,
        rate_ask: truthCore.rateAsk,
        min_term_months: truthCore.minTermMonths,
        availability_start: truthCore.availabilityStart,
        min_rentable: truthCore.minRentable,
      },
      activated_at: new Date().toISOString(),
      owner_email: email,
    };

    const existing = JSON.parse(
      localStorage.getItem('wex_activated_warehouses') || '[]'
    );
    const filtered = existing.filter(
      (w: { id: string }) => w.id !== activatedWarehouse.id
    );
    filtered.push(activatedWarehouse);
    localStorage.setItem(
      'wex_activated_warehouses',
      JSON.stringify(filtered)
    );

    // Save supplier profile so dashboard recognizes the user
    const supplierProfile = {
      id: `supplier-${Date.now()}`,
      name: email.split('@')[0].replace(/[._-]/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
      company: (email.split('@')[1]?.split('.')[0] || 'Unknown').replace(/-/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
      email: email,
    };
    localStorage.setItem('wex_supplier', JSON.stringify(supplierProfile));

    // Write final memory
    if (isSmokeTest) {
      addMemory(
        'Report',
        `Income report requested: ${truthCore.sqft.toLocaleString()} sqft @ $${truthCore.rateAsk.toFixed(2)}/sqft/mo → $${revenue.toLocaleString()}/yr — sent to ${email}`,
        '📧'
      );
    } else {
      addMemory(
        'Activation',
        `Warehouse activated: ${truthCore.sqft.toLocaleString()} sqft @ $${truthCore.rateAsk.toFixed(2)}/sqft/mo → $${revenue.toLocaleString()}/yr`,
        '🚀'
      );
    }

    // Track email submission event
    trackEvent('email_submitted', {
      email,
      revenue,
      sqft: truthCore.sqft,
      minRentable: truthCore.minRentable,
      rateAsk: truthCore.rateAsk,
      market_rate_low: revenueEstimate?.low_rate || null,
      market_rate_high: revenueEstimate?.high_rate || null,
      recommended_rate: revenueEstimate ? parseFloat((revenueEstimate.low_rate * 0.95).toFixed(2)) : null,
      pricingPath: truthCore.pricingPath,
      activityTier: truthCore.activityTier,
      hasOffice: truthCore.hasOffice,
      weekendAccess: truthCore.weekendAccess,
      minTermMonths: truthCore.minTermMonths,
      availabilityStart: truthCore.availabilityStart,
      additionalNotes: truthCore.additionalNotes,
      address: truthCore.address,
      state: buildingData?.state,
      city: buildingData?.city,
      zip: buildingData?.zip,
      buildingSqft: buildingData?.building_size_sqft,
    });

    setActivating(false);
    setIsActive(true);
  }

  // Auto-redirect to dashboard after activation animation (production only)
  useEffect(() => {
    if (isActive && !isSmokeTest) {
      const timer = setTimeout(() => router.push('/supplier'), 3000);
      return () => clearTimeout(timer);
    }
  }, [isActive, router]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="min-h-[calc(100vh-8rem)] flex flex-col justify-center items-center bg-slate-100 overflow-hidden"
      style={{ perspective: 1000 }}
    >
      {/* Confetti only in production mode */}
      {isActive && !isSmokeTest && <ConfettiOverlay />}

      <div className="z-10 w-full max-w-lg px-4">
        <motion.div
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          style={{ rotateX, rotateY }}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            x.set(e.clientX - rect.left);
            y.set(e.clientY - rect.top);
          }}
          onMouseLeave={() => {
            x.set(200);
            y.set(200);
          }}
          className="bg-white rounded-[28px] overflow-hidden shadow-2xl cursor-default"
        >
          {/* TOP 45% — THE VIEW */}
          <div className="relative" style={{ height: '45%', minHeight: 240 }}>
            {bgImage ? (
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: `url(${bgImage})` }}
              />
            ) : (
              <div className="absolute inset-0 bg-gradient-to-br from-slate-600 via-slate-700 to-emerald-800" />
            )}

            {/* STATUS BADGE — top right of photo */}
            <div className="absolute top-4 right-4 z-20">
              <motion.div
                animate={{
                  backgroundColor:
                    isActive && !isSmokeTest ? '#10B981' : '#F59E0B',
                }}
                className="px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest text-white shadow-lg flex items-center gap-1.5"
              >
                {isActive && !isSmokeTest ? (
                  <Check size={12} strokeWidth={4} />
                ) : (
                  <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                )}
                {isActive && !isSmokeTest
                  ? 'Asset Active'
                  : copy.phase6.statusBadge}
              </motion.div>
            </div>

            {/* The "ACTIVE" Stamp — production only */}
            {isActive && !isSmokeTest && (
              <motion.div
                initial={{ scale: 2.5, opacity: 0, rotate: -15 }}
                animate={{ scale: 1, opacity: 1, rotate: -12 }}
                transition={{ type: 'spring', stiffness: 300, damping: 15, delay: 0.2 }}
                className="absolute inset-0 flex items-center justify-center z-30 pointer-events-none"
              >
                <div className="border-4 border-emerald-400 text-emerald-400 text-5xl font-black uppercase tracking-[0.3em] px-8 py-3 rounded-lg bg-emerald-500/10 backdrop-blur-sm">
                  ACTIVE
                </div>
              </motion.div>
            )}

            {/* DNA Tags */}
            <div className="absolute bottom-3 left-3 flex flex-wrap gap-1.5">
              {assetTags
                .filter((t) => t.type === 'dna')
                .map((tag, i) => (
                  <span
                    key={i}
                    className="bg-black/40 backdrop-blur-md border border-white/20 px-2.5 py-1 rounded-full text-[11px] font-medium text-white"
                  >
                    {tag.label}
                  </span>
                ))}
            </div>
          </div>

          {/* BOTTOM 55% — THE DEED */}
          <div className="px-8 pt-6 pb-8 bg-white">
            {/* Address */}
            <h2 className="text-xl font-bold text-slate-900 leading-tight mb-1">
              {truthCore.address || buildingData?.address || '123 Industrial Blvd'}
            </h2>
            <p className="text-slate-400 text-xs mb-4">
              {buildingData?.city && buildingData?.state
                ? `${buildingData.city}, ${buildingData.state} ${buildingData.zip || ''}`
                : 'Industrial'}
            </p>

            {/* Upgrade Tags (green) */}
            {assetTags.filter((t) => t.type === 'upgrade').length > 0 && (
              <div className="flex flex-wrap gap-2 mb-4">
                {assetTags
                  .filter((t) => t.type === 'upgrade')
                  .map((tag, i) => (
                    <span
                      key={i}
                      className="bg-emerald-500 text-white px-3 py-1 rounded-full text-xs font-bold shadow-sm"
                    >
                      {tag.label}
                    </span>
                  ))}
              </div>
            )}

            {/* Revenue Label */}
            <div className="flex items-center justify-center gap-1.5 mb-1 relative">
              <p className="text-slate-400 text-[10px] font-bold uppercase tracking-[0.2em]">
                {copy.phase6.revenueLabel}
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
            <div className="text-5xl font-bold text-emerald-600 mb-1 tracking-tight text-center">
              $<CountUp end={revenue} duration={1.0} separator="," />
              <span className="text-lg text-slate-400 font-normal">/yr</span>
            </div>

            {/* Rate lock text (production) or email prompt (smoke test) */}
            {copy.phase6.rateLockText && (
              <div className="flex justify-center items-center gap-2 text-slate-500 text-sm mb-6">
                <span>🔒</span>
                <span>{copy.phase6.rateLockText(truthCore.rateAsk.toFixed(2))}</span>
              </div>
            )}
            {copy.phase6.emailPrompt && (
              <div className="text-slate-500 text-sm mb-6 text-center space-y-0.5">
                {copy.phase6.emailPrompt.split('\n').map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            )}

            {/* THE SIGN / REPORT FLOW */}
            {!isActive ? (
              <div>
                <div className="bg-slate-50 p-1 rounded-xl border border-slate-200 mb-4">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleActivate()}
                    placeholder={copy.phase6.emailPlaceholder}
                    className="w-full bg-white rounded-lg px-4 py-3 outline-none border-b border-transparent focus:border-emerald-500 transition-colors text-slate-900 placeholder:text-slate-400"
                  />
                </div>

                <motion.button
                  onClick={handleActivate}
                  disabled={!emailValid || activating}
                  animate={{
                    backgroundColor: emailValid ? '#059669' : '#94a3b8',
                    boxShadow: emailValid
                      ? '0 10px 30px -10px rgba(16, 185, 129, 0.5)'
                      : '0 0 0 0 transparent',
                  }}
                  transition={{ duration: 0.3 }}
                  className="w-full text-white text-lg font-bold py-4 rounded-xl transition-all flex justify-center items-center gap-2 disabled:cursor-not-allowed"
                  style={{ opacity: emailValid ? 1 : 0.5 }}
                >
                  {isSmokeTest ? <Mail size={20} /> : <ShieldCheck size={20} />}
                  {activating
                    ? copy.phase6.buttonLoading
                    : emailValid
                    ? copy.phase6.button
                    : copy.phase6.buttonDisabled}
                </motion.button>

                <p className="text-xs text-slate-400 mt-4 max-w-xs mx-auto text-center">
                  {copy.phase6.legal}
                </p>
              </div>
            ) : (
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="py-6 text-center"
              >
                {isSmokeTest ? (
                  <>
                    <CheckCircle size={48} className="text-emerald-500 mx-auto mb-3" strokeWidth={2} />
                    <p className="text-emerald-800 font-bold text-xl mb-2">
                      {copy.phase6.successTitle}
                    </p>
                    <p className="text-slate-500 text-sm leading-relaxed max-w-xs mx-auto mb-6">
                      Check your inbox for the ${revenue.toLocaleString()}/yr breakdown.
                      <br />
                      We will notify you if a tenant matches your criteria.
                    </p>

                    {/* Onboarding CTA — post-EarnCheck */}
                    <div className="border-t border-slate-200 pt-6 mt-2">
                      <motion.button
                        onClick={() => {
                          const warehouseId = buildingData?.id;
                          const url = warehouseId
                            ? `/supplier/onboard?warehouse_id=${warehouseId}`
                            : '/supplier/onboard';
                          router.push(url);
                        }}
                        className="w-full bg-blue-600 hover:bg-blue-700 text-white text-lg font-bold py-4 rounded-xl transition-colors flex justify-center items-center gap-2 shadow-lg shadow-blue-600/25"
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.99 }}
                      >
                        Join the WEx Network
                      </motion.button>
                      <p className="text-slate-400 text-xs mt-3 text-center leading-relaxed">
                        Your property data is already on file — onboarding takes less than 5 minutes
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="space-y-4">
                    <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 text-center">
                      <p className="text-emerald-800 font-bold text-lg mb-1">
                        {copy.phase6.successTitle}
                      </p>
                      <p className="text-emerald-600 text-sm">
                        {copy.phase6.successSubtitle}
                      </p>
                    </div>
                    {copy.phase6.successLink && (
                      <div className="text-center">
                        <a
                          href={copy.phase6.successLink}
                          className="inline-block text-emerald-600 hover:text-emerald-700 text-sm font-medium underline underline-offset-4"
                        >
                          {copy.phase6.successLinkText}
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
