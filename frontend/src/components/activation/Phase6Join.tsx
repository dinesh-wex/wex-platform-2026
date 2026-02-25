'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, useMotionValue, useTransform, AnimatePresence } from 'framer-motion';
import CountUp from 'react-countup';
import { Check, ShieldCheck, ChevronDown, ChevronUp, Eye, EyeOff } from 'lucide-react';
import ConfettiOverlay from './shared/ConfettiOverlay';
import {
  TruthCore,
  BuildingData,
  RevenueEstimate,
  ContextualMemoryEntry,
  calculateRevenue,
} from './types';
import { api, signup as apiSignup } from '@/lib/api';
import { setToken } from '@/lib/auth';
import { trackEvent } from '@/lib/analytics';
import { useSupplier } from '@/components/supplier/SupplierAuthProvider';

interface Phase6JoinProps {
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

const AGREEMENT_TERMS = [
  {
    title: 'Platform Rules',
    content:
      'You agree to maintain accurate listing data, respond to tenant inquiries within 48 hours, and keep your availability status up to date. WEx may temporarily pause your listing if these standards are not met.',
  },
  {
    title: 'Anti-Circumvention',
    content:
      'Tenants introduced through the WEx network are WEx-sourced for 12 months after the initial introduction. Direct side-deals bypass the platform protections that benefit both parties.',
  },
  {
    title: 'Payout Terms',
    content:
      'WEx collects rent from tenants and pays suppliers within 5 business days of receipt. WEx retains a service fee (disclosed per deal) that covers tenant sourcing, insurance coordination, and ongoing support.',
  },
];

function buildAssetTags(bd: BuildingData | null, tc: TruthCore): AssetTag[] {
  const tags: AssetTag[] = [];
  if (bd?.year_built) tags.push({ label: `Built ${bd.year_built}`, type: 'dna' });
  if (bd?.clear_height_ft) tags.push({ label: `${bd.clear_height_ft}' Clear`, type: 'dna' });
  if (bd?.drive_in_bays) tags.push({ label: `${bd.drive_in_bays} Drive-in${bd.drive_in_bays > 1 ? 's' : ''}`, type: 'dna' });
  if (bd?.dock_doors_receiving) tags.push({ label: `${bd.dock_doors_receiving} Dock Doors`, type: 'dna' });
  if (bd?.has_sprinkler) tags.push({ label: 'Sprinklered', type: 'dna' });
  if (tc.activityTier === 'storage_light_assembly') tags.push({ label: 'Light Ops Permitted', type: 'upgrade' });
  if (tc.hasOffice) tags.push({ label: 'Office Included', type: 'upgrade' });
  if (tc.weekendAccess) tags.push({ label: 'Weekend Access', type: 'upgrade' });
  return tags;
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export default function Phase6Join(props: Phase6JoinProps) {
  const { truthCore, buildingData, setMemories } = props;
  const router = useRouter();
  const { login } = useSupplier();
  const [isActive, setIsActive] = useState(false);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [company, setCompany] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Agreement
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [expandedTerm, setExpandedTerm] = useState<number | null>(null);

  const revenue = calculateRevenue(truthCore);
  const assetTags = buildAssetTags(buildingData, truthCore);
  const emailValid = isValidEmail(email);
  const passwordValid = password.length >= 8;
  const nameValid = firstName.trim().length > 0 && lastName.trim().length > 0;
  const formValid = emailValid && passwordValid && nameValid && agreementAccepted;

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

  async function handleJoin() {
    if (!formValid) return;
    setActivating(true);
    setError(null);

    // 1. Try to create account on backend, then log in via auth context
    let signupSucceeded = false;
    try {
      const fullName = `${firstName.trim()} ${lastName.trim()}`;
      const result = await apiSignup(email, password, fullName, 'supplier', company || undefined);
      if (result?.access_token) {
        setToken(result.access_token);
        signupSucceeded = true;
        // Log in through auth provider so context state is updated
        try {
          await login(email, password);
        } catch {
          // Token already set — auth provider will pick it up on next mount
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '';
      // If email already registered, try logging in with the password
      if (message.includes('already registered')) {
        try {
          await login(email, password);
          signupSucceeded = true;
        } catch {
          console.warn('Login after duplicate signup failed');
        }
      } else {
        console.warn('Signup failed, continuing with local mode:', message);
      }
    }

    // 2. Build the activation payload
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
      activation_status: 'on',
    };

    // 3. Try to activate warehouse on backend
    // If signup/login succeeded, use authenticated call (assigns to new user's company).
    // If it failed, use anonymous call to avoid leaking a previous user's session.
    try {
      if (buildingData?.id) {
        if (signupSucceeded) {
          await api.activateWarehouse(buildingData.id, payload);
        } else {
          await api.activateWarehouseAnon(buildingData.id, payload);
        }
      }
    } catch {
      // Backend unavailable — continue with localStorage
    }

    // 4. Save to localStorage for demo/fallback mode
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
      status: 'active',
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
    localStorage.setItem('wex_activated_warehouses', JSON.stringify(filtered));

    // 5. Save supplier profile
    const supplierProfile = {
      id: `supplier-${Date.now()}`,
      name: `${firstName.trim()} ${lastName.trim()}`,
      company: company || (email.split('@')[1]?.split('.')[0] || 'Unknown').replace(/-/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
      email: email,
    };
    localStorage.setItem('wex_supplier', JSON.stringify(supplierProfile));

    // 6. Write memory
    addMemory(
      'Activation',
      `Warehouse activated: ${truthCore.sqft.toLocaleString()} sqft @ $${truthCore.rateAsk.toFixed(2)}/sqft/mo → $${revenue.toLocaleString()}/yr`,
      '🚀'
    );

    // 7. Track event
    trackEvent('supplier_joined', {
      email,
      revenue,
      sqft: truthCore.sqft,
      rateAsk: truthCore.rateAsk,
      pricingPath: truthCore.pricingPath,
      signupSucceeded,
      address: truthCore.address,
      state: buildingData?.state,
      city: buildingData?.city,
    });

    setActivating(false);
    setIsActive(true);
  }

  // Auto-redirect to dashboard after activation animation
  useEffect(() => {
    if (isActive) {
      const timer = setTimeout(() => router.push('/supplier'), 3000);
      return () => clearTimeout(timer);
    }
  }, [isActive, router]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="min-h-[calc(100vh-8rem)] flex flex-col justify-center items-center bg-slate-100 overflow-hidden py-8"
      style={{ perspective: 1000 }}
    >
      {isActive && <ConfettiOverlay />}

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
          {/* TOP — THE VIEW */}
          <div className="relative" style={{ height: '45%', minHeight: 200 }}>
            {bgImage ? (
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: `url(${bgImage})` }}
              />
            ) : (
              <div className="absolute inset-0 bg-gradient-to-br from-slate-600 via-slate-700 to-emerald-800" />
            )}

            {/* STATUS BADGE */}
            <div className="absolute top-4 right-4 z-20">
              <motion.div
                animate={{
                  backgroundColor: isActive ? '#10B981' : '#F59E0B',
                }}
                className="px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest text-white shadow-lg flex items-center gap-1.5"
              >
                {isActive ? (
                  <Check size={12} strokeWidth={4} />
                ) : (
                  <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                )}
                {isActive ? 'Asset Active' : 'Pending Activation'}
              </motion.div>
            </div>

            {/* ACTIVE STAMP */}
            {isActive && (
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

          {/* BOTTOM — THE DEED */}
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

            {/* Upgrade Tags */}
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

            {/* Revenue */}
            <p className="text-slate-400 text-[10px] font-bold uppercase tracking-[0.2em] text-center mb-1">
              Projected Annual Income
            </p>
            <div className="text-5xl font-bold text-emerald-600 mb-1 tracking-tight text-center">
              $<CountUp end={revenue} duration={1.0} separator="," />
              <span className="text-lg text-slate-400 font-normal">/yr</span>
            </div>
            <div className="flex justify-center items-center gap-2 text-slate-500 text-sm mb-6">
              <span>🔒</span>
              <span>${truthCore.rateAsk.toFixed(2)}/sqft Rate Locked via Warehouse Exchange</span>
            </div>

            {/* FORM OR SUCCESS */}
            {!isActive ? (
              <div>
                {/* Account Creation Form */}
                <div className="space-y-3 mb-5">
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      placeholder="First name"
                      className="w-1/2 bg-slate-50 rounded-lg px-4 py-3 outline-none border border-slate-200 focus:border-emerald-500 transition-colors text-slate-900 placeholder:text-slate-400"
                    />
                    <input
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      placeholder="Last name"
                      className="w-1/2 bg-slate-50 rounded-lg px-4 py-3 outline-none border border-slate-200 focus:border-emerald-500 transition-colors text-slate-900 placeholder:text-slate-400"
                    />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Email address"
                    className="w-full bg-slate-50 rounded-lg px-4 py-3 outline-none border border-slate-200 focus:border-emerald-500 transition-colors text-slate-900 placeholder:text-slate-400"
                  />
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Create password (min 8 characters)"
                      className="w-full bg-slate-50 rounded-lg px-4 py-3 pr-12 outline-none border border-slate-200 focus:border-emerald-500 transition-colors text-slate-900 placeholder:text-slate-400"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  <input
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="Company name (optional)"
                    className="w-full bg-slate-50 rounded-lg px-4 py-3 outline-none border border-slate-200 focus:border-emerald-500 transition-colors text-slate-900 placeholder:text-slate-400"
                  />
                </div>

                {/* Agreement Terms */}
                <div className="border border-slate-200 rounded-xl overflow-hidden mb-4">
                  <p className="px-4 py-2.5 bg-slate-50 text-xs font-bold text-slate-600 uppercase tracking-wider border-b border-slate-200">
                    WEx Network Agreement
                  </p>
                  {AGREEMENT_TERMS.map((term, i) => (
                    <div key={i} className="border-b border-slate-100 last:border-b-0">
                      <button
                        type="button"
                        onClick={() => setExpandedTerm(expandedTerm === i ? null : i)}
                        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-slate-50 transition-colors"
                      >
                        <span className="text-slate-700 text-sm font-medium">{term.title}</span>
                        {expandedTerm === i ? (
                          <ChevronUp size={14} className="text-slate-400" />
                        ) : (
                          <ChevronDown size={14} className="text-slate-400" />
                        )}
                      </button>
                      <AnimatePresence>
                        {expandedTerm === i && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="overflow-hidden"
                          >
                            <p className="px-4 pb-3 text-slate-500 text-xs leading-relaxed">
                              {term.content}
                            </p>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  ))}
                </div>

                {/* Agreement Checkbox */}
                <label className="flex items-start gap-3 cursor-pointer mb-5 group select-none">
                  <div className="shrink-0 mt-0.5">
                    <input
                      type="checkbox"
                      checked={agreementAccepted}
                      onChange={(e) => setAgreementAccepted(e.target.checked)}
                      className="w-5 h-5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer"
                    />
                  </div>
                  <span className="text-slate-600 text-xs leading-relaxed group-hover:text-slate-800 transition-colors">
                    I agree to the WEx Network Agreement and authorize Warehouse Exchange
                    to list my property and facilitate tenant placements on my behalf.
                  </span>
                </label>

                {/* Error */}
                {error && (
                  <p className="text-red-500 text-xs text-center mb-3">{error}</p>
                )}

                {/* Validation hint — show what's missing */}
                {!formValid && (email || firstName || password) && (
                  <p className="text-slate-400 text-xs text-center mb-3">
                    {!nameValid && 'First and last name required. '}
                    {!emailValid && 'Valid email required. '}
                    {!passwordValid && 'Password must be 8+ characters. '}
                    {!agreementAccepted && 'Please accept the agreement.'}
                  </p>
                )}

                {/* CTA Button */}
                <button
                  onClick={handleJoin}
                  disabled={!formValid || activating}
                  className={`w-full text-white text-lg font-bold py-4 rounded-xl transition-all flex justify-center items-center gap-2 ${
                    formValid
                      ? 'bg-emerald-600 hover:bg-emerald-700 shadow-lg shadow-emerald-600/25 cursor-pointer'
                      : 'bg-slate-400 cursor-not-allowed opacity-50'
                  }`}
                >
                  <ShieldCheck size={20} />
                  {activating ? 'Activating...' : 'Join the WEx Network'}
                </button>

                <p className="text-xs text-slate-400 mt-4 max-w-xs mx-auto text-center">
                  By clicking, you accept the WEx Capacity Agreement and grant programmatic matching rights.
                </p>
              </div>
            ) : (
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="py-6 text-center"
              >
                <div className="space-y-4">
                  <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 text-center">
                    <p className="text-emerald-800 font-bold text-lg mb-1">
                      System Active
                    </p>
                    <p className="text-emerald-600 text-sm">
                      Matching tenants to your criteria...
                    </p>
                  </div>
                  <div className="text-center">
                    <a
                      href="/supplier"
                      className="inline-block text-emerald-600 hover:text-emerald-700 text-sm font-medium underline underline-offset-4"
                    >
                      Go to Dashboard →
                    </a>
                  </div>
                </div>
              </motion.div>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
