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
  Eye,
  EyeOff,
} from "lucide-react";
import AgreementCheckbox from "@/components/ui/AgreementCheckbox";
import HoldCountdown from "@/components/ui/HoldCountdown";
import { api, storeAuthToken } from "@/lib/api";

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
  /** Flow type: "reserve_tour" (4-step) or "book_instantly" (3-step) */
  flowType?: "reserve_tour" | "book_instantly";
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
/*  Pricing Summary Bar                                                */
/* ------------------------------------------------------------------ */
function PricingSummaryBar({ deal, holdExpiresAt }: { deal: DealInfo; holdExpiresAt?: string }) {
  return (
    <div className="px-6 py-3 bg-slate-800/50 border-b border-slate-700/60 flex items-center justify-between text-sm">
      <div className="flex items-center gap-2 text-slate-300">
        <span>{deal.sqft_allocated?.toLocaleString()} sqft</span>
        <span className="text-slate-600">&middot;</span>
        <span>${deal.monthly_payment?.toLocaleString()}/mo</span>
        <span className="text-slate-600">&middot;</span>
        <span>{deal.term_months} months</span>
        <span className="text-slate-600">&middot;</span>
        <span>${(deal.monthly_payment * deal.term_months)?.toLocaleString()}</span>
      </div>
      {holdExpiresAt && <HoldCountdown holdExpiresAt={holdExpiresAt} format="held_for" />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 1: Account Auth (Register / Login)                            */
/* ------------------------------------------------------------------ */
function StepAccountAuth({
  engagementId,
  onSuccess,
  onError,
}: {
  engagementId: string;
  onSuccess: () => void;
  onError: (msg: string) => void;
}) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  function validate(): boolean {
    setFieldError(null);
    if (mode === "register") {
      if (!firstName.trim()) { setFieldError("First name is required."); return false; }
      if (!lastName.trim()) { setFieldError("Last name is required."); return false; }
    }
    if (!email) { setFieldError("Email is required."); return false; }
    if (!password) { setFieldError("Password is required."); return false; }
    if (mode === "register") {
      if (password.length < 8) { setFieldError("Password must be at least 8 characters."); return false; }
      if (password !== confirmPassword) { setFieldError("Passwords do not match."); return false; }
    }
    return true;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setSubmitting(true);
    setFieldError(null);
    try {
      if (mode === "register") {
        const res = await api.register({
          email,
          password,
          name: `${firstName.trim()} ${lastName.trim()}`,
          role: "buyer",
          company: company.trim() || undefined,
          phone: phone || undefined,
          engagement_id: engagementId,
        });
        storeAuthToken(res.access_token || res.token);
      } else {
        const res = await api.login({ email, password });
        storeAuthToken(res.access_token || res.token);
        await api.linkBuyer(engagementId);
      }
      onSuccess();
    } catch (err: any) {
      const msg = err.message || "Something went wrong";
      if (msg.includes("409") || msg.toLowerCase().includes("already exists")) {
        setFieldError("An account with this email already exists. Sign in instead.");
      } else {
        onError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="px-6 py-6 space-y-4"
    >
      <div className="text-center mb-2">
        <h3 className="text-lg font-bold text-white">
          {mode === "register" ? "Create Your Account" : "Sign In"}
        </h3>
        <p className="text-sm text-slate-400 mt-1">
          {mode === "register"
            ? "Create an account to continue with your tour booking."
            : "Sign in to continue with your tour booking."}
        </p>
      </div>

      {fieldError && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
          <p className="text-sm text-red-300">{fieldError}</p>
        </div>
      )}

      <div className="space-y-3">
        {mode === "register" && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">First Name</label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="Jane"
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Last Name</label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Smith"
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1.5">
                Company <span className="text-slate-500">(optional)</span>
              </label>
              <input
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Acme Logistics"
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </>
        )}

        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Password</label>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "Min 8 characters" : "Your password"}
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-300"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {mode === "register" && (
          <>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">
                Confirm Password
              </label>
              <input
                type={showPassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter password"
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1.5">
                Phone <span className="text-slate-500">(optional)</span>
              </label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="(555) 555-0100"
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-slate-500 mt-1">
                For tour reminders and updates
              </p>
            </div>
          </>
        )}
      </div>

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="w-full bg-blue-600 text-white py-3.5 rounded-xl font-semibold hover:bg-blue-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {submitting ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            {mode === "register" ? "Creating Account..." : "Signing In..."}
          </>
        ) : mode === "register" ? (
          "Create Account & Continue"
        ) : (
          "Sign In & Continue"
        )}
      </button>

      <p className="text-center text-sm text-slate-400">
        {mode === "register" ? (
          <>
            Already have an account?{" "}
            <button
              onClick={() => { setMode("login"); setFieldError(null); }}
              className="text-blue-400 hover:text-blue-300 font-medium"
            >
              Sign in
            </button>
          </>
        ) : (
          <>
            New to WEx?{" "}
            <button
              onClick={() => { setMode("register"); setFieldError(null); }}
              className="text-blue-400 hover:text-blue-300 font-medium"
            >
              Create an account
            </button>
          </>
        )}
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
  flowType = "reserve_tour",
}: {
  dealId: string;
  onSigned: (warehouse: WarehouseInfo, holdExpiresAt?: string) => void;
  onError: (msg: string) => void;
  flowType?: "reserve_tour" | "book_instantly";
}) {
  const [accepted, setAccepted] = useState(false);
  const [signing, setSigning] = useState(false);

  async function handleSign() {
    if (!accepted) return;
    setSigning(true);
    try {
      const guaranteeRes = await api.signGuarantee(dealId);
      // New engagement endpoint returns flat engagement data
      // Fetch property details separately after guarantee is signed
      let warehouseData: any = {};
      try {
        warehouseData = await api.getEngagementProperty(dealId);
      } catch {
        // Property fetch failed — continue with what we have
      }

      // For instant book flow, also call the instant book API
      if (flowType === "book_instantly") {
        try {
          await api.confirmInstantBook(dealId);
        } catch {
          // Instant book API failed — continue to confirmation anyway
        }
      }

      onSigned(warehouseData, guaranteeRes?.hold_expires_at);
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
          <Shield className="w-7 h-7 text-blue-400" />
        </div>
        <h3 className="text-lg font-bold text-white">
          Your space is protected by WEx.
        </h3>
      </div>

      <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-4 space-y-2.5">
        <div className="flex items-start gap-2.5">
          <span className="text-emerald-400 shrink-0">&#10003;</span>
          <p className="text-sm text-slate-300">This space and rate are held for 72 hours</p>
        </div>
        <div className="flex items-start gap-2.5">
          <span className="text-emerald-400 shrink-0">&#10003;</span>
          <p className="text-sm text-slate-300">Your rate is locked — no renegotiation after the tour</p>
        </div>
        <div className="flex items-start gap-2.5">
          <span className="text-emerald-400 shrink-0">&#10003;</span>
          <p className="text-sm text-slate-300">Payment goes through WEx, never directly to the owner</p>
        </div>
        <div className="flex items-start gap-2.5">
          <span className="text-emerald-400 shrink-0">&#10003;</span>
          <p className="text-sm text-slate-300">WEx handles disputes if the space doesn&#39;t match what&#39;s described</p>
        </div>
        <div className="flex items-start gap-2.5">
          <span className="text-emerald-400 shrink-0">&#10003;</span>
          <p className="text-sm text-slate-300">Your contact info stays private until the tour is confirmed</p>
        </div>
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
            {flowType === "book_instantly" ? "Booking..." : "Confirming..."}
          </>
        ) : (
          <>
            {flowType === "book_instantly" ? "Confirm & Book This Space" : "Confirm & See the Space"}
            <ChevronRight className="w-5 h-5" />
          </>
        )}
      </button>

      <div className="flex items-center justify-center gap-1.5">
        <Shield className="w-3.5 h-3.5 text-emerald-400" />
        <p className="text-xs text-slate-500">
          WEx Occupancy Guarantee active
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

  // Build a minimum date (24 hours from now)
  const minDateTime = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const minDate = minDateTime.toISOString().split("T")[0];

  // Generate time options: 8:00 AM through 5:00 PM, 30-minute increments
  const timeOptions: { value: string; label: string }[] = [];
  for (let h = 8; h <= 17; h++) {
    for (const m of [0, 30]) {
      if (h === 17 && m === 30) break; // Stop at 5:00 PM
      const value = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      const h12 = h > 12 ? h - 12 : h === 0 ? 12 : h;
      const ampm = h >= 12 ? "PM" : "AM";
      const label = `${h12}:${String(m).padStart(2, "0")} ${ampm}`;
      timeOptions.push({ value, label });
    }
  }

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

  const propertyImageUrl = warehouse.primary_image_url;
  const streetViewUrl = warehouse.address
    ? api.streetViewUrl(warehouse.address)
    : null;
  const mapsUrl = warehouse.address
    ? `https://maps.google.com/?q=${encodeURIComponent(warehouse.address)}`
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="px-6 py-6 space-y-5"
    >
      {/* Your Reserved Space Banner */}
      <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center shrink-0">
            <MapPin className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1">
              YOUR RESERVED SPACE
            </p>
            <p className="text-white font-bold text-lg leading-tight">
              {warehouse.address || "Address loading..."}
            </p>
            <p className="text-sm text-slate-400 mt-0.5">
              {warehouse.city}, {warehouse.state}{" "}
              {warehouse.zip && warehouse.zip}
            </p>
            {mapsUrl && (
              <a
                href={mapsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mt-1.5"
              >
                <MapPin className="w-3 h-3" />
                Open in Maps
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Property Photo / Street View */}
      <div className="rounded-xl overflow-hidden border border-slate-700/60 bg-slate-800 h-48">
        {propertyImageUrl ? (
          <img
            src={propertyImageUrl}
            alt={warehouse.address || "Property photo"}
            className="w-full h-full object-cover"
          />
        ) : streetViewUrl ? (
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
          <p className="text-xs text-slate-500 mb-1">Available</p>
          <p className="text-sm font-bold text-white">
            {deal.sqft_allocated
              ? `${deal.sqft_allocated.toLocaleString()} sqft`
              : warehouse.building_size_sqft
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
              {timeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-3">
          <label className="block text-xs text-slate-400 mb-1.5">
            Notes <span className="text-slate-500">(optional)</span>
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Any special requests or access instructions"
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
            Schedule My Tour
            <ChevronRight className="w-5 h-5" />
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
  holdExpiresAt,
  onDone,
}: {
  warehouse: WarehouseInfo;
  tourDate: string;
  tourTime: string;
  holdExpiresAt?: string;
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

  // Format hold expiry
  const formattedHoldExpiry = holdExpiresAt
    ? new Date(holdExpiresAt).toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

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
        <h3 className="text-xl font-bold text-white mb-1">Space Reserved!</h3>
        <p className="text-sm text-slate-400">
          Tour request sent. Supplier confirms within 12 hours.
        </p>
      </div>

      {/* Tour Details Summary */}
      <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-left space-y-3">
        <div className="flex items-start gap-3">
          <MapPin className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Address
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

        {formattedHoldExpiry && (
          <>
            <div className="h-px bg-slate-700/50" />
            <div className="flex items-start gap-3">
              <Lock className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">
                  Hold Expires
                </p>
                <p className="text-sm text-white font-medium">{formattedHoldExpiry}</p>
              </div>
            </div>
          </>
        )}
      </div>

      <p className="text-xs text-slate-400">
        We&apos;ll notify you by email (and SMS if you provided your number) when confirmed.
      </p>

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
            <span role="img" aria-label="shield">&#x1F6E1;</span> WEx Occupancy Guarantee active
          </p>
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 3 (Book Instantly): Confirmation — Space Booked!              */
/* ------------------------------------------------------------------ */
function StepBookConfirmation({
  deal,
  onDone,
}: {
  deal: DealInfo;
  onDone: () => void;
}) {
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
        <h3 className="text-xl font-bold text-white mb-1">Space Booked!</h3>
        <p className="text-sm text-slate-400">
          Agreement is being prepared.
        </p>
      </div>

      {/* Agreement Info */}
      <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-left space-y-3">
        <div className="flex items-start gap-3">
          <Lock className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Status
            </p>
            <p className="text-sm text-white font-medium">Instant Book Confirmed</p>
          </div>
        </div>

        <div className="h-px bg-slate-700/50" />

        <div className="flex items-start gap-3">
          <Building2 className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Space
            </p>
            <p className="text-sm text-white font-medium">
              {deal.sqft_allocated?.toLocaleString()} sqft &middot; ${deal.monthly_payment?.toLocaleString()}/mo
            </p>
          </div>
        </div>

        <div className="h-px bg-slate-700/50" />

        <div className="flex items-start gap-3">
          <Calendar className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Term
            </p>
            <p className="text-sm text-white font-medium">{deal.term_months} months</p>
          </div>
        </div>
      </div>

      <p className="text-sm text-slate-400">
        Your agreement will be sent to your email shortly.
      </p>

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
  flowType = "reserve_tour",
  onComplete,
}: TourBookingFlowProps) {
  const isInstantBook = flowType === "book_instantly";
  const totalSteps = isInstantBook ? 3 : 4;

  // Determine initial step based on deal state
  const getInitialStep = () => {
    if (deal.guarantee_signed_at) {
      return isInstantBook ? 3 : 3; // Skip to schedule (reserve) or confirmation (instant)
    }
    return 1; // Start from contact confirmation
  };

  const [step, setStep] = useState(getInitialStep);
  const [warehouse, setWarehouse] = useState<WarehouseInfo>(initialWarehouse);
  const [tourDate, setTourDate] = useState("");
  const [tourTime, setTourTime] = useState("");
  const [holdExpiresAt, setHoldExpiresAt] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setStep(getInitialStep());
      setWarehouse(initialWarehouse);
      setHoldExpiresAt(undefined);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, deal.id]);

  function handleGuaranteeSigned(revealedWarehouse: WarehouseInfo, holdExpiry?: string) {
    setWarehouse({ ...warehouse, ...revealedWarehouse });
    if (holdExpiry) setHoldExpiresAt(holdExpiry);
    if (isInstantBook) {
      // Skip tour scheduling, go straight to confirmation (step 3)
      setStep(3);
    } else {
      setStep(3);
    }
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
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <Lock className="w-5 h-5 text-blue-400" />
                    {isInstantBook ? "Book Instantly" : "Reserve & Tour"}
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

              {/* Pricing Summary Bar */}
              <PricingSummaryBar deal={deal} holdExpiresAt={step >= 3 ? holdExpiresAt : undefined} />

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
                    <StepAccountAuth
                      key="step1"
                      engagementId={deal.id}
                      onSuccess={() => setStep(2)}
                      onError={setError}
                    />
                  )}
                  {step === 2 && (
                    <StepSignGuarantee
                      key="step2"
                      dealId={deal.id}
                      onSigned={handleGuaranteeSigned}
                      onError={setError}
                      flowType={flowType}
                    />
                  )}
                  {/* Reserve & Tour: Step 3 = Schedule Tour, Step 4 = Confirmation */}
                  {!isInstantBook && step === 3 && (
                    <StepScheduleTour
                      key="step3"
                      warehouse={warehouse}
                      deal={deal}
                      onScheduled={handleTourScheduled}
                      onError={setError}
                    />
                  )}
                  {!isInstantBook && step === 4 && (
                    <StepConfirmation
                      key="step4"
                      warehouse={warehouse}
                      tourDate={tourDate}
                      tourTime={tourTime}
                      holdExpiresAt={holdExpiresAt}
                      onDone={handleDone}
                    />
                  )}
                  {/* Book Instantly: Step 3 = Book Confirmation (no tour scheduling) */}
                  {isInstantBook && step === 3 && (
                    <StepBookConfirmation
                      key="step3-book"
                      deal={deal}
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
