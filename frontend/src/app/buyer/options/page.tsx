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
  Ruler,
  Box,
  Settings2,
  Edit2,
  Smartphone,
} from "lucide-react";
import { api } from "@/lib/api";
import ContactCaptureModal from "@/components/ui/ContactCaptureModal";
import TourBookingFlow from "@/components/ui/TourBookingFlow";
import ModifySearchDrawer, { type SearchIntent } from "@/components/ui/ModifySearchDrawer";

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
    zip?: string;
    neighborhood?: string;
    distance_miles?: number | null;
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

const ACTIVITY_TIER_LABELS: Record<string, string> = {
  storage_only: "Storage Only",
  storage_light_assembly: "Storage & Light Assembly",
  distribution: "Distribution",
  ecommerce_fulfillment: "E-Commerce Fulfillment",
  manufacturing_light: "Light Manufacturing",
  manufacturing_heavy: "Heavy Manufacturing",
  cold_storage: "Cold Storage",
  cross_dock: "Cross Dock",
};

function formatActivityTier(raw: string | undefined | null): string {
  if (!raw) return "Industrial";
  if (ACTIVITY_TIER_LABELS[raw]) return ACTIVITY_TIER_LABELS[raw];
  // Fallback: convert snake_case to Title Case
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------------ */
/*  Map flat API tier1 response to nested MatchOption                   */
/* ------------------------------------------------------------------ */
function mapApiToMatchOption(raw: any): MatchOption {
  // If already nested (e.g. from buildDemoOptions), pass through
  if (raw.location && typeof raw.location === "object") return raw as MatchOption;

  const features: FeaturePill[] = [];
  const f = raw.features || {};
  if (f.clear_height) features.push({ label: `${f.clear_height}ft Clear`, icon: "height" });
  if (f.dock_doors) features.push({ label: `${f.dock_doors} Docks`, icon: "dock" });
  if (f.has_sprinkler) features.push({ label: "Sprinklered", icon: "sprinkler" });
  if (f.has_office) features.push({ label: "Office Space", icon: "office" });
  if (f.parking) features.push({ label: `${f.parking} Parking`, icon: "parking" });

  return {
    match_id: raw.match_id || "",
    warehouse_id: raw.warehouse_id || "",
    tier: raw.tier || 1,
    match_score: raw.confidence ?? raw.match_score ?? 0,
    match_explanation: raw.reasoning || raw.match_explanation || "",
    location: {
      city: raw.city || "",
      state: raw.state || "",
      zip: raw.zip || "",
      neighborhood: raw.neighborhood || "",
      distance_miles: raw.distance_miles ?? null,
    },
    property: {
      type: formatActivityTier(f.activity_tier),
      available_sqft: raw.available_sqft || 0,
      building_total_sqft: raw.building_size_sqft || undefined,
    },
    features,
    pricing: {
      rate_sqft: raw.buyer_rate || 0,
      monthly_total: raw.monthly_cost || 0,
      term_months: raw.term_months || 6,
      term_total: raw.total_value || 0,
    },
    primary_image: raw.primary_image_url
      ? { url: raw.primary_image_url, type: "supplier" }
      : null,
    instant_book_eligible: raw.instant_book_eligible || false,
    description: raw.description || undefined,
    use_type_callouts: raw.use_type_callouts || [],
    within_budget: raw.within_budget ?? true,
    budget_stretch_pct: raw.budget_stretch_pct ?? 0,
    budget_alternative_available: raw.budget_alternative_available ?? false,
  } as MatchOption;
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
  const [lightbox, setLightbox] = useState(false);
  const [lbIndex, setLbIndex] = useState(0);
  const [failedUrls, setFailedUrls] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || el.clientWidth === 0) return;
    const idx = Math.round(el.scrollLeft / el.clientWidth);
    setSwipeIndex(idx);
  }, []);

  // Filter out broken images
  const validImages = images.filter((img) => !failedUrls.has(img.url));
  const handleImgError = (url: string) => {
    setFailedUrls((prev) => new Set(prev).add(url));
  };

  const hero = validImages[0] || null;
  const insets = validImages.slice(1, 3);
  const extraCount = Math.max(0, validImages.length - 3);

  // --- EMPTY STATE ---
  if (validImages.length === 0) {
    return (
      <div className="relative w-full aspect-video bg-gradient-to-br from-slate-100 to-slate-200 flex flex-col items-center justify-center gap-3">
        <Building2 className="w-16 h-16 text-slate-300" />
        <span className="text-sm text-slate-400">Satellite view pending</span>
      </div>
    );
  }

  // --- SINGLE IMAGE ---
  if (validImages.length === 1) {
    return (
      <div className="relative w-full aspect-video bg-slate-100 overflow-hidden">
        <img src={hero!.url} alt={alt} className="absolute inset-0 w-full h-full object-cover" onError={() => handleImgError(hero!.url)} />
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
        <div className="relative overflow-hidden cursor-pointer" onClick={() => { setLbIndex(0); setLightbox(true); }}>
          <img src={hero!.url} alt={alt} className="absolute inset-0 w-full h-full object-cover" onError={() => handleImgError(hero!.url)} />
          {hasVirtualTour && <VirtualTourButton />}
        </div>
        {/* Inset stack */}
        <div className="flex flex-col gap-1">
          {insets.map((img, i) => (
            <div key={i} className="relative flex-1 overflow-hidden cursor-pointer" onClick={() => { setLbIndex(i + 1); setLightbox(true); }}>
              <img src={img.url} alt={`${alt} ${i + 2}`} className="absolute inset-0 w-full h-full object-cover" onError={() => handleImgError(img.url)} />
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
          {validImages.map((img, i) => (
            <div key={i} className="snap-center shrink-0 w-full aspect-video relative bg-slate-100">
              <img src={img.url} alt={`${alt} ${i + 1}`} className="absolute inset-0 w-full h-full object-cover" onError={() => handleImgError(img.url)} />
              {i === 0 && hasVirtualTour && <VirtualTourButton />}
            </div>
          ))}
        </div>
        {/* Pagination dots */}
        {validImages.length > 1 && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
            {validImages.map((_, i) => (
              <div key={i} className={`w-2 h-2 rounded-full transition-colors ${i === swipeIndex ? "bg-white" : "bg-white/50"}`} />
            ))}
          </div>
        )}
      </div>

      {/* Lightbox modal */}
      {lightbox && (
        <div className="fixed inset-0 z-[9999] bg-black/90 flex items-center justify-center" onClick={() => setLightbox(false)}>
          {/* Close button */}
          <button className="absolute top-4 right-4 text-white/80 hover:text-white text-3xl font-light z-10 w-10 h-10 flex items-center justify-center" onClick={() => setLightbox(false)}>✕</button>
          {/* Prev */}
          {validImages.length > 1 && (
            <button className="absolute left-4 text-white/70 hover:text-white text-4xl z-10" onClick={(e) => { e.stopPropagation(); setLbIndex((lbIndex - 1 + validImages.length) % validImages.length); }}>‹</button>
          )}
          {/* Image */}
          <img
            src={validImages[lbIndex]?.url}
            alt={`${alt} ${lbIndex + 1}`}
            className="max-h-[85vh] max-w-[90vw] object-contain rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />
          {/* Next */}
          {validImages.length > 1 && (
            <button className="absolute right-14 text-white/70 hover:text-white text-4xl z-10" onClick={(e) => { e.stopPropagation(); setLbIndex((lbIndex + 1) % validImages.length); }}>›</button>
          )}
          {/* Counter */}
          <div className="absolute bottom-6 text-white/70 text-sm">{lbIndex + 1} / {validImages.length}</div>
        </div>
      )}
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
  allocatedSqft,
}: {
  option: MatchOption;
  index: number;
  onAccept: (matchId: string) => void;
  onAsk: (matchId: string) => void;
  accepting: string | null;
  allocatedSqft: number;
}) {
  // Derive display strings with fallbacks
  const neighborhood = option.location.neighborhood || "";
  const cityStateZip = [
    option.location.city,
    option.location.state ? `, ${option.location.state}` : "",
    option.location.zip ? ` ${option.location.zip}` : "",
  ].join("").trim() || "Industrial Area";

  // Neighborhood · City, State Zip  (or just City, State Zip if no neighborhood)
  const locationSubline = neighborhood
    ? `${neighborhood} · ${cityStateZip}`
    : cityStateZip;

  // City, State heading — fallback to neighborhood if city empty
  const cityState = option.location.city
    ? `${option.location.city}${option.location.state ? `, ${option.location.state}` : ""}`
    : neighborhood || "Industrial Area";

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
            <div className="flex items-center gap-2 mb-2">
              <div className="flex items-center gap-1.5 text-slate-500 text-sm font-bold uppercase tracking-widest">
                <MapPin size={16} className="flex-shrink-0" />
                {neighborhood || cityState}
              </div>
              {option.location.distance_miles != null && (
                <span className="text-xs font-semibold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full flex-shrink-0">
                  {option.location.distance_miles < 1 ? '<1' : Math.round(option.location.distance_miles)} mi away
                </span>
              )}
            </div>
            {/* Anti-circumvention: NO STREET ADDRESS */}
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900 mb-1">
              {cityState}
            </h2>
            <p className="text-sm text-slate-400 mb-2">
              {locationSubline}
            </p>
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
            {/* Use type callouts */}
            {(option as any).use_type_callouts && (option as any).use_type_callouts.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {(option as any).use_type_callouts.map((callout: string, i: number) => (
                  <span key={i} className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md">
                    {callout}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 4. FINANCIALS ("The Ticket") — 5-column breakdown */}
        <div className="bg-slate-50 rounded-2xl p-6 mb-8 border border-slate-100">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 md:gap-2 items-center text-center">
            {/* Allocated Size */}
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Allocated Size</p>
              <p className="text-xl font-bold text-slate-900">{allocatedSqft.toLocaleString()}</p>
              <p className="text-xs text-slate-500">sqft</p>
            </div>
            {/* × operator */}
            <div className="hidden md:flex items-center justify-center">
              <span className="text-slate-300 text-lg font-bold">×</span>
            </div>
            {/* Your Rate */}
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Your Rate</p>
              <p className="text-xl font-bold text-slate-900">${option.pricing.rate_sqft.toFixed(2)}</p>
              <p className="text-xs text-slate-500">/sqft/month</p>
            </div>
            {/* = operator */}
            <div className="hidden md:flex items-center justify-center">
              <span className="text-slate-300 text-lg font-bold">=</span>
            </div>
            {/* Monthly Cost */}
            <div>
              <p className="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">Monthly Cost</p>
              <p className="text-2xl font-bold text-emerald-600">{formatCurrency(option.pricing.monthly_total)}</p>
              <p className="text-xs text-slate-500">all-in pricing</p>
            </div>
          </div>

          {/* Term row */}
          <div className="mt-4 pt-4 border-t border-slate-200 grid grid-cols-2 md:grid-cols-3 gap-4 items-center text-center">
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Monthly Cost</p>
              <p className="text-lg font-bold text-slate-900">{formatCurrency(option.pricing.monthly_total)}</p>
            </div>
            <div className="hidden md:flex items-center justify-center">
              <span className="text-slate-300 text-lg font-bold">×</span>
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Term</p>
              <p className="text-lg font-bold text-slate-900">{option.pricing.term_months} months</p>
            </div>
          </div>

          {/* Total Value highlight */}
          <div className="mt-4 pt-4 border-t border-slate-200 text-center">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Total Lease Value</p>
            <p className="text-2xl font-bold text-slate-900">{formatCurrency(option.pricing.term_total)}</p>
            <p className="text-xs text-slate-500">over {option.pricing.term_months} months</p>
          </div>

          {/* Budget indicator */}
          {(option as any).budget_stretch_pct != null && (option as any).budget_stretch_pct > 0 && (
            <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-600">
              <span className="w-3 h-3 rounded-full bg-amber-400 flex-shrink-0" />
              <span>{Math.round((option as any).budget_stretch_pct)}% above your stated budget</span>
            </div>
          )}

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

          {/* Show match score instead of just "sourcing" */}
          <div className="flex items-center gap-2 mb-2">
            <div className="text-sm font-medium text-emerald-700">
              {Math.round(option.match_score)}% estimated match
            </div>
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

  // Pending options (Tier 2) subscription state
  const [pendingSubscribed, setPendingSubscribed] = useState(false);

  // Tour booking flow state
  const [tourFlowOpen, setTourFlowOpen] = useState(false);
  const [tourFlowDeal, setTourFlowDeal] = useState<any>(null);
  const [tourFlowWarehouse, setTourFlowWarehouse] = useState<any>(null);

  // Modify Search drawer state
  const [modifyDrawerOpen, setModifyDrawerOpen] = useState(false);

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
  /*  Modify Search — drawer helpers                                    */
  /* ---------------------------------------------------------------- */
  function getCurrentIntent(): SearchIntent {
    const need = getBuyerNeed();
    return {
      location: need.location || "",
      sqft: parseBuyerSqft(need),
      useType: need.use_type || "storage",
      goodsType: need.goods_type || "",
      timing: need.timing || "Immediately",
      duration: need.duration || "6 Months",
      amenities: (need.requirements || "")
        .split(",")
        .map((r: string) => r.trim())
        .filter(Boolean),
    };
  }

  async function handleModifySearch(intent: SearchIntent) {
    setLoading(true);

    // Parse duration to months
    let durationMonths = 6;
    const dMatch = intent.duration.match(/^(\d+)\s*Month/i);
    if (dMatch) durationMonths = parseInt(dMatch[1]);
    else if (intent.duration === "Flexible") durationMonths = 0;

    // Persist updated need to localStorage
    const buyerNeed = {
      location: intent.location,
      size_sqft: `${intent.sqft.toLocaleString()} sqft`,
      sqft_raw: String(intent.sqft),
      use_type: intent.useType,
      goods_type: intent.goodsType || "Not specified",
      timing: intent.timing,
      duration: intent.duration,
      requirements: intent.amenities.join(", ") || "None specified",
    };
    localStorage.setItem("wex_buyer_need", JSON.stringify(buyerNeed));

    // Re-run the clearing engine
    try {
      const result = await api.anonymousSearch({
        location: intent.location,
        use_type: intent.useType,
        goods_type: intent.goodsType || undefined,
        size_sqft: intent.sqft,
        timing: intent.timing,
        duration_months: durationMonths,
        deal_breakers: intent.amenities,
      });

      localStorage.setItem("wex_search_session", JSON.stringify(result));

      // Update results in-place
      if (result.session_token) {
        await loadFromSession(result.session_token);
      } else if (result.matches) {
        // Direct match results
        const mapped = (result.matches || []).map(mapApiToMatchOption);
        const t1 = mapped.filter((m: MatchOption) => m.tier === 1);
        const t2 = mapped.filter((m: MatchOption) => m.tier === 2);
        setTier1(t1);
        setTier2(t2);
        setLoading(false);
      } else {
        setLoading(false);
      }
    } catch (err) {
      console.error("Modify search failed:", err);
      setError("Search update failed. Please try again.");
      setLoading(false);
    }
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

            const propertyType = formatActivityTier(wh.truth_core?.activity_tier);

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
                    ...(wh.image_urls || [])
                      .filter((u: string) => u !== wh.image_url)
                      .slice(0, 4)
                      .map((u: string) => ({ url: u, type: "supplier" })),
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

    // Try cached results matching THIS session token
    let cached: any = null;
    try {
      const stored = localStorage.getItem("wex_search_session");
      if (stored) {
        const parsed = JSON.parse(stored);
        // Only use cache if it matches the current session token
        if (parsed.session_token === token) {
          cached = parsed;
        }
      }
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

    // If we have matching cached results from the search that just ran, use them
    // (avoids an extra API call since anonymousSearch already returned the data)
    if (cached && (cached.tier1?.length > 0 || cached.tier2?.length > 0)) {
      const t1: MatchOption[] = (cached.tier1 || []).map(mapApiToMatchOption);
      const t2: MatchOption[] = (cached.tier2 || []).map(mapApiToMatchOption);
      setTier1(t1.sort((a: MatchOption, b: MatchOption) => b.match_score - a.match_score));
      setTier2(t2);
      setLoading(false);
      return;
    }

    try {
      // Fetch from backend session cache
      const data = await api.getSearchSession(token);
      const t1: MatchOption[] = (data.tier1 || []).map(mapApiToMatchOption);
      const t2: MatchOption[] = (data.tier2 || []).map(mapApiToMatchOption);

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
      // Backend unavailable -- use demo data
      const demo = buildDemoOptions();
      setTier1(demo.tier1);
      setTier2(demo.tier2);
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
      const raw = Array.isArray(data)
        ? data
        : data.options || data.matches || [];
      const opts: MatchOption[] = raw.map(mapApiToMatchOption);
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
            {/* Page Title + Buyer Intent Summary */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="w-full max-w-4xl mx-auto mb-8"
            >
              <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-4">
                <div>
                  <h2 className="text-2xl font-bold text-slate-900 mb-2">
                    Cleared Options
                  </h2>
                  <p className="text-slate-500 text-sm">
                    We found {tier1.length}{" "}
                    {tier1.length === 1 ? "space" : "spaces"} matching your
                    criteria. All rates are all-in.
                  </p>
                </div>
                <button
                  onClick={() => setModifyDrawerOpen(true)}
                  className="flex items-center gap-2 text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:border-slate-400 hover:bg-slate-50 px-4 py-2 rounded-lg transition-all"
                >
                  <Edit2 size={14} /> Modify Search
                </button>
              </div>

              {/* Intent Summary Banner */}
              {(() => {
                const need = getBuyerNeed();
                const hasData = need.location || need.size_sqft || need.use_type;
                if (!hasData) return null;
                const reqPills = (need.requirements || "")
                  .split(",")
                  .map((r: string) => r.trim())
                  .filter(Boolean);
                return (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-wrap items-center gap-y-3 gap-x-6">
                    {need.location && (
                      <>
                        <div className="flex items-center gap-2">
                          <MapPin size={16} className="text-slate-400" />
                          <span className="text-sm font-bold text-slate-700">{need.location}</span>
                        </div>
                        <div className="hidden md:block w-px h-4 bg-slate-300" />
                      </>
                    )}
                    {need.size_sqft && (
                      <>
                        <div className="flex items-center gap-2">
                          <Ruler size={16} className="text-slate-400" />
                          <span className="text-sm font-bold text-slate-700">{need.size_sqft}</span>
                        </div>
                        <div className="hidden md:block w-px h-4 bg-slate-300" />
                      </>
                    )}
                    {need.use_type && (
                      <>
                        <div className="flex items-center gap-2">
                          <Box size={16} className="text-slate-400" />
                          <span className="text-sm font-bold text-slate-700">{need.use_type}</span>
                        </div>
                        {reqPills.length > 0 && (
                          <div className="hidden md:block w-px h-4 bg-slate-300" />
                        )}
                      </>
                    )}
                    {reqPills.length > 0 && (
                      <div className="flex items-center gap-2">
                        <Settings2 size={16} className="text-slate-400" />
                        <div className="flex gap-1.5 flex-wrap">
                          {reqPills.map((req: string, i: number) => (
                            <span key={i} className="text-xs font-bold text-slate-600 bg-slate-200/70 px-2 py-0.5 rounded-md">
                              {req}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </motion.div>

            {/* Tier 1 Cards */}
            <div className="space-y-8">
              {(() => {
                const allocSqft = parseBuyerSqft(getBuyerNeed());
                return tier1.map((option, i) => (
                  <Tier1Card
                    key={option.match_id}
                    option={option}
                    index={i}
                    onAccept={handleAcceptClick}
                    onAsk={handleAskClick}
                    accepting={accepting}
                    allocatedSqft={allocSqft}
                  />
                ));
              })()}
            </div>

            {/* Pending Options Strip (Tier 2 as status indicator) */}
            {tier2.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
                className="w-full max-w-4xl mx-auto mt-8 mb-24"
              >
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 md:p-6 flex flex-col md:flex-row items-center justify-between gap-6 shadow-sm">
                  {/* LEFT: Status Indicator */}
                  <div className="flex items-start gap-4 w-full md:w-auto">
                    <div className="mt-1 bg-blue-100 text-blue-600 p-2 rounded-full relative flex-shrink-0">
                      <span className="animate-ping absolute inset-0 rounded-full bg-blue-400 opacity-20" />
                      <Search size={20} className="relative z-10" />
                    </div>
                    <div>
                      <h4 className="text-lg font-bold text-slate-900 mb-1">
                        {tier2.length} more {tier2.length === 1 ? "space" : "spaces"} in your area {tier2.length === 1 ? "is" : "are"} being confirmed.
                      </h4>
                      <p className="text-sm text-slate-600">
                        We are actively verifying terms. We&apos;ll notify you as they become available.
                      </p>
                    </div>
                  </div>

                  {/* RIGHT: Lead Capture */}
                  <div className="w-full md:w-auto flex-shrink-0">
                    {!pendingSubscribed ? (
                      <div className="flex flex-col sm:flex-row gap-3">
                        <button
                          onClick={() => setPendingSubscribed(true)}
                          className="flex items-center justify-center gap-2 bg-white border border-slate-300 hover:border-slate-900 hover:bg-slate-900 hover:text-white text-slate-700 text-sm font-bold py-2.5 px-5 rounded-lg transition-all"
                        >
                          <Smartphone size={16} /> Text Me Updates
                        </button>
                        <button
                          onClick={() => setPendingSubscribed(true)}
                          className="flex items-center justify-center gap-2 bg-white border border-slate-300 hover:border-slate-900 hover:bg-slate-900 hover:text-white text-slate-700 text-sm font-bold py-2.5 px-5 rounded-lg transition-all"
                        >
                          <Mail size={16} /> Email Me
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 border border-emerald-200 py-2.5 px-5 rounded-lg text-sm font-bold">
                        <CheckCircle2 size={18} /> You&apos;re on the list
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
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

      {/* Modify Search — slide-out drawer */}
      <ModifySearchDrawer
        isOpen={modifyDrawerOpen}
        onClose={() => setModifyDrawerOpen(false)}
        currentIntent={getCurrentIntent()}
        onUpdate={handleModifySearch}
      />
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
