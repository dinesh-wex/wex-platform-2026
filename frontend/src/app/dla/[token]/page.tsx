'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Building2,
  MapPin,
  Ruler,
  DollarSign,
  Shield,
  Clock,
  TrendingUp,
  AlertCircle,
  ArrowRight,
} from 'lucide-react';
import { api } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PropertyData {
  warehouse_id: string;
  address: string;
  city?: string;
  state?: string;
  zip?: string;
  building_size_sqft?: number;
  year_built?: number;
  construction_type?: string;
  property_type?: string;
  primary_image_url?: string;
  owner_name?: string;
  clear_height_ft?: number;
  dock_doors_receiving?: number;
  dock_doors_shipping?: number;
  drive_in_bays?: number;
  parking_spaces?: number;
  has_office_space?: boolean;
  has_sprinkler?: boolean;
  power_supply?: string;
}

interface BuyerRequirement {
  sqft_needed?: number;
  min_sqft?: number;
  max_sqft?: number;
  use_type?: string;
  needed_from?: string;
  duration_months?: number;
  city?: string;
  state?: string;
}

interface MarketRange {
  low: number;
  high: number;
  source?: string;
}

interface DLAData {
  token: string;
  status: string;
  property_data: PropertyData;
  buyer_requirement: BuyerRequirement;
  suggested_rate: number;
  market_range: MarketRange;
  expires_at: string;
}

type DLAStep = 'loading' | 'property_confirm' | 'deal' | 'rate_decision' | 'agreement' | 'success' | 'error';

// ---------------------------------------------------------------------------
// Agreement Terms
// ---------------------------------------------------------------------------

const AGREEMENT_TERMS = [
  {
    title: 'WEx Network Terms',
    content:
      'By joining the WEx Network, you agree to maintain accurate listing data, respond to tenant inquiries promptly, and keep your availability status current. WEx handles tenant sourcing, payments, and insurance coordination.',
  },
  {
    title: 'Anti-Circumvention',
    content:
      'Tenants introduced through WEx are WEx-sourced for 12 months after the initial introduction. This protects both parties and ensures the platform can continue providing deal flow.',
  },
  {
    title: 'Payment Terms',
    content:
      'WEx collects rent from tenants and deposits your share within 5 business days. WEx retains a transparent service fee (disclosed per deal) covering tenant sourcing, insurance, and ongoing support.',
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DLAPage() {
  const params = useParams();
  const token = params.token as string;

  const [step, setStep] = useState<DLAStep>('loading');
  const [data, setData] = useState<DLAData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Rate decision state
  const [rateMode, setRateMode] = useState<'accept' | 'counter' | null>(null);
  const [counterRate, setCounterRate] = useState('');
  const [rateResponse, setRateResponse] = useState<any>(null);
  const [submittingRate, setSubmittingRate] = useState(false);

  // Agreement state
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [expandedTerm, setExpandedTerm] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);

  // ---------------------------------------------------------------------------
  // Load DLA token data
  // ---------------------------------------------------------------------------

  const loadToken = useCallback(async () => {
    try {
      const result = await api.resolveDLAToken(token);
      setData(result);
      // If token was already progressed, jump to appropriate step
      if (result.status === 'rate_decided') {
        setStep('agreement');
      } else if (result.status === 'confirmed') {
        setStep('success');
      } else {
        setStep('property_confirm');
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'This link is invalid or has expired.';
      setError(message);
      setStep('error');
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      loadToken();
    }
  }, [token, loadToken]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handlePropertyConfirm() {
    setStep('deal');
  }

  function handlePropertyCorrect() {
    // In a full implementation, this would open an edit form
    // For now, proceed with a note
    setStep('deal');
  }

  function handleViewDeal() {
    setStep('rate_decision');
  }

  async function handleRateSubmit() {
    if (!data) return;
    setSubmittingRate(true);
    setError(null);

    try {
      const accepted = rateMode === 'accept';
      const proposed_rate = !accepted ? parseFloat(counterRate) : undefined;

      if (!accepted && (!counterRate || isNaN(proposed_rate!))) {
        setError('Please enter a valid rate.');
        setSubmittingRate(false);
        return;
      }

      const result = await api.submitDLARate(token, {
        accepted,
        proposed_rate,
      });

      setRateResponse(result);
      setStep('agreement');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to submit rate.';
      setError(message);
    } finally {
      setSubmittingRate(false);
    }
  }

  async function handleConfirmAgreement() {
    if (!agreementAccepted || !data) return;
    setConfirming(true);
    setError(null);

    try {
      await api.confirmDLA(token, {
        agreement_ref: `dla-${token}-${Date.now()}`,
        stripe_setup: false,
      });
      setStep('success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to confirm agreement.';
      setError(message);
    } finally {
      setConfirming(false);
    }
  }

  async function handleDecline(reason?: string) {
    try {
      await api.storeDLAOutcome(token, {
        outcome: 'declined',
        reason: reason || 'Declined via DLA page',
      });
    } catch {
      // Silently fail — don't block the user
    }
  }

  // ---------------------------------------------------------------------------
  // Computed values
  // ---------------------------------------------------------------------------

  const property = data?.property_data;
  const buyer = data?.buyer_requirement;
  const suggestedRate = data?.suggested_rate || 0;
  const marketRange = data?.market_range || { low: 0, high: 0 };
  const sqft = buyer?.sqft_needed || buyer?.max_sqft || 0;
  const estimatedMonthly = suggestedRate && sqft ? Math.round(suggestedRate * sqft) : 0;
  const expiresAt = data?.expires_at ? new Date(data.expires_at) : null;

  // ---------------------------------------------------------------------------
  // Step indicator
  // ---------------------------------------------------------------------------

  const steps = ['Confirm', 'Deal', 'Rate', 'Agreement', 'Live'];
  const stepIndex = {
    loading: -1,
    property_confirm: 0,
    deal: 1,
    rate_decision: 2,
    agreement: 3,
    success: 4,
    error: -1,
  }[step];

  // ---------------------------------------------------------------------------
  // UI
  // ---------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-lg mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 bg-blue-600/10 border border-blue-500/20 rounded-full px-4 py-1.5 mb-4">
            <Shield size={14} className="text-blue-400" />
            <span className="text-blue-400 text-xs font-bold tracking-wider uppercase">
              Warehouse Exchange
            </span>
          </div>

          {/* Expiry countdown */}
          {expiresAt && step !== 'success' && step !== 'error' && (
            <div className="flex items-center justify-center gap-1.5 text-amber-400 text-xs mb-3">
              <Clock size={12} />
              <span>
                Offer expires {expiresAt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} at{' '}
                {expiresAt.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
              </span>
            </div>
          )}
        </div>

        {/* Step progress */}
        {stepIndex >= 0 && step !== 'success' && (
          <div className="flex items-center justify-between mb-8 px-2">
            {steps.map((label, i) => (
              <div key={label} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                      i <= stepIndex
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-800 text-gray-600 border border-gray-700'
                    }`}
                  >
                    {i < stepIndex ? (
                      <CheckCircle size={14} />
                    ) : (
                      i + 1
                    )}
                  </div>
                  <span
                    className={`text-[10px] mt-1 ${
                      i <= stepIndex ? 'text-blue-400' : 'text-gray-600'
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {i < steps.length - 1 && (
                  <div
                    className={`w-8 h-px mx-1 mb-4 ${
                      i < stepIndex ? 'bg-blue-600' : 'bg-gray-800'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        <AnimatePresence mode="wait">
          {/* ── LOADING ────────────────────────────────────────────── */}
          {step === 'loading' && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center py-20"
            >
              <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
              <p className="text-gray-500 text-sm">Loading your property details...</p>
            </motion.div>
          )}

          {/* ── ERROR ──────────────────────────────────────────────── */}
          {step === 'error' && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-16"
            >
              <AlertCircle size={48} className="text-red-400 mx-auto mb-4" />
              <h2 className="text-xl font-bold text-white mb-2">Link Unavailable</h2>
              <p className="text-gray-400 text-sm max-w-sm mx-auto">
                {error || 'This link is invalid or has expired. If you received this link recently, please contact us.'}
              </p>
            </motion.div>
          )}

          {/* ── STEP 1: PROPERTY CONFIRM ───────────────────────────── */}
          {step === 'property_confirm' && property && (
            <motion.div
              key="property_confirm"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <h2 className="text-xl font-bold text-white text-center mb-2">
                Is this your property?
              </h2>
              <p className="text-gray-400 text-sm text-center mb-6">
                We have this building on file. Confirm or correct the details.
              </p>

              {/* Property Card */}
              <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden mb-6">
                {property.primary_image_url && (
                  <div
                    className="h-40 bg-cover bg-center"
                    style={{ backgroundImage: `url(${property.primary_image_url})` }}
                  />
                )}

                <div className="p-5 space-y-4">
                  <div className="flex items-start gap-3">
                    <MapPin size={18} className="text-blue-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-white font-semibold">{property.address}</p>
                      <p className="text-gray-500 text-sm">
                        {[property.city, property.state, property.zip].filter(Boolean).join(', ')}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    {property.building_size_sqft && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Ruler size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300">
                          {property.building_size_sqft.toLocaleString()} sqft
                        </span>
                      </div>
                    )}
                    {property.construction_type && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Building2 size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300 capitalize">
                          {property.construction_type}
                        </span>
                      </div>
                    )}
                    {property.clear_height_ft && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Ruler size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300">
                          {property.clear_height_ft}&apos; clear
                        </span>
                      </div>
                    )}
                    {property.dock_doors_receiving != null && property.dock_doors_receiving > 0 && (
                      <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg px-3 py-2">
                        <Building2 size={14} className="text-gray-400" />
                        <span className="text-sm text-gray-300">
                          {property.dock_doors_receiving} dock doors
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {property.has_office_space && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        Office Included
                      </span>
                    )}
                    {property.has_sprinkler && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        Sprinklered
                      </span>
                    )}
                    {property.drive_in_bays != null && property.drive_in_bays > 0 && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        {property.drive_in_bays} Drive-in{property.drive_in_bays > 1 ? 's' : ''}
                      </span>
                    )}
                    {property.parking_spaces != null && property.parking_spaces > 0 && (
                      <span className="bg-blue-600/20 text-blue-400 px-2.5 py-1 rounded-full text-xs font-medium">
                        {property.parking_spaces} Parking
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handlePropertyCorrect}
                  className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium py-3.5 rounded-xl transition-colors border border-gray-700"
                >
                  Something&apos;s Wrong
                </button>
                <button
                  onClick={handlePropertyConfirm}
                  className="flex-[2] bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl transition-colors"
                >
                  Yes, This Is Mine
                </button>
              </div>
            </motion.div>
          )}

          {/* ── STEP 2: THE DEAL ───────────────────────────────────── */}
          {step === 'deal' && buyer && (
            <motion.div
              key="deal"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <h2 className="text-xl font-bold text-white text-center mb-2">
                There&apos;s a Deal on the Table
              </h2>
              <p className="text-gray-400 text-sm text-center mb-6">
                A company is actively looking for space that matches your property.
              </p>

              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 mb-6 space-y-5">
                {/* Buyer requirement summary */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 text-sm">Space Needed</span>
                    <span className="text-white font-semibold">
                      {(buyer.sqft_needed || buyer.max_sqft || 0).toLocaleString()} sqft
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 text-sm">Use Type</span>
                    <span className="text-white font-semibold capitalize">
                      {buyer.use_type || 'General'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 text-sm">Starting</span>
                    <span className="text-white font-semibold">
                      {buyer.needed_from || 'ASAP'}
                    </span>
                  </div>
                  {buyer.duration_months && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500 text-sm">Term</span>
                      <span className="text-white font-semibold">
                        {buyer.duration_months} months
                      </span>
                    </div>
                  )}
                </div>

                {/* Rate highlight */}
                <div className="border-t border-gray-800 pt-4">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign size={16} className="text-emerald-400" />
                    <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">
                      Proposed Rate
                    </span>
                  </div>
                  <p className="text-3xl font-bold text-emerald-400">
                    ${suggestedRate.toFixed(2)}
                    <span className="text-sm text-gray-500 font-normal">/sqft/mo</span>
                  </p>
                  {estimatedMonthly > 0 && (
                    <p className="text-gray-400 text-sm mt-1">
                      That&apos;s ~<span className="text-emerald-400 font-semibold">${estimatedMonthly.toLocaleString()}</span>/month
                    </p>
                  )}
                </div>

                {/* Market range context */}
                {marketRange.high > 0 && (
                  <div className="bg-gray-800/50 rounded-xl p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp size={14} className="text-blue-400" />
                      <span className="text-gray-400 text-xs font-bold uppercase tracking-wider">
                        Market Range
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500 text-sm">${marketRange.low.toFixed(2)}</span>
                      <div className="flex-1 mx-3 h-1.5 bg-gray-700 rounded-full relative">
                        {/* Marker for suggested rate */}
                        <div
                          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-emerald-400 rounded-full border-2 border-gray-900"
                          style={{
                            left: `${Math.min(100, Math.max(0, ((suggestedRate - marketRange.low) / (marketRange.high - marketRange.low)) * 100))}%`,
                          }}
                        />
                      </div>
                      <span className="text-gray-500 text-sm">${marketRange.high.toFixed(2)}</span>
                    </div>
                    <p className="text-gray-600 text-xs mt-1 text-center">
                      NNN lease rates in your area
                    </p>
                  </div>
                )}
              </div>

              <button
                onClick={handleViewDeal}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                Continue
                <ArrowRight size={18} />
              </button>
            </motion.div>
          )}

          {/* ── STEP 3: RATE DECISION ──────────────────────────────── */}
          {step === 'rate_decision' && (
            <motion.div
              key="rate_decision"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <h2 className="text-xl font-bold text-white text-center mb-2">
                Your Rate Decision
              </h2>
              <p className="text-gray-400 text-sm text-center mb-6">
                Accept the proposed rate for the fastest path, or set your own.
              </p>

              <div className="space-y-3 mb-6">
                {/* Accept option */}
                <button
                  onClick={() => { setRateMode('accept'); setError(null); }}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    rateMode === 'accept'
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-gray-800 bg-gray-900 hover:border-gray-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-white font-semibold">Accept ${suggestedRate.toFixed(2)}/sqft</p>
                      <p className="text-gray-500 text-sm mt-0.5">
                        Fastest path to agreement — recommended rate
                      </p>
                    </div>
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                        rateMode === 'accept'
                          ? 'border-emerald-500 bg-emerald-500'
                          : 'border-gray-600'
                      }`}
                    >
                      {rateMode === 'accept' && <CheckCircle size={12} className="text-white" />}
                    </div>
                  </div>
                </button>

                {/* Counter option */}
                <button
                  onClick={() => { setRateMode('counter'); setError(null); }}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    rateMode === 'counter'
                      ? 'border-blue-500 bg-blue-500/10'
                      : 'border-gray-800 bg-gray-900 hover:border-gray-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-white font-semibold">Set My Own Rate</p>
                      <p className="text-gray-500 text-sm mt-0.5">
                        We&apos;ll present your rate to the buyer honestly
                      </p>
                    </div>
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                        rateMode === 'counter'
                          ? 'border-blue-500 bg-blue-500'
                          : 'border-gray-600'
                      }`}
                    >
                      {rateMode === 'counter' && <CheckCircle size={12} className="text-white" />}
                    </div>
                  </div>
                </button>
              </div>

              {/* Counter rate input */}
              {rateMode === 'counter' && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="mb-6"
                >
                  <label className="block text-gray-400 text-sm mb-2">
                    Your rate per sqft/month
                  </label>
                  <div className="relative">
                    <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 text-lg">$</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={counterRate}
                      onChange={(e) => setCounterRate(e.target.value)}
                      placeholder={suggestedRate.toFixed(2)}
                      className="w-full bg-gray-900 border border-gray-700 rounded-xl pl-8 pr-16 py-3.5 text-white text-lg focus:outline-none focus:border-blue-500 transition-colors"
                    />
                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">/sqft</span>
                  </div>
                  {counterRate && parseFloat(counterRate) > 0 && sqft > 0 && (
                    <p className="text-gray-500 text-sm mt-2">
                      = ${(parseFloat(counterRate) * sqft).toLocaleString(undefined, { maximumFractionDigits: 0 })}/month
                    </p>
                  )}

                  {/* Honest context about counter rates */}
                  <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-3 mt-3">
                    <p className="text-amber-400 text-xs leading-relaxed">
                      We&apos;ll present your rate to the buyer along with other options in their budget range.
                      Rates closer to ${suggestedRate.toFixed(2)}/sqft tend to win more often.
                    </p>
                  </div>
                </motion.div>
              )}

              {/* Submit button */}
              {rateMode && (
                <motion.button
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  onClick={handleRateSubmit}
                  disabled={submittingRate || (rateMode === 'counter' && (!counterRate || parseFloat(counterRate) <= 0))}
                  className={`w-full font-bold py-4 rounded-xl transition-all flex items-center justify-center gap-2 ${
                    submittingRate || (rateMode === 'counter' && (!counterRate || parseFloat(counterRate) <= 0))
                      ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                      : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }`}
                >
                  {submittingRate ? (
                    <>
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Submitting...
                    </>
                  ) : rateMode === 'accept' ? (
                    <>Accept &amp; Continue</>
                  ) : (
                    <>Submit My Rate</>
                  )}
                </motion.button>
              )}

              {/* Decline link */}
              <button
                onClick={() => { handleDecline('Not interested from rate page'); setStep('error'); setError('No problem. Your property stays on file.'); }}
                className="w-full text-gray-600 hover:text-gray-500 text-sm mt-4 transition-colors"
              >
                Not interested right now
              </button>

              {error && (
                <p className="text-red-400 text-sm text-center mt-4">{error}</p>
              )}
            </motion.div>
          )}

          {/* ── STEP 4: AGREEMENT ──────────────────────────────────── */}
          {step === 'agreement' && (
            <motion.div
              key="agreement"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <h2 className="text-xl font-bold text-white text-center mb-2">
                Almost There
              </h2>
              <p className="text-gray-400 text-sm text-center mb-6">
                Review and accept the network agreement to go live.
              </p>

              {/* Rate confirmation banner */}
              {rateResponse && (
                <div className={`rounded-xl p-4 mb-6 border ${
                  rateResponse.within_budget === false
                    ? 'bg-amber-500/10 border-amber-500/20'
                    : 'bg-emerald-500/10 border-emerald-500/20'
                }`}>
                  <p className={`text-sm ${
                    rateResponse.within_budget === false ? 'text-amber-400' : 'text-emerald-400'
                  }`}>
                    {rateResponse.message}
                  </p>
                </div>
              )}

              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 mb-6">
                <h3 className="text-white font-semibold text-lg mb-4">
                  WEx Network Agreement
                </h3>

                <div className="space-y-2 mb-6">
                  {AGREEMENT_TERMS.map((term, i) => (
                    <div
                      key={i}
                      className="border border-gray-800 rounded-lg overflow-hidden"
                    >
                      <button
                        onClick={() => setExpandedTerm(expandedTerm === i ? null : i)}
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

              <motion.button
                onClick={handleConfirmAgreement}
                disabled={!agreementAccepted || confirming}
                className={`w-full text-lg font-bold py-4 rounded-xl transition-all flex justify-center items-center gap-2 ${
                  agreementAccepted
                    ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/25'
                    : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                }`}
                whileHover={agreementAccepted ? { scale: 1.01 } : {}}
                whileTap={agreementAccepted ? { scale: 0.99 } : {}}
              >
                {confirming ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Activating...
                  </>
                ) : (
                  <>
                    <Shield size={20} />
                    Confirm &amp; Go Live
                  </>
                )}
              </motion.button>

              <button
                onClick={() => setStep('rate_decision')}
                className="w-full text-gray-500 hover:text-gray-400 text-sm mt-4 transition-colors"
              >
                Back to rate
              </button>

              {error && (
                <p className="text-red-400 text-sm text-center mt-4">{error}</p>
              )}
            </motion.div>
          )}

          {/* ── STEP 5: SUCCESS ────────────────────────────────────── */}
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
                You&apos;re Live!
              </h2>
              <p className="text-gray-400 text-sm leading-relaxed max-w-sm mx-auto mb-8">
                Your property is now active on the WEx network. The buyer has been
                notified and you&apos;ll hear from us shortly with next steps.
              </p>

              {estimatedMonthly > 0 && (
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-6 inline-block">
                  <p className="text-gray-500 text-xs font-bold uppercase tracking-wider mb-1">
                    Estimated Monthly Income
                  </p>
                  <p className="text-3xl font-bold text-emerald-400">
                    ${estimatedMonthly.toLocaleString()}
                    <span className="text-sm text-gray-500 font-normal">/mo</span>
                  </p>
                </div>
              )}

              <div className="space-y-3">
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                  <h3 className="text-white font-semibold text-sm mb-2">What happens next?</h3>
                  <ul className="text-gray-400 text-sm space-y-2 text-left">
                    <li className="flex items-start gap-2">
                      <CheckCircle size={14} className="text-emerald-400 mt-0.5 shrink-0" />
                      <span>Buyer has been notified of your availability</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle size={14} className="text-emerald-400 mt-0.5 shrink-0" />
                      <span>If the buyer selects your space, we&apos;ll coordinate a tour</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle size={14} className="text-emerald-400 mt-0.5 shrink-0" />
                      <span>Your property is now visible to all qualified tenants</span>
                    </li>
                  </ul>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
