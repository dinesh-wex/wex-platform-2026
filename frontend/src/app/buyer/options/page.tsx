"use client";

import { useEffect, useState, useRef, useCallback, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Check,
  Info,
  ArrowLeft,
  ArrowUpRight,
  ShieldCheck,
  Sparkles,
  MapPin,
  Truck,
  Loader2,
  AlertCircle,
  Building2,
  Zap,
  CalendarCheck,
  Star,
  Mail,
  Bell,
  Clock,
  Search,
  Shield,
  CheckCircle2,
  Droplets,
  Thermometer,
  Car,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";
import ContactCaptureModal from "@/components/ui/ContactCaptureModal";
import TourBookingFlow from "@/components/ui/TourBookingFlow";

// Alias for optional icon
const DoorOpen = ArrowRight;

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface FeaturePill {
  label: string;
  icon: string; // "height" | "dock" | "sprinkler" | "power" | "climate" | "office" | "access" | "parking" | "drivein"
}

interface MatchOption {
  match_id: string;
  warehouse_id: string;
  tier: 1 | 2;
  match_score: number;
  match_explanation: string;

  location: {
    city: string;
    state: string;
    neighborhood?: string;
  };

  property: {
    type: string;
    building_class?: string;
    available_sqft: number;
    building_total_sqft?: number;
  };

  features: FeaturePill[];

  pricing: {
    rate_sqft: number;
    monthly_total: number;
    term_months: number;
    term_total: number;
  };

  market_context?: {
    area_name: string;
    rate_low: number;
    rate_high: number;
  };

  primary_image?: {
    url: string;
    type: string;
  } | null;

  instant_book_eligible?: boolean;
  description?: string;
  images?: { url: string; type: string }[];
  has_virtual_tour?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount);
}

function formatNumber(num: number): string {
  return new Intl.NumberFormat("en-US").format(num);
}

/* ------------------------------------------------------------------ */
/*  Icon mapping for feature pills                                     */
/* ------------------------------------------------------------------ */
function getFeatureIcon(iconName: string) {
  switch (iconName) {
    case "height":
      return ArrowUpRight;
    case "dock":
      return Truck;
    case "sprinkler":
      return Droplets;
    case "power":
      return Zap;
    case "climate":
      return Thermometer;
    case "office":
      return Building2;
    case "access":
      return Clock;
    case "parking":
      return Car;
    case "drivein":
      return DoorOpen;
    default:
      return Check;
  }
}

/* ------------------------------------------------------------------ */
/*  Smart Media Gallery — Bento (desktop) / Swipe (mobile)             */
/* ------------------------------------------------------------------ */
function SmartMediaGallery({
  images,
  hasVirtualTour,
  alt,
}: {
  images: { url: string; type: string }[];
  hasVirtualTour: boolean;
  alt: string;
}) {
  const [swipeIndex, setSwipeIndex] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || el.clientWidth === 0) return;
    const idx = Math.round(el.scrollLeft / el.clientWidth);
    setSwipeIndex(idx);
  }, []);
  const hero = images[0] || null;
  const insets = images.slice(1, 3);
  const extraCount = Math.max(0, images.length - 3);

  // --- EMPTY STATE ---
  if (images.length === 0) {
    return (
      <div className="relative w-full aspect-video bg-gradient-to-br from-slate-100 to-slate-200 flex flex-col items-center justify-center gap-3">
        <Building2 className="w-16 h-16 text-slate-300" />
        <span className="text-sm text-slate-400">Satellite view pending</span>
      </div>
    );
  }

  // --- SINGLE IMAGE ---
  if (images.length === 1) {
    return (
      <div className="relative w-full aspect-video bg-slate-100 overflow-hidden">
        <img src={hero!.url} alt={alt} className="absolute inset-0 w-full h-full object-cover" />
        {hasVirtualTour && <VirtualTourButton />}
      </div>
    );
  }

  // --- DESKTOP BENTO (hidden on mobile) ---
  // --- MOBILE SWIPE  (hidden on desktop) ---
  return (
    <>
      {/* Desktop Bento: 70 / 30 split */}
      <div className="hidden md:grid grid-cols-[7fr_3fr] gap-1 relative overflow-hidden rounded-t-2xl" style={{ height: 340 }}>
        {/* Hero */}
        <div className="relative overflow-hidden">
          <img src={hero!.url} alt={alt} className="absolute inset-0 w-full h-full object-cover" />
          {hasVirtualTour && <VirtualTourButton />}
        </div>
        {/* Inset stack */}
        <div className="flex flex-col gap-1">
          {insets.map((img, i) => (
            <div key={i} className="relative flex-1 overflow-hidden">
              <img src={img.url} alt={`${alt} ${i + 2}`} className="absolute inset-0 w-full h-full object-cover" />
              {/* "+N more" overlay on last inset */}
              {i === insets.length - 1 && extraCount > 0 && (
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                  <span className="text-white font-bold text-lg">+{extraCount} more</span>
                </div>
              )}
            </div>
          ))}
          {/* If only one inset, fill remaining space with placeholder */}
          {insets.length === 1 && (
            <div className="relative flex-1 overflow-hidden bg-slate-200 flex items-center justify-center">
              <Building2 className="w-8 h-8 text-slate-300" />
            </div>
          )}
        </div>
      </div>

      {/* Mobile Swipe */}
      <div className="md:hidden relative">
        <div ref={scrollRef} onScroll={handleScroll} className="overflow-x-auto snap-x snap-mandatory flex scrollbar-hide" style={{ scrollbarWidth: "none" }}>
          {images.map((img, i) => (
            <div key={i} className="snap-center shrink-0 w-full aspect-video relative bg-slate-100">
              <img src={img.url} alt={`${alt} ${i + 1}`} className="absolute inset-0 w-full h-full object-cover" />
              {i === 0 && hasVirtualTour && <VirtualTourButton />}
            </div>
          ))}
        </div>
        {/* Pagination dots */}
        {images.length > 1 && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
            {images.map((_, i) => (
              <div key={i} className={`w-2 h-2 rounded-full transition-colors ${i === swipeIndex ? "bg-white" : "bg-white/50"}`} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

/* Frosted-glass virtual tour play button — only rendered when has_virtual_tour */
function VirtualTourButton() {
  return (
    <div className="absolute inset-0 flex items-center justify-center z-10">
      <button className="bg-white/20 backdrop-blur-md border border-white/30 text-white font-semibold px-5 py-3 rounded-xl flex items-center gap-2.5 shadow-2xl hover:bg-white/30 transition-all cursor-pointer group">
        <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center group-hover:scale-110 transition-transform">
          <div className="w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-l-[10px] border-l-slate-900 ml-0.5" />
        </div>
        <span className="text-sm tracking-wide">View Virtual Tour</span>
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tier 1 Card — Editorial Deal Card                                  */
/* ------------------------------------------------------------------ */
function Tier1Card({
  option,
  index,
  onAccept,
  onAsk,
  accepting,
}: {
  option: MatchOption;
  index: number;
  onAccept: (matchId: string) => void;
  onAsk: (matchId: string) => void;
  accepting: string | null;
}) {
  // Derive display strings with fallbacks
  const neighborhood =
    option.location.neighborhood ||
    (option.location.city
      ? `${option.location.city}, ${option.location.state}`
      : "Industrial Area");

  // City, State heading — fallback to neighborhood if city empty
  const cityState = option.location.city
    ? `${option.location.city}${option.location.state ? `, ${option.location.state}` : ""}`
    : neighborhood;

  const propertyMeta = [
    option.property.type,
    option.property.building_class &&
    (option.property.building_class === "A" ||
      option.property.building_class === "B")
      ? `Class ${option.property.building_class}`
      : null,
  ]
    .filter(Boolean)
    .join(" \u2022 ");

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.15, duration: 0.5, ease: "easeOut" }}
      className="w-full max-w-3xl mx-auto bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-xl transition-shadow duration-300"
    >
      {/* 1. SMART MEDIA GALLERY — Bento (desktop) / Swipe (mobile) */}
      <div className="relative">
        <SmartMediaGallery
          images={option.images || (option.primary_image?.url ? [option.primary_image] : [])}
          hasVirtualTour={option.has_virtual_tour || false}
          alt={cityState}
        />
        {/* Match Badge — top left, overlaid on gallery */}
        <div className="absolute top-4 left-4 bg-emerald-500 text-white font-bold px-3 py-1.5 rounded-md flex items-center gap-1.5 shadow-lg z-20">
          <Sparkles size={16} />
          {option.match_score}% Match
        </div>
      </div>

      <div className="p-6 md:p-8">
        {/* 2. IDENTITY & SIZE — 3-column grid, top-aligned */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start mb-8 border-b border-slate-100 pb-8">
          {/* Location — spans 2 columns */}
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 text-slate-500 text-sm font-bold uppercase tracking-widest mb-2">
              <MapPin size={16} /> {neighborhood}
            </div>
            {/* Anti-circumvention: NO STREET ADDRESS */}
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900 mb-2">
              {cityState}
            </h2>
            <p className="text-slate-500 font-medium">
              {propertyMeta}
            </p>
          </div>

          {/* Size Context Box — 1 column, top-aligned with text */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-right">
            <div className="text-2xl font-bold text-emerald-600">
              {formatNumber(option.property.available_sqft)} sqft
            </div>
            <div className="text-sm text-slate-500 font-medium">
              available space
            </div>
            {option.property.building_total_sqft &&
              option.property.building_total_sqft > option.property.available_sqft && (
              <div className="text-xs text-slate-400 mt-1 pt-1 border-t border-slate-200">
                in {formatNumber(option.property.building_total_sqft)} sqft building
              </div>
            )}
          </div>
        </div>

        {/* 3. FEATURE PILLS (Max 5) */}
        {option.features.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-8">
            {option.features.slice(0, 5).map((pill, idx) => {
              const PillIcon = getFeatureIcon(pill.icon);
              return (
                <span key={idx} className="bg-white border border-slate-200 text-slate-700 px-3 py-1.5 rounded-lg text-sm font-bold flex items-center gap-2">
                  <PillIcon size={14} className="text-emerald-500" />
                  {pill.label}
                </span>
              );
            })}
          </div>
        )}

        {/* 4. FINANCIALS ("The Ticket") */}
        <div className="bg-slate-50 rounded-2xl p-6 mb-8 border border-slate-100">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 md:divide-x md:divide-slate-200">
            <div className="md:pl-0">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Your Rate</p>
              <p className="text-xl font-bold text-slate-900">${option.pricing.rate_sqft.toFixed(2)}</p>
              <p className="text-xs text-slate-500">/sqft/month</p>
            </div>
            <div className="md:pl-6">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Monthly Cost</p>
              <p className="text-2xl font-bold text-emerald-600">{formatCurrency(option.pricing.monthly_total)}</p>
              <p className="text-xs text-slate-500">all-in pricing</p>
            </div>
            <div className="md:pl-6">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Term</p>
              <p className="text-xl font-bold text-slate-900">{option.pricing.term_months}</p>
              <p className="text-xs text-slate-500">months</p>
            </div>
            <div className="md:pl-6">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Total Value</p>
              <p className="text-xl font-bold text-slate-900">{formatCurrency(option.pricing.term_total)}</p>
              <p className="text-xs text-slate-500">over full term</p>
            </div>
          </div>

          {/* Market Context Banner */}
          {option.market_context && (
            <div className="mt-6 bg-blue-50/50 border border-blue-100 rounded-lg p-3 flex items-start gap-3">
              <Info size={16} className="text-blue-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-blue-900">
                Market rates in {option.market_context.area_name} typically run{" "}
                <span className="font-bold">
                  ${option.market_context.rate_low.toFixed(2)}&ndash;${option.market_context.rate_high.toFixed(2)}/sqft
                </span>{" "}
                for comparable space.
              </p>
            </div>
          )}
        </div>

        {/* 5. AI SYNTHESIS ("Why This Space") */}
        {option.match_explanation && (
          <div className="mb-8">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-widest mb-3 flex items-center gap-2">
              <Sparkles size={16} className="text-emerald-500" /> Why This Space
            </h3>
            <p className="text-slate-600 leading-relaxed text-lg">
              {option.match_explanation}
            </p>
          </div>
        )}

        {/* 6. ACTIONS */}
        <div className="flex flex-col md:flex-row gap-4 pt-6 border-t border-slate-100">
          <button
            onClick={() => onAccept(option.match_id)}
            disabled={accepting === option.match_id}
            className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-lg font-bold py-4 px-6 rounded-xl transition-all shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2 disabled:opacity-70"
          >
            {accepting === option.match_id ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <CalendarCheck className="w-5 h-5" />
                Accept &amp; Schedule Tour
              </>
            )}
          </button>

          <button
            onClick={() => onAsk(option.match_id)}
            className="flex-1 bg-white border-2 border-slate-200 hover:border-slate-900 text-slate-900 text-lg font-bold py-4 px-6 rounded-xl transition-all flex items-center justify-center gap-2"
          >
            Ask About This Space
          </button>
        </div>

        <div className="text-center mt-4 text-xs text-slate-400 font-medium flex items-center justify-center gap-1.5">
          <ShieldCheck size={14} /> All rates are all-in. Every deal includes WEx Occupancy Guarantee.
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tier 2 Card (muted, sourcing in progress)                          */
/* ------------------------------------------------------------------ */
function Tier2Card({
  option,
  index,
}: {
  option: MatchOption;
  index: number;
}) {
  const neighborhood =
    option.location.neighborhood ||
    `${option.location.city}, ${option.location.state}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 + index * 0.1, duration: 0.5 }}
      className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden"
    >
      <div className="flex flex-col sm:flex-row">
        {/* Image placeholder */}
        <div className="sm:w-1/3 h-40 sm:h-auto bg-gradient-to-br from-slate-100 to-slate-200 relative min-h-[160px] flex items-center justify-center">
          {option.primary_image?.url ? (
            <img
              src={option.primary_image.url}
              alt={neighborhood}
              className="w-full h-full object-cover"
            />
          ) : (
            <Building2 className="w-10 h-10 text-slate-400" />
          )}
          {/* Match badge */}
          <div className="absolute top-3 left-3">
            <div className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 text-slate-600 border border-gray-200">
              <Star className="w-3 h-3" />
              {option.match_score}% Match
            </div>
          </div>
        </div>

        {/* Info */}
        <div className="sm:w-2/3 p-5">
          <div className="flex items-center gap-1.5 text-slate-600 mb-2">
            <MapPin className="w-3.5 h-3.5" />
            <span className="text-sm">{neighborhood}</span>
          </div>

          <div className="flex items-center gap-2 mb-3">
            <div className="bg-gray-100 px-2.5 py-1 rounded-lg">
              <span className="text-xs font-medium text-slate-600">
                {formatNumber(option.property.available_sqft)} sqft
              </span>
            </div>
            {option.property.type && (
              <span className="text-xs text-slate-400">
                {option.property.type}
              </span>
            )}
          </div>

          {/* Feature pills (compact) */}
          {option.features.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {option.features.slice(0, 3).map((pill, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-slate-100 text-xs text-slate-500"
                >
                  <Check className="w-3 h-3 text-slate-300" />
                  {pill.label}
                </span>
              ))}
            </div>
          )}

          {/* Sourcing in progress */}
          <div className="flex items-center gap-2 mb-2">
            <div className="relative flex items-center justify-center w-4 h-4">
              <span className="absolute inline-flex h-full w-full rounded-full bg-blue-300/50 animate-ping" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
            </div>
            <span className="text-sm font-medium text-blue-600">
              Confirming availability and rate
            </span>
          </div>

          <p className="text-xs text-slate-500">
            This space is being verified by our team. You&apos;ll be notified
            when terms are available.
          </p>
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  No-Match Contact Form (inline, not modal)                           */
/* ------------------------------------------------------------------ */
function NoMatchContactCapture({
  onSubmit,
}: {
  onSubmit: (email: string, phone: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setSubmitting(true);
    try {
      await fetch("/api/buyer/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, phone }),
      });
    } catch {
      // Stubbed -- continue
    }
    localStorage.setItem(
      "wex_buyer_contact",
      JSON.stringify({ email, phone })
    );
    setSubmitting(false);
    setSubmitted(true);
    onSubmit(email, phone);
  }

  if (submitted) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-emerald-50 border border-emerald-200 rounded-2xl px-6 py-8 text-center"
      >
        <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto mb-3" />
        <h4 className="text-lg font-semibold text-slate-900 mb-1">
          You&apos;re all set
        </h4>
        <p className="text-sm text-slate-600">
          We&apos;ll send your matches to{" "}
          <strong className="text-slate-900">{email}</strong> as soon as
          they&apos;re ready.
        </p>
      </motion.div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="bg-white border border-gray-200 shadow-sm rounded-2xl p-6">
        <h4 className="text-base font-semibold text-slate-900 mb-1">
          Where should we send your matches?
        </h4>
        <p className="text-sm text-slate-500 mb-5">
          Enter your contact info and we&apos;ll notify you the moment options
          are ready.
        </p>

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full bg-white border border-gray-300 rounded-lg pl-10 pr-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
            </div>
          </div>
          <div className="flex-1">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="(555) 123-4567"
              className="w-full bg-white border border-gray-300 rounded-lg px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || !email}
            className="bg-emerald-600 text-white px-6 py-2.5 rounded-lg font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60 flex items-center justify-center gap-2 whitespace-nowrap"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Bell className="w-4 h-4" />
                Notify Me
              </>
            )}
          </button>
        </div>

        <div className="flex items-center gap-1.5 mt-3">
          <Shield className="w-3.5 h-3.5 text-emerald-600" />
          <p className="text-xs text-slate-500">
            No spam, ever. We&apos;ll only use this to send your matches.
          </p>
        </div>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Inner Component (uses useSearchParams)                             */
/* ------------------------------------------------------------------ */
function OptionsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const sessionToken = searchParams.get("session");
  const legacyNeedId = searchParams.get("need_id"); // backwards compat

  const [tier1, setTier1] = useState<MatchOption[]>([]);
  const [tier2, setTier2] = useState<MatchOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState<string | null>(null);

  // Contact capture modal state
  const [contactModalOpen, setContactModalOpen] = useState(false);
  const [pendingMatchId, setPendingMatchId] = useState<string | null>(null);
  const [contactCaptured, setContactCaptured] = useState(false);

  // Email list modal state
  const [emailListModalOpen, setEmailListModalOpen] = useState(false);

  // Tour booking flow state
  const [tourFlowOpen, setTourFlowOpen] = useState(false);
  const [tourFlowDeal, setTourFlowDeal] = useState<any>(null);
  const [tourFlowWarehouse, setTourFlowWarehouse] = useState<any>(null);

  // Check if contact is already saved
  useEffect(() => {
    const saved = localStorage.getItem("wex_buyer_contact");
    if (saved) setContactCaptured(true);
  }, []);

  useEffect(() => {
    if (sessionToken) {
      loadFromSession(sessionToken);
    } else if (legacyNeedId) {
      loadOptions(legacyNeedId);
    } else {
      setError("No search session found. Please start a search first.");
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionToken, legacyNeedId]);

  /* ---------------------------------------------------------------- */
  /*  Buyer data from localStorage                                     */
  /* ---------------------------------------------------------------- */
  function getBuyerNeed(): Record<string, string | null> {
    try {
      const stored = localStorage.getItem("wex_buyer_need");
      return stored ? JSON.parse(stored) : {};
    } catch {
      return {};
    }
  }

  function parseBuyerSqft(need: Record<string, string | null>): number {
    const raw = parseInt(need.sqft_raw || "0");
    if (raw > 0) return raw;
    const sizeMatch = (need.size_sqft || "").replace(/,/g, "").match(/(\d+)/);
    return sizeMatch ? parseInt(sizeMatch[1]) : 5000;
  }

  function parseBuyerRate(
    need: Record<string, string | null>,
    sqft: number
  ): number {
    const budget = need.budget || "";
    const perSqftMatch = budget.match(/\$([\d.]+)\/sqft/);
    if (perSqftMatch) return parseFloat(perSqftMatch[1]);
    const monthlyMatch = budget.replace(/,/g, "").match(/\$?([\d.]+)\/mo/);
    if (monthlyMatch && sqft > 0)
      return Math.round((parseFloat(monthlyMatch[1]) / sqft) * 100) / 100;
    return 1.1;
  }

  /* ---------------------------------------------------------------- */
  /*  Build feature pills from warehouse data                          */
  /*  localStorage shape: wh.clear_height, wh.dock_doors,             */
  /*  wh.sprinklered, wh.power_phase, wh.parking_spaces,              */
  /*  wh.drive_in_bays, wh.truth_core.has_office                      */
  /* ---------------------------------------------------------------- */
  function buildFeaturePills(wh: any): FeaturePill[] {
    const pills: FeaturePill[] = [];
    if (!wh) return pills;

    // Clear height — top-level field
    if (wh.clear_height) {
      pills.push({
        label: `${wh.clear_height}' Clear`,
        icon: "height",
      });
    }
    // Dock doors — top-level field
    if (wh.dock_doors) {
      pills.push({
        label: `${wh.dock_doors} Dock Doors`,
        icon: "dock",
      });
    }
    // Sprinkler — top-level boolean "sprinklered"
    if (wh.sprinklered) {
      pills.push({ label: "Sprinklered", icon: "sprinkler" });
    }
    // Power — top-level "power_phase"
    const power = (wh.power_phase || "").toLowerCase();
    if (power.includes("3-phase") || power.includes("3 phase") || power.includes("three")) {
      pills.push({ label: "3-Phase Power", icon: "power" });
    }
    // Office — nested in truth_core
    if (wh.truth_core?.has_office) {
      pills.push({ label: "Office Space", icon: "office" });
    }
    // Parking — top-level
    if (wh.parking_spaces && wh.parking_spaces > 0) {
      pills.push({
        label: `${wh.parking_spaces} Parking`,
        icon: "parking",
      });
    }
    // Drive-in bays — top-level
    if (wh.drive_in_bays && wh.drive_in_bays > 0) {
      pills.push({
        label: `${wh.drive_in_bays} Drive-In`,
        icon: "drivein",
      });
    }

    return pills.slice(0, 5);
  }

  /* ---------------------------------------------------------------- */
  /*  Build Demo Options (Tier 1 + Tier 2)                             */
  /* ---------------------------------------------------------------- */
  function buildDemoOptions(): {
    tier1: MatchOption[];
    tier2: MatchOption[];
  } {
    const buyerNeed = getBuyerNeed();
    const buyerSqft = parseBuyerSqft(buyerNeed);
    const buyerRate = parseBuyerRate(buyerNeed, buyerSqft);

    const tier1Options: MatchOption[] = [];
    const tier2Options: MatchOption[] = [];

    // Try to use locally activated warehouses
    try {
      const stored = localStorage.getItem("wex_activated_warehouses");
      if (stored) {
        const localWarehouses = JSON.parse(stored);
        if (localWarehouses.length > 0) {
          localWarehouses.forEach((wh: any, i: number) => {
            const warehouseSqft =
              wh.available_sqft || wh.total_sqft || 10000;
            const allocatedSqft = Math.min(buyerSqft, warehouseSqft);
            // Calculate buyer rate from actual supplier rate using WEx formula
            const supplierRate =
              wh.supplier_rate || wh.truth_core?.rate_ask || 0;
            const matchRate =
              supplierRate > 0
                ? Math.ceil(supplierRate * 1.2 * 1.06 * 100) / 100
                : buyerRate;
            const monthlyCost =
              Math.round(matchRate * allocatedSqft * 100) / 100;
            const matchScore = [94, 89, 84, 78, 76][i] || 74;
            const termMonths = 6;
            const termTotal =
              Math.round(monthlyCost * termMonths * 100) / 100;

            const features = buildFeaturePills(wh);

            // Build specific "Why This Space" text from actual data
            const whyParts: string[] = [];
            if (wh.clear_height) {
              whyParts.push(`${wh.clear_height}-foot clear height accommodates high-stack pallet storage for your inventory`);
            }
            if (wh.dock_doors) {
              whyParts.push(`${wh.dock_doors} dock doors support efficient receiving and shipping operations`);
            }
            if (wh.city) {
              whyParts.push(`Located in the ${wh.city} industrial corridor`);
            }
            if (warehouseSqft > allocatedSqft * 1.5) {
              whyParts.push(`The ${warehouseSqft.toLocaleString()} sqft building has room to expand without relocating`);
            }
            if (wh.sprinklered) {
              whyParts.push(`Fully sprinklered facility`);
            }
            if (wh.truth_core?.has_office) {
              whyParts.push(`On-site office space included`);
            }
            const matchExplanation = whyParts.length > 0
              ? `${whyParts.slice(0, 4).join(". ")}. Your ${allocatedSqft.toLocaleString()} sqft requirement fits well within the available space.`
              : `This ${allocatedSqft.toLocaleString()} sqft space in ${wh.city || "the area"} is a strong match for your storage requirements.`;

            // Map activity tier to display name
            const activityMap: Record<string, string> = {
              storage_only: "Storage",
              storage_light_assembly: "Storage & Light Assembly",
              distribution: "Distribution",
              ecommerce_fulfillment: "E-Commerce Fulfillment",
              manufacturing_light: "Light Manufacturing",
            };
            const propertyType = activityMap[wh.truth_core?.activity_tier] || wh.truth_core?.activity_tier || "Industrial";

            const opt: MatchOption = {
              match_id: `match-local-${i}`,
              warehouse_id: wh.id,
              tier: i < 3 ? 1 : 2,
              match_score: matchScore,
              match_explanation: matchExplanation,
              location: (() => {
                let city = wh.city || "";
                let state = wh.state || "";
                // Fallback: extract from address "1234 St, City, ST 12345"
                if (!city && wh.address) {
                  const parts = wh.address.split(",").map((s: string) => s.trim());
                  if (parts.length >= 2) {
                    city = parts[parts.length - 2] || "";
                    const stateZip = parts[parts.length - 1] || "";
                    const stateMatch = stateZip.match(/^([A-Z]{2})/);
                    if (stateMatch && !state) state = stateMatch[1];
                  }
                }
                return {
                  city,
                  state,
                  neighborhood: city
                    ? `${city}${state ? `, ${state}` : ""}`
                    : "Metro Area",
                };
              })(),
              property: {
                type: propertyType,
                building_class: "A",
                available_sqft: allocatedSqft,
                building_total_sqft: warehouseSqft,
              },
              features,
              pricing: {
                rate_sqft: matchRate,
                monthly_total: monthlyCost,
                term_months: termMonths,
                term_total: termTotal,
              },
              market_context: {
                area_name: `${wh.city || "Metro"}, ${wh.state || ""}`.trim(),
                rate_low:
                  Math.round(matchRate * 0.65 * 100) / 100,
                rate_high:
                  Math.round(matchRate * 1.2 * 100) / 100,
              },
              primary_image: wh.image_url
                ? { url: wh.image_url, type: "supplier" }
                : null,
              instant_book_eligible: i === 0,
              description: wh.description || undefined,
              images: wh.image_url
                ? [
                    { url: wh.image_url, type: "supplier" },
                    ...(wh.image_urls || []).slice(0, 4).map((u: string) => ({ url: u, type: "supplier" })),
                  ]
                : [],
              has_virtual_tour: !!wh.virtual_tour_url,
            };

            if (i < 3) {
              tier1Options.push(opt);
            } else {
              tier2Options.push(opt);
            }
          });

          // Always add at least one Tier 2 option for demo purposes
          if (tier2Options.length === 0) {
            tier2Options.push({
              match_id: "match-tier2-demo-1",
              warehouse_id: "wh-sourcing-1",
              tier: 2,
              match_score: 78,
              match_explanation: "",
              location: {
                city:
                  buyerNeed.location?.split(",")[0]?.trim() || "Metro",
                state:
                  buyerNeed.location?.split(",")[1]?.trim() || "",
                neighborhood: buyerNeed.location || "Metro Area",
              },
              property: {
                type: "Industrial",
                available_sqft: buyerSqft,
              },
              features: [],
              pricing: {
                rate_sqft: 0,
                monthly_total: 0,
                term_months: 6,
                term_total: 0,
              },
              primary_image: null,
            });
          }

          return { tier1: tier1Options, tier2: tier2Options };
        }
      }
    } catch {
      // fall through
    }

    // Hardcoded fallback
    const monthlyCost = Math.round(buyerRate * buyerSqft * 100) / 100;
    const termMonths = 6;
    const termTotal = Math.round(monthlyCost * termMonths * 100) / 100;

    return {
      tier1: [
        {
          match_id: "match-demo-1",
          warehouse_id: "wh-demo-1",
          tier: 1,
          match_score: 94,
          match_explanation: `This ${buyerSqft.toLocaleString()} sqft allocation matches your needs with strong logistics access, dock-high loading, and flexible activity tiers. Located in the Phoenix industrial corridor with proximity to major highways. The WEx Clearing Engine scored this as a 94% match based on location fit, size alignment, and feature compatibility with your stated requirements.`,
          location: {
            city: "Phoenix",
            state: "AZ",
            neighborhood: "South Phoenix Industrial Corridor",
          },
          property: {
            type: "Industrial",
            building_class: "A",
            available_sqft: buyerSqft,
            building_total_sqft: Math.round(buyerSqft * 1.6),
          },
          features: [
            { label: "30' Clear", icon: "height" },
            { label: "12 Dock Doors", icon: "dock" },
            { label: "Sprinklered", icon: "sprinkler" },
            { label: "3-Phase Power", icon: "power" },
            { label: "20+ Parking", icon: "parking" },
          ],
          pricing: {
            rate_sqft: buyerRate,
            monthly_total: monthlyCost,
            term_months: termMonths,
            term_total: termTotal,
          },
          market_context: {
            area_name: "Phoenix, AZ",
            rate_low: Math.round(buyerRate * 0.65 * 100) / 100,
            rate_high: Math.round(buyerRate * 1.2 * 100) / 100,
          },
          primary_image: null,
          images: [],
          has_virtual_tour: false,
          instant_book_eligible: false,
        },
      ],
      tier2: [
        {
          match_id: "match-tier2-1",
          warehouse_id: "wh-sourcing-1",
          tier: 2,
          match_score: 82,
          match_explanation: "",
          location: {
            city: "Phoenix",
            state: "AZ",
            neighborhood: "West Phoenix Logistics Park",
          },
          property: {
            type: "Industrial",
            available_sqft: buyerSqft,
          },
          features: [
            { label: "24' Clear", icon: "height" },
            { label: "8 Dock Doors", icon: "dock" },
            { label: "Sprinklered", icon: "sprinkler" },
          ],
          pricing: {
            rate_sqft: 0,
            monthly_total: 0,
            term_months: 6,
            term_total: 0,
          },
          primary_image: null,
        },
        {
          match_id: "match-tier2-2",
          warehouse_id: "wh-sourcing-2",
          tier: 2,
          match_score: 76,
          match_explanation: "",
          location: {
            city: "Chandler",
            state: "AZ",
            neighborhood: "Chandler Distribution Zone",
          },
          property: {
            type: "Flex",
            available_sqft: Math.round(buyerSqft * 1.2),
          },
          features: [
            { label: "Office Space", icon: "office" },
            { label: "6 Dock Doors", icon: "dock" },
          ],
          pricing: {
            rate_sqft: 0,
            monthly_total: 0,
            term_months: 6,
            term_total: 0,
          },
          primary_image: null,
        },
      ],
    };
  }

  /* ---------------------------------------------------------------- */
  /*  Load from Session Token (new anonymous flow)                     */
  /* ---------------------------------------------------------------- */
  async function loadFromSession(token: string) {
    setLoading(true);
    setError(null);

    // Try cached results from localStorage first (set during search)
    let cached: any = null;
    try {
      const stored = localStorage.getItem("wex_search_session");
      if (stored) cached = JSON.parse(stored);
    } catch {
      /* ignore */
    }

    if (token === "local") {
      // Pure fallback -- use demo data from localStorage
      const demo = buildDemoOptions();
      setTier1(demo.tier1);
      setTier2(demo.tier2);
      setLoading(false);
      return;
    }

    try {
      // Fetch from backend session cache
      const data = await api.getSearchSession(token);
      const t1: MatchOption[] = data.tier1 || [];
      const t2: MatchOption[] = data.tier2 || [];

      if (t1.length > 0 || t2.length > 0) {
        setTier1(
          t1.sort(
            (a: MatchOption, b: MatchOption) =>
              b.match_score - a.match_score
          )
        );
        setTier2(t2);
      } else {
        // Backend returned empty -- use demo data
        const demo = buildDemoOptions();
        setTier1(demo.tier1);
        setTier2(demo.tier2);
      }
    } catch {
      // Backend unavailable -- try cached results, then demo
      if (
        cached &&
        (cached.tier1?.length > 0 || cached.tier2?.length > 0)
      ) {
        setTier1(cached.tier1 || []);
        setTier2(cached.tier2 || []);
      } else {
        const demo = buildDemoOptions();
        setTier1(demo.tier1);
        setTier2(demo.tier2);
      }
    } finally {
      setLoading(false);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Load Options from API (legacy need_id flow)                      */
  /* ---------------------------------------------------------------- */
  async function loadOptions(nId: string) {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getClearedOptions(nId);
      const opts: MatchOption[] = Array.isArray(data)
        ? data
        : data.options || data.matches || [];
      if (opts.length > 0) {
        // Split into tiers
        const t1 = opts
          .filter((o) => o.tier === 1 || !o.tier)
          .slice(0, 3)
          .sort((a, b) => b.match_score - a.match_score);
        const t2 = opts.filter((o) => o.tier === 2);
        setTier1(t1);
        setTier2(t2);
      } else {
        const demo = buildDemoOptions();
        setTier1(demo.tier1);
        setTier2(demo.tier2);
      }
    } catch (err: any) {
      // Only show error banner for real connection failures, not 404s (expected in demo mode)
      const msg = err.message || "Failed to load options";
      const isExpectedError =
        msg.includes("not found") ||
        msg.includes("404") ||
        msg.includes("422");
      if (!isExpectedError) {
        setError(msg);
      }
      const demo = buildDemoOptions();
      setTier1(demo.tier1);
      setTier2(demo.tier2);
    } finally {
      setLoading(false);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Accept handler (opens contact modal first if needed)             */
  /* ---------------------------------------------------------------- */
  function handleAcceptClick(matchId: string) {
    if (contactCaptured) {
      executeAccept(matchId);
    } else {
      setPendingMatchId(matchId);
      setContactModalOpen(true);
    }
  }

  function handleContactSubmitted() {
    setContactModalOpen(false);
    setContactCaptured(true);
    if (pendingMatchId) {
      executeAccept(pendingMatchId);
      setPendingMatchId(null);
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function handleAskClick(_matchId: string) {
    // Open contact capture if not already captured, then could open a chat/inquiry flow
    if (!contactCaptured) {
      setPendingMatchId(null);
      setContactModalOpen(true);
    } else {
      // For now, show a simple confirmation
      alert(
        "A WEx specialist will reach out to you shortly about this space."
      );
    }
  }

  async function executeAccept(matchId: string) {
    setAccepting(matchId);

    // Find the matching option for warehouse info
    const option = tier1.find((o) => o.match_id === matchId);

    try {
      // Try to accept via API if we have a legacy need ID
      const result = legacyNeedId
        ? await api.acceptMatch(legacyNeedId, {
            match_id: matchId,
            deal_type: "standard",
          })
        : null;

      // Open TourBookingFlow instead of redirecting
      const deal = result?.deal || {
        id: result?.deal_id || `deal-${matchId}`,
        warehouse_id: option?.warehouse_id || "",
        sqft_allocated: option?.property.available_sqft || 0,
        rate_per_sqft: option?.pricing.rate_sqft || 0,
        monthly_payment: option?.pricing.monthly_total || 0,
        term_months: option?.pricing.term_months || 6,
        guarantee_signed_at: null,
        status: "terms_accepted",
      };

      const warehouse = {
        id: option?.warehouse_id || "",
        address: null, // Masked until guarantee signed
        city: option?.location.city || "",
        state: option?.location.state || "",
        zip: null,
        building_size_sqft: option?.property.available_sqft || 0,
        primary_image_url: option?.primary_image?.url || null,
      };

      setTourFlowDeal(deal);
      setTourFlowWarehouse(warehouse);
      setTourFlowOpen(true);
    } catch {
      // Even on API error, open the flow with demo data
      const deal = {
        id: `deal-${matchId}`,
        warehouse_id: option?.warehouse_id || "",
        sqft_allocated: option?.property.available_sqft || 0,
        rate_per_sqft: option?.pricing.rate_sqft || 0,
        monthly_payment: option?.pricing.monthly_total || 0,
        term_months: option?.pricing.term_months || 6,
        guarantee_signed_at: null,
        status: "terms_accepted",
      };

      const warehouse = {
        id: option?.warehouse_id || "",
        address: null,
        city: option?.location.city || "",
        state: option?.location.state || "",
        zip: null,
        building_size_sqft: option?.property.available_sqft || 0,
        primary_image_url: option?.primary_image?.url || null,
      };

      setTourFlowDeal(deal);
      setTourFlowWarehouse(warehouse);
      setTourFlowOpen(true);
    } finally {
      setAccepting(null);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Determine which state to show                                    */
  /* ---------------------------------------------------------------- */
  const hasTier1 = tier1.length > 0;

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link
                href="/buyer"
                className="text-slate-400 hover:text-slate-600 transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900">
                  W<span className="text-blue-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">
                  {hasTier1 ? "Cleared Options" : "Sourcing Options"}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* Email Me This List button (only when Tier 1 results exist) */}
              {!loading && hasTier1 && (
                <button
                  onClick={() => {
                    if (contactCaptured) {
                      alert(
                        "We'll email you a summary of these options shortly."
                      );
                    } else {
                      setEmailListModalOpen(true);
                    }
                  }}
                  className="hidden sm:flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 transition-colors border border-gray-300 hover:border-gray-400 px-3 py-1.5 rounded-lg"
                >
                  <Mail className="w-3.5 h-3.5" />
                  Email Me This List
                </button>
              )}
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Shield className="w-4 h-4 text-emerald-500" />
                <span className="hidden sm:inline">WEx Guaranteed</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* -------------------------------------------------------- */}
        {/*  Loading State                                            */}
        {/* -------------------------------------------------------- */}
        {loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-24"
          >
            <div className="relative">
              <Loader2 className="w-14 h-14 text-emerald-500 animate-spin" />
              <Zap className="w-6 h-6 text-emerald-400 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
            </div>
            <p className="text-slate-900 font-medium mt-5 text-lg">
              Running WEx Clearing Engine...
            </p>
            <p className="text-sm text-slate-500 mt-1">
              Analyzing warehouse network for optimal matches
            </p>
          </motion.div>
        )}

        {/* -------------------------------------------------------- */}
        {/*  Error banner (non-blocking -- demo data still shows)     */}
        {/* -------------------------------------------------------- */}
        {error && !loading && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3 mb-6"
          >
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                Could not connect to backend
              </p>
              <p className="text-xs text-amber-600 mt-1">
                Showing demo matches. Start the FastAPI backend for live
                data.
              </p>
            </div>
          </motion.div>
        )}

        {/* -------------------------------------------------------- */}
        {/*  STATE 1: Tier 1 matches exist                            */}
        {/* -------------------------------------------------------- */}
        {!loading && hasTier1 && (
          <>
            {/* Page Title */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-8"
            >
              <h2 className="text-2xl font-bold text-slate-900 mb-2">
                Cleared Options
              </h2>
              <p className="text-slate-500">
                We found {tier1.length}{" "}
                {tier1.length === 1 ? "space" : "spaces"} that match your
                requirements. All rates shown are all-in — no hidden fees.
              </p>
            </motion.div>

            {/* Tier 1 Cards */}
            <div className="space-y-8">
              {tier1.map((option, i) => (
                <Tier1Card
                  key={option.match_id}
                  option={option}
                  index={i}
                  onAccept={handleAcceptClick}
                  onAsk={handleAskClick}
                  accepting={accepting}
                />
              ))}
            </div>

            {/* Tier 2 Section */}
            {tier2.length > 0 && (
              <div className="mt-12">
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                  className="flex items-center gap-3 mb-6"
                >
                  <div className="h-px flex-1 bg-gray-200" />
                  <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                    <Clock className="w-4 h-4" />
                    Being Evaluated
                  </div>
                  <div className="h-px flex-1 bg-gray-200" />
                </motion.div>

                <div className="space-y-4">
                  {tier2.map((option, i) => (
                    <Tier2Card
                      key={option.match_id}
                      option={option}
                      index={i}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* -------------------------------------------------------- */}
        {/*  STATE 3: No Tier 1 Matches -- first-class sourcing screen */}
        {/* -------------------------------------------------------- */}
        {!loading && !hasTier1 && (
          <>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center py-12"
            >
              {/* Animated search icon */}
              <div className="relative inline-flex items-center justify-center w-20 h-20 mb-6">
                <motion.div
                  animate={{ scale: [1, 1.15, 1] }}
                  transition={{
                    duration: 2.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                  className="absolute inset-0 rounded-full bg-emerald-50"
                />
                <motion.div
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{
                    duration: 2.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: 0.3,
                  }}
                  className="absolute inset-2 rounded-full bg-emerald-100"
                />
                <Search className="w-8 h-8 text-emerald-400 relative z-10" />
              </div>

              <h2 className="text-2xl font-bold text-slate-900 mb-3">
                We&apos;re sourcing options for your search
              </h2>
              <p className="text-slate-500 max-w-lg mx-auto text-base leading-relaxed">
                Based on our network, expect 2&ndash;4 options within
                24&ndash;48 hours. Our DLA (Dynamic Listing Acquisition)
                engine is actively reaching out to warehouse operators in
                your target market.
              </p>
            </motion.div>

            {/* Contact Capture */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="max-w-2xl mx-auto mb-12"
            >
              <NoMatchContactCapture
                onSubmit={() => setContactCaptured(true)}
              />
            </motion.div>

            {/* Tier 2 "being sourced" cards */}
            {tier2.length > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 }}
              >
                <div className="flex items-center gap-3 mb-6">
                  <div className="h-px flex-1 bg-gray-200" />
                  <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                    <Clock className="w-4 h-4" />
                    Being Sourced
                  </div>
                  <div className="h-px flex-1 bg-gray-200" />
                </div>

                <div className="space-y-4">
                  {tier2.map((option, i) => (
                    <Tier2Card
                      key={option.match_id}
                      option={option}
                      index={i}
                    />
                  ))}
                </div>
              </motion.div>
            )}
          </>
        )}

        {/* Footer */}
        <div className="text-center py-8 mt-4">
          <div className="flex items-center justify-center gap-2 mb-2">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            <span className="text-sm text-emerald-600 font-medium">
              WEx Occupancy Guarantee Insurance included
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Powered by W
            <span className="text-blue-500 font-semibold">Ex</span>{" "}
            Clearing House | All-in pricing, no hidden fees
          </p>
        </div>
      </main>

      {/* Contact Capture Modal -- "Accept & Schedule Tour" trigger */}
      <ContactCaptureModal
        open={contactModalOpen}
        onClose={() => {
          setContactModalOpen(false);
          setPendingMatchId(null);
        }}
        onSubmit={handleContactSubmitted}
        headline="Confirm Your Tour"
        subtitle="We need your contact info to schedule the tour with the warehouse operator."
        submitLabel="Confirm & Schedule Tour"
        trustText="We'll only use this to coordinate your tour. No spam, ever."
      />

      {/* Contact Capture Modal -- "Email Me This List" trigger */}
      <ContactCaptureModal
        open={emailListModalOpen}
        onClose={() => setEmailListModalOpen(false)}
        onSubmit={() => {
          setEmailListModalOpen(false);
          setContactCaptured(true);
        }}
        headline="Email Me This List"
        subtitle="We'll send a summary of all matched options to your inbox."
        submitLabel="Send My Options"
        trustText="Service, not a gate. We'll only email you about these results."
        emailOnly
      />

      {/* Tour Booking Flow -- anti-circumvention multi-step modal */}
      {tourFlowDeal && tourFlowWarehouse && (
        <TourBookingFlow
          open={tourFlowOpen}
          onClose={() => {
            setTourFlowOpen(false);
            setTourFlowDeal(null);
            setTourFlowWarehouse(null);
          }}
          deal={tourFlowDeal}
          warehouse={tourFlowWarehouse}
          onComplete={() => {
            setTourFlowOpen(false);
            router.push("/buyer/deals");
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page Component with Suspense boundary for useSearchParams          */
/* ------------------------------------------------------------------ */
export default function BuyerOptionsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
        </div>
      }
    >
      <OptionsContent />
    </Suspense>
  );
}
