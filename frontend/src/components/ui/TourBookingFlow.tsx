"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Loader2,
  CheckCircle2,
  MapPin,
  Calendar,
  Clock,
  Shield,
  Building2,
  Lock,
  Unlock,
  ChevronRight,
  AlertCircle,
} from "lucide-react";
import AgreementCheckbox from "@/components/ui/AgreementCheckbox";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface WarehouseInfo {
  id: string;
  address?: string | null;
  city?: string;
  state?: string;
  zip?: string | null;
  lat?: number | null;
  lng?: number | null;
  building_size_sqft?: number;
  primary_image_url?: string | null;
  year_built?: number;
  construction_type?: string;
}

interface DealInfo {
  id: string;
  warehouse_id: string;
  sqft_allocated: number;
  rate_per_sqft: number;
  monthly_payment: number;
  term_months: number;
  guarantee_signed_at?: string | null;
  status: string;
}

export interface TourBookingFlowProps {
  open: boolean;
  onClose: () => void;
  deal: DealInfo;
  warehouse: WarehouseInfo;
  /** Called when the entire flow completes */
  onComplete: (result: {
    tourDate: string;
    tourTime: string;
    addressRevealed: boolean;
  }) => void;
}

/* ------------------------------------------------------------------ */
/*  Step indicator                                                     */
/* ------------------------------------------------------------------ */
function StepIndicator({
  currentStep,
  totalSteps,
}: {
  currentStep: number;
  totalSteps: number;
}) {
  return (
    <div className="flex items-center gap-2 px-6 py-3 border-b border-slate-700/60">
      {Array.from({ length: totalSteps }, (_, i) => {
        const step = i + 1;
        const isActive = step === currentStep;
        const isComplete = step < currentStep;
        return (
          <div key={step} className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                isComplete
                  ? "bg-emerald-500 text-white"
                  : isActive
                  ? "bg-blue-600 text-white ring-2 ring-blue-400/40"
                  : "bg-slate-700 text-slate-400"
              }`}
            >
              {isComplete ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                step
              )}
            </div>
            {step < totalSteps && (
              <div
                className={`w-8 h-0.5 ${
                  isComplete ? "bg-emerald-500" : "bg-slate-700"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 1: Contact Confirmed                                          */
/* ------------------------------------------------------------------ */
function StepContactConfirmed({ onNext }: { onNext: () => void }) {
  useEffect(() => {
    // Auto-advance after a brief confirmation display
    const timer = setTimeout(onNext, 1200);
    return () => clearTimeout(timer);
  }, [onNext]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="px-6 py-10 text-center"
    >
      <div className="w-16 h-16 rounded-full bg-emerald-500/15 flex items-center justify-center mx-auto mb-4">
        <CheckCircle2 className="w-8 h-8 text-emerald-400" />
      </div>
      <h3 className="text-lg font-bold text-white mb-1">Contact Confirmed</h3>
      <p className="text-sm text-slate-400">
        Your contact information is on file. Proceeding to guarantee...
      </p>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 2: Sign Guarantee                                             */
/* ------------------------------------------------------------------ */
function StepSignGuarantee({
  dealId,
  onSigned,
  onError,
}: {
  dealId: string;
  onSigned: (warehouse: WarehouseInfo) => void;
  onError: (msg: string) => void;
}) {
  const [accepted, setAccepted] = useState(false);
  const [signing, setSigning] = useState(false);

  async function handleSign() {
    if (!accepted) return;
    setSigning(true);
    try {
      const result = await api.signGuarantee(dealId);
      // The API returns the deal + warehouse with full address
      onSigned(result.warehouse || {});
    } catch (err: any) {
      onError(err.message || "Failed to sign guarantee");
    } finally {
      setSigning(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="px-6 py-6 space-y-5"
    >
      <div className="text-center mb-2">
        <div className="w-14 h-14 rounded-full bg-blue-500/15 flex items-center justify-center mx-auto mb-3">
          <Lock className="w-7 h-7 text-blue-400" />
        </div>
        <h3 className="text-lg font-bold text-white">
          Sign WEx Occupancy Guarantee
        </h3>
        <p className="text-sm text-slate-400 mt-1">
          The property address will be revealed after you sign.
        </p>
      </div>

      <AgreementCheckbox
        type="occupancy_guarantee"
        onAccept={setAccepted}
        accepted={accepted}
      />

      <button
        onClick={handleSign}
        disabled={!accepted || signing}
        className="w-full bg-blue-600 text-white py-3.5 rounded-xl font-semibold hover:bg-blue-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {signing ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Signing...
          </>
        ) : (
          <>
            <Unlock className="w-5 h-5" />
            Sign & Reveal Address
          </>
        )}
      </button>

      <div className="flex items-center justify-center gap-1.5">
        <Shield className="w-3.5 h-3.5 text-emerald-400" />
        <p className="text-xs text-slate-500">
          Anti-circumvention protection for both parties
        </p>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 3: Address Revealed + Schedule Tour                           */
/* ------------------------------------------------------------------ */
function StepScheduleTour({
  warehouse,
  deal,
  onScheduled,
  onError,
}: {
  warehouse: WarehouseInfo;
  deal: DealInfo;
  onScheduled: (date: string, time: string) => void;
  onError: (msg: string) => void;
}) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [notes, setNotes] = useState("");
  const [scheduling, setScheduling] = useState(false);

  // Build a minimum date (tomorrow)
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const minDate = tomorrow.toISOString().split("T")[0];

  async function handleSchedule() {
    if (!date || !time) return;
    setScheduling(true);
    try {
      await api.scheduleTour(deal.id, {
        preferred_date: date,
        preferred_time: time,
        notes: notes || undefined,
      });
      onScheduled(date, time);
    } catch (err: any) {
      onError(err.message || "Failed to schedule tour");
    } finally {
      setScheduling(false);
    }
  }

  const streetViewUrl = warehouse.address
    ? api.streetViewUrl(warehouse.address)
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="px-6 py-6 space-y-5"
    >
      {/* Address Revealed Banner */}
      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center shrink-0">
            <MapPin className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1">
              Address Revealed
            </p>
            <p className="text-white font-bold text-lg leading-tight">
              {warehouse.address || "Address loading..."}
            </p>
            <p className="text-sm text-slate-400 mt-0.5">
              {warehouse.city}, {warehouse.state}{" "}
              {warehouse.zip && warehouse.zip}
            </p>
          </div>
        </div>
      </div>

      {/* Satellite / Street View Image */}
      <div className="rounded-xl overflow-hidden border border-slate-700/60 bg-slate-800 h-48">
        {streetViewUrl ? (
          <img
            src={streetViewUrl}
            alt={warehouse.address || "Property view"}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
            <Building2 className="w-10 h-10 text-slate-600" />
            <span className="text-xs text-slate-500">
              Property image loading...
            </span>
          </div>
        )}
      </div>

      {/* Property Quick Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-slate-800/60 rounded-lg p-3 text-center border border-slate-700/40">
          <p className="text-xs text-slate-500 mb-1">Size</p>
          <p className="text-sm font-bold text-white">
            {warehouse.building_size_sqft
              ? `${warehouse.building_size_sqft.toLocaleString()} sqft`
              : "--"}
          </p>
        </div>
        <div className="bg-slate-800/60 rounded-lg p-3 text-center border border-slate-700/40">
          <p className="text-xs text-slate-500 mb-1">Rate</p>
          <p className="text-sm font-bold text-white">
            ${deal.rate_per_sqft.toFixed(2)}/sqft
          </p>
        </div>
        <div className="bg-slate-800/60 rounded-lg p-3 text-center border border-slate-700/40">
          <p className="text-xs text-slate-500 mb-1">Monthly</p>
          <p className="text-sm font-bold text-emerald-400">
            $
            {deal.monthly_payment.toLocaleString(undefined, {
              maximumFractionDigits: 0,
            })}
          </p>
        </div>
      </div>

      {/* Date/Time Picker */}
      <div>
        <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Calendar className="w-4 h-4 text-blue-400" />
          Pick Your Tour Time
        </h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Date</label>
            <input
              type="date"
              min={minDate}
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Time</label>
            <select
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">Select time</option>
              <option value="09:00">9:00 AM</option>
              <option value="09:30">9:30 AM</option>
              <option value="10:00">10:00 AM</option>
              <option value="10:30">10:30 AM</option>
              <option value="11:00">11:00 AM</option>
              <option value="11:30">11:30 AM</option>
              <option value="12:00">12:00 PM</option>
              <option value="12:30">12:30 PM</option>
              <option value="13:00">1:00 PM</option>
              <option value="13:30">1:30 PM</option>
              <option value="14:00">2:00 PM</option>
              <option value="14:30">2:30 PM</option>
              <option value="15:00">3:00 PM</option>
              <option value="15:30">3:30 PM</option>
              <option value="16:00">4:00 PM</option>
              <option value="16:30">4:30 PM</option>
            </select>
          </div>
        </div>

        <div className="mt-3">
          <label className="block text-xs text-slate-400 mb-1.5">
            Notes (optional)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Any special requests or questions for the tour..."
            rows={2}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          />
        </div>
      </div>

      <button
        onClick={handleSchedule}
        disabled={!date || !time || scheduling}
        className="w-full bg-blue-600 text-white py-3.5 rounded-xl font-semibold hover:bg-blue-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {scheduling ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Scheduling...
          </>
        ) : (
          <>
            <Calendar className="w-5 h-5" />
            Schedule Tour
          </>
        )}
      </button>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 4: Confirmation                                               */
/* ------------------------------------------------------------------ */
function StepConfirmation({
  warehouse,
  tourDate,
  tourTime,
  onDone,
}: {
  warehouse: WarehouseInfo;
  tourDate: string;
  tourTime: string;
  onDone: () => void;
}) {
  // Format date nicely
  const dateObj = new Date(tourDate + "T00:00:00");
  const formattedDate = dateObj.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  // Format time nicely
  const [hours, minutes] = tourTime.split(":");
  const h = parseInt(hours);
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h > 12 ? h - 12 : h === 0 ? 12 : h;
  const formattedTime = `${h12}:${minutes} ${ampm}`;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="px-6 py-8 text-center space-y-5"
    >
      <div className="w-20 h-20 rounded-full bg-emerald-500/15 flex items-center justify-center mx-auto">
        <CheckCircle2 className="w-10 h-10 text-emerald-400" />
      </div>

      <div>
        <h3 className="text-xl font-bold text-white mb-1">Tour Scheduled!</h3>
        <p className="text-sm text-slate-400">
          The supplier will confirm within 12 hours.
        </p>
      </div>

      {/* Tour Details Summary */}
      <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-left space-y-3">
        <div className="flex items-start gap-3">
          <MapPin className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Location
            </p>
            <p className="text-sm text-white font-medium">
              {warehouse.address || "Address on file"}
            </p>
            <p className="text-xs text-slate-400">
              {warehouse.city}, {warehouse.state}
            </p>
          </div>
        </div>

        <div className="h-px bg-slate-700/50" />

        <div className="flex items-start gap-3">
          <Calendar className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Date
            </p>
            <p className="text-sm text-white font-medium">{formattedDate}</p>
          </div>
        </div>

        <div className="h-px bg-slate-700/50" />

        <div className="flex items-start gap-3">
          <Clock className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Time
            </p>
            <p className="text-sm text-white font-medium">{formattedTime}</p>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <button
          onClick={onDone}
          className="w-full bg-blue-600 text-white py-3 rounded-xl font-semibold hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
        >
          View My Deals
          <ChevronRight className="w-4 h-4" />
        </button>

        <div className="flex items-center justify-center gap-1.5">
          <Shield className="w-3.5 h-3.5 text-emerald-400" />
          <p className="text-xs text-slate-500">
            WEx Occupancy Guarantee active
          </p>
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main TourBookingFlow Component                                     */
/* ------------------------------------------------------------------ */
export default function TourBookingFlow({
  open,
  onClose,
  deal,
  warehouse: initialWarehouse,
  onComplete,
}: TourBookingFlowProps) {
  // Determine initial step based on deal state
  const getInitialStep = () => {
    if (deal.guarantee_signed_at) return 3; // Already signed, skip to schedule
    return 1; // Start from contact confirmation
  };

  const [step, setStep] = useState(getInitialStep);
  const [warehouse, setWarehouse] = useState<WarehouseInfo>(initialWarehouse);
  const [tourDate, setTourDate] = useState("");
  const [tourTime, setTourTime] = useState("");
  const [error, setError] = useState<string | null>(null);
  const totalSteps = 4;

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setStep(getInitialStep());
      setWarehouse(initialWarehouse);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, deal.id]);

  function handleGuaranteeSigned(revealedWarehouse: WarehouseInfo) {
    setWarehouse({ ...warehouse, ...revealedWarehouse });
    setStep(3);
  }

  function handleTourScheduled(date: string, time: string) {
    setTourDate(date);
    setTourTime(time);
    setStep(4);
  }

  function handleDone() {
    onComplete({
      tourDate,
      tourTime,
      addressRevealed: true,
    });
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="tour-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            key="tour-modal"
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 350 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full max-w-lg bg-slate-900 rounded-2xl shadow-2xl border border-slate-700 overflow-hidden max-h-[90vh] flex flex-col">
              {/* Header */}
              <div className="px-6 pt-5 pb-0 flex items-start justify-between shrink-0">
                <div>
                  <h2 className="text-lg font-bold text-white">
                    Schedule Your Tour
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Step {step} of {totalSteps}
                  </p>
                </div>
                <button
                  onClick={onClose}
                  className="text-slate-500 hover:text-slate-300 transition-colors p-1 -mr-1 -mt-1"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Step Indicators */}
              <StepIndicator currentStep={step} totalSteps={totalSteps} />

              {/* Error Banner */}
              {error && (
                <div className="mx-6 mt-4 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                  <p className="text-sm text-red-300">{error}</p>
                </div>
              )}

              {/* Step Content (scrollable) */}
              <div className="flex-1 overflow-y-auto">
                <AnimatePresence mode="wait">
                  {step === 1 && (
                    <StepContactConfirmed
                      key="step1"
                      onNext={() => setStep(2)}
                    />
                  )}
                  {step === 2 && (
                    <StepSignGuarantee
                      key="step2"
                      dealId={deal.id}
                      onSigned={handleGuaranteeSigned}
                      onError={setError}
                    />
                  )}
                  {step === 3 && (
                    <StepScheduleTour
                      key="step3"
                      warehouse={warehouse}
                      deal={deal}
                      onScheduled={handleTourScheduled}
                      onError={setError}
                    />
                  )}
                  {step === 4 && (
                    <StepConfirmation
                      key="step4"
                      warehouse={warehouse}
                      tourDate={tourDate}
                      tourTime={tourTime}
                      onDone={handleDone}
                    />
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
