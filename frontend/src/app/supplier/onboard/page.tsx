'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle, ChevronDown, ChevronUp, Building2, MapPin, Ruler, DollarSign, Edit3, Shield } from 'lucide-react';
import { api, fetchAPI } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WarehouseData {
  id: string;
  address: string;
  city?: string;
  state?: string;
  zip?: string;
  building_size_sqft?: number;
  year_built?: number;
  construction_type?: string;
  property_type?: string;
  primary_image_url?: string;
  truth_core?: {
    supplier_rate_per_sqft?: number;
    activity_tier?: string;
    min_sqft?: number;
    max_sqft?: number;
    has_office_space?: boolean;
    clear_height_ft?: number;
    dock_doors_receiving?: number;
    drive_in_bays?: number;
    has_sprinkler?: boolean;
  } | null;
}

type OnboardStep = 'loading' | 'review' | 'agreement' | 'success';

// ---------------------------------------------------------------------------
// Agreement Terms (expandable)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SupplierOnboardPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" /></div>}>
      <SupplierOnboardContent />
    </Suspense>
  );
}

function SupplierOnboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const warehouseId = searchParams.get('warehouse_id');

  const [step, setStep] = useState<OnboardStep>('loading');
  const [warehouse, setWarehouse] = useState<WarehouseData | null>(null);
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [expandedTerm, setExpandedTerm] = useState<number | null>(null);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Load warehouse data
  // ---------------------------------------------------------------------------

  const loadWarehouse = useCallback(async (id: string) => {
    try {
      const data = await api.getWarehouse(id);
      setWarehouse(data);
      setStep('review');
    } catch {
      setError('Could not load property data. Please try again.');
      setStep('review');
    }
  }, []);

  useEffect(() => {
    if (warehouseId) {
      loadWarehouse(warehouseId);
    } else {
      // Path B: no existing property data -> redirect to EarnCheck with onboard flag
      router.replace('/supplier/earncheck?onboard=true');
    }
  }, [warehouseId, loadWarehouse, router]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleConfirm() {
    setStep('agreement');
  }

  function handleEdit() {
    // Send back to EarnCheck with warehouse pre-loaded
    router.push(`/supplier/earncheck?warehouse_id=${warehouseId}&onboard=true`);
  }

  async function handleActivate() {
    if (!agreementAccepted || !warehouse) return;
    setActivating(true);
    setError(null);

    try {
      await fetchAPI('/api/supplier/onboard', {
        method: 'POST',
        body: JSON.stringify({
          warehouse_id: warehouse.id,
          agreement_accepted: true,
        }),
      });
      setStep('success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Activation failed';
      setError(message);
    } finally {
      setActivating(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const rate = warehouse?.truth_core?.supplier_rate_per_sqft;
  const sqft = warehouse?.truth_core?.max_sqft || warehouse?.building_size_sqft;
  const estimatedMonthly = rate && sqft ? Math.round(rate * sqft) : null;
  const estimatedAnnual = estimatedMonthly ? estimatedMonthly * 12 : null;

  // ---------------------------------------------------------------------------
  // UI
  // ---------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-lg mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 bg-blue-600/10 border border-blue-500/20 rounded-full px-4 py-1.5 mb-4">
            <Shield size={14} className="text-blue-400" />
            <span className="text-blue-400 text-xs font-bold tracking-wider uppercase">
              WEx Network Onboarding
            </span>
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">
            {step === 'success' ? 'Welcome to the Network' : 'Join the WEx Network'}
          </h1>
          <p className="text-gray-400 text-sm">
            {step === 'loading' && 'Loading your property data...'}
            {step === 'review' && 'Review your property details and confirm to continue.'}
            {step === 'agreement' && 'Review and accept the network agreement to activate.'}
            {step === 'success' && 'Your listing is live and visible to qualified tenants.'}
          </p>
        </div>

        <AnimatePresence mode="wait">
          {/* ── LOADING ─────────────────────────────────────────────── */}
          {step === 'loading' && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex justify-center py-20"
            >
              <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </motion.div>
          )}

          {/* ── REVIEW STEP ─────────────────────────────────────────── */}
          {step === 'review' && warehouse && (
            <motion.div
              key="review"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              {/* Property Card */}
              <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden mb-6">
                {/* Image header */}
                {warehouse.primary_image_url && (
                  <div
                    className="h-40 bg-cover bg-center"
                    style={{ backgroundImage: `url(${warehouse.primary_image_url})` }}
                  />
                )}

                <div className="p-6 space-y-4">
                  {/* Address */}
                  <div className="flex items-start gap-3">
                    <MapPin size={18} className="text-blue-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-white font-semibold">{warehouse.address}</p>
                      <p className="text-gray-500 text-sm">
                        {[warehouse.city, warehouse.state, warehouse.zip].filter(Boolean).join(', ')}
                      </p>
                    </div>
                  </div>

                  {/* Building details */}
                  <div className="grid grid-cols-2 gap-3">
                    {warehouse.building_size_sqft && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Ruler size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300">
                          {warehouse.building_size_sqft.toLocaleString()} sqft
                        </span>
                      </div>
                    )}
                    {warehouse.construction_type && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Building2 size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300 capitalize">
                          {warehouse.construction_type}
                        </span>
                      </div>
                    )}
                    {warehouse.truth_core?.clear_height_ft && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Ruler size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300">
                          {warehouse.truth_core.clear_height_ft}&apos; clear
                        </span>
                      </div>
                    )}
                    {warehouse.truth_core?.dock_doors_receiving != null && warehouse.truth_core.dock_doors_receiving > 0 && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Building2 size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300">
                          {warehouse.truth_core.dock_doors_receiving} dock doors
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Feature tags */}
                  <div className="flex flex-wrap gap-2">
                    {warehouse.truth_core?.has_office_space && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        Office Included
                      </span>
                    )}
                    {warehouse.truth_core?.has_sprinkler && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        Sprinklered
                      </span>
                    )}
                    {warehouse.truth_core?.drive_in_bays != null && warehouse.truth_core.drive_in_bays > 0 && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        {warehouse.truth_core.drive_in_bays} Drive-in{warehouse.truth_core.drive_in_bays > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>

                  {/* Estimated rate */}
                  {rate && (
                    <div className="border-t border-gray-800 pt-4">
                      <div className="flex items-center gap-2 mb-1">
                        <DollarSign size={14} className="text-emerald-400" />
                        <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">
                          Estimated Rate
                        </span>
                      </div>
                      <p className="text-2xl font-bold text-emerald-400">
                        ${rate.toFixed(2)}
                        <span className="text-sm text-gray-500 font-normal">/sqft/mo</span>
                      </p>
                      {estimatedAnnual && (
                        <p className="text-gray-500 text-sm mt-0.5">
                          ~${estimatedAnnual.toLocaleString()}/yr projected
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Confirmation prompt */}
              <p className="text-center text-gray-300 text-sm font-medium mb-4">
                Everything look correct?
              </p>

              <div className="flex gap-3">
                <button
                  onClick={handleEdit}
                  className="flex-1 flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium py-3.5 rounded-xl transition-colors border border-gray-700"
                >
                  <Edit3 size={16} />
                  Edit
                </button>
                <button
                  onClick={handleConfirm}
                  className="flex-[2] bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl transition-colors"
                >
                  Confirm &amp; Continue
                </button>
              </div>

              {error && (
                <p className="text-red-400 text-sm text-center mt-4">{error}</p>
              )}
            </motion.div>
          )}

          {/* ── AGREEMENT STEP ──────────────────────────────────────── */}
          {step === 'agreement' && (
            <motion.div
              key="agreement"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-6">
                <h3 className="text-white font-semibold text-lg mb-4">
                  WEx Network Agreement
                </h3>

                {/* Expandable terms */}
                <div className="space-y-2 mb-6">
                  {AGREEMENT_TERMS.map((term, i) => (
                    <div
                      key={i}
                      className="border border-gray-800 rounded-lg overflow-hidden"
                    >
                      <button
                        onClick={() =>
                          setExpandedTerm(expandedTerm === i ? null : i)
                        }
                        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-800/50 transition-colors"
                      >
                        <span className="text-gray-300 text-sm font-medium">
                          {term.title}
                        </span>
                        {expandedTerm === i ? (
                          <ChevronUp size={16} className="text-gray-500" />
                        ) : (
                          <ChevronDown size={16} className="text-gray-500" />
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
                            <p className="px-4 pb-3 text-gray-500 text-sm leading-relaxed">
                              {term.content}
                            </p>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  ))}
                </div>

                {/* Agreement checkbox */}
                <label className="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={agreementAccepted}
                    onChange={(e) => setAgreementAccepted(e.target.checked)}
                    className="mt-0.5 w-5 h-5 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
                  />
                  <span className="text-gray-300 text-sm leading-relaxed group-hover:text-gray-200 transition-colors">
                    I agree to the WEx Network Agreement and authorize Warehouse Exchange
                    to list my property and facilitate tenant placements on my behalf.
                  </span>
                </label>
              </div>

              {/* Activate button */}
              <motion.button
                onClick={handleActivate}
                disabled={!agreementAccepted || activating}
                className={`w-full text-lg font-bold py-4 rounded-xl transition-all flex justify-center items-center gap-2 ${
                  agreementAccepted
                    ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/25'
                    : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                }`}
                whileHover={agreementAccepted ? { scale: 1.01 } : {}}
                whileTap={agreementAccepted ? { scale: 0.99 } : {}}
              >
                {activating ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Activating...
                  </>
                ) : (
                  <>
                    <Shield size={20} />
                    Activate My Listing
                  </>
                )}
              </motion.button>

              {/* Back link */}
              <button
                onClick={() => setStep('review')}
                className="w-full text-gray-500 hover:text-gray-400 text-sm mt-4 transition-colors"
              >
                Back to review
              </button>

              {error && (
                <p className="text-red-400 text-sm text-center mt-4">{error}</p>
              )}
            </motion.div>
          )}

          {/* ── SUCCESS STEP ────────────────────────────────────────── */}
          {step === 'success' && (
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4 }}
              className="text-center py-8"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 300, damping: 15, delay: 0.2 }}
              >
                <CheckCircle size={64} className="text-emerald-400 mx-auto mb-4" strokeWidth={1.5} />
              </motion.div>

              <h2 className="text-2xl font-bold text-white mb-2">
                You&apos;re In the Network
              </h2>
              <p className="text-gray-400 text-sm leading-relaxed max-w-sm mx-auto mb-8">
                Your listing is now active on the WEx platform. Qualified tenants in your
                area can now see your space. We&apos;ll notify you as soon as there&apos;s a match.
              </p>

              {estimatedAnnual && (
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-8 inline-block">
                  <p className="text-gray-500 text-xs font-bold uppercase tracking-wider mb-1">
                    Projected Annual Income
                  </p>
                  <p className="text-3xl font-bold text-emerald-400">
                    ${estimatedAnnual.toLocaleString()}
                    <span className="text-sm text-gray-500 font-normal">/yr</span>
                  </p>
                </div>
              )}

              <div>
                <button
                  onClick={() => router.push('/supplier')}
                  className="bg-blue-600 hover:bg-blue-700 text-white font-bold px-8 py-3.5 rounded-xl transition-colors"
                >
                  Go to Dashboard
                </button>
              </div>
            </motion.div>
          )}

          {/* ── ERROR STATE (no warehouse) ──────────────────────────── */}
          {step === 'review' && !warehouse && error && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-12"
            >
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={() => router.push('/supplier/earncheck')}
                className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-3 rounded-xl transition-colors"
              >
                Start EarnCheck
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
