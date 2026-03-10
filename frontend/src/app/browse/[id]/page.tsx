"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  MapPin,
  Warehouse as WarehouseIcon,
  X,
  Truck,
  Building2,
  Thermometer,
  Zap,
  Clock,
  ParkingSquare,
  Loader2,
  Menu,
  Calendar,
  Bolt,
  Info,
  CheckCircle,
  AlertTriangle,
  Camera,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api";
import ApproximateLocationMap from "@/components/maps/ApproximateLocationMap";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PropertyDetail {
  id: string;
  tier: 1 | 2;
  location: { city: string; state: string; display: string };
  building_type: string;
  features: { key: string; label: string }[];
  specs: Record<string, any>;
  sqft_range: { min: number; max: number; display: string } | null;
  rate_range: { min: number; max: number; display: string } | null;
  instant_book_eligible: boolean;
  tour_required: boolean;
  has_image: boolean;
  image_url?: string | null;
  image_urls: string[];
  approximate_location: { lat: number; lng: number } | null;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const FEATURE_ICON_MAP: Record<string, typeof Truck> = {
  dock: Truck,
  office: Building2,
  climate: Thermometer,
  power: Zap,
  "24_7": Clock,
  parking: ParkingSquare,
};

const SPEC_LABELS: Record<string, { label: string; suffix?: string; boolean?: boolean; format?: "number" }> = {
  clear_height_ft: { label: "Clear Height", suffix: " ft" },
  dock_doors: { label: "Dock Doors" },
  parking_spaces: { label: "Parking Spaces" },
  has_office: { label: "Office Space", boolean: true },
  has_sprinkler: { label: "Sprinkler System", boolean: true },
  power_supply: { label: "Power Supply" },
  year_built: { label: "Year Built" },
  construction_type: { label: "Construction" },
  zoning: { label: "Zoning" },
  building_size_sqft: { label: "Building Size", suffix: " sqft", format: "number" },
};

function formatSpecValue(key: string, value: any): string | null {
  const config = SPEC_LABELS[key];
  if (!config) return null;
  if (value === null || value === undefined) return null;

  if (config.boolean) {
    return value ? "Yes" : "No";
  }

  if (config.format === "number" && typeof value === "number") {
    return value.toLocaleString() + (config.suffix || "");
  }

  return String(value) + (config.suffix || "");
}

/* ------------------------------------------------------------------ */
/*  Navbar                                                             */
/* ------------------------------------------------------------------ */

function BrowseNavbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 20);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-white/90 backdrop-blur-md border-b border-slate-200 shadow-lg shadow-slate-900/5"
          : "bg-white border-b border-slate-100"
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2">
          <WarehouseIcon className="h-6 w-6 text-emerald-600" />
          <span className="text-lg font-bold text-slate-900">WEx</span>
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          <Link
            href="/browse"
            className="text-sm font-medium text-slate-900"
          >
            Browse Spaces
          </Link>
          <Link
            href="/supplier/earncheck?intent=onboard"
            className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
          >
            List Your Space
          </Link>
          <Link
            href="/buyer"
            className="inline-flex h-9 items-center justify-center rounded-lg bg-emerald-600 px-5 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
          >
            Find Space
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="text-slate-600 hover:text-slate-900 md:hidden"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-slate-200 bg-white/95 backdrop-blur-md px-6 py-6 md:hidden">
          <div className="flex flex-col gap-4">
            <Link href="/browse" onClick={() => setMobileOpen(false)} className="text-sm font-medium text-slate-900">
              Browse Spaces
            </Link>
            <Link href="/supplier/earncheck?intent=onboard" onClick={() => setMobileOpen(false)} className="text-sm text-slate-600 hover:text-slate-900 transition-colors">
              List Your Space
            </Link>
            <Link href="/buyer" onClick={() => setMobileOpen(false)} className="inline-flex h-10 items-center justify-center rounded-lg bg-emerald-600 px-5 text-sm font-semibold text-white transition-all hover:bg-emerald-500">
              Find Space
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/*  SafeImage — Frosted Contain (prevents awkward cropping)            */
/* ------------------------------------------------------------------ */

function SafeImage({ src, alt, onClick }: { src: string; alt: string; onClick?: () => void }) {
  return (
    <div
      className={`relative w-full h-full bg-slate-900 overflow-hidden group${onClick ? " cursor-pointer" : ""}`}
      onClick={onClick}
    >
      {/* Blurred background fill */}
      <img
        src={src}
        alt=""
        className="absolute inset-0 w-full h-full object-cover opacity-40 blur-xl scale-110"
      />
      {/* Uncropped foreground */}
      <img
        src={src}
        alt={alt}
        className="relative z-10 w-full h-full object-contain drop-shadow-2xl transition-transform duration-500 group-hover:scale-[1.02]"
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Hero Gallery                                                       */
/* ------------------------------------------------------------------ */

function HeroSection({ property, onImageClick }: { property: PropertyDetail; onImageClick: (index: number) => void }) {
  const images =
    property.image_urls?.length > 0
      ? property.image_urls
      : property.image_url
      ? [property.image_url]
      : [];

  const tierBadge = property.tier === 2 ? (
    <span className="absolute top-4 left-4 z-20 inline-flex items-center gap-1 rounded-full bg-amber-600/90 backdrop-blur-sm px-3 py-1.5 text-xs font-medium text-white">
      &#9203; Check Availability
    </span>
  ) : (
    <span className="absolute top-4 left-4 z-20 inline-flex items-center gap-1 rounded-full bg-emerald-600/90 backdrop-blur-sm px-3 py-1.5 text-xs font-medium text-white">
      &#9889; Instant Book
    </span>
  );

  if (images.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-6 pt-2">
        <div className="relative h-64 md:h-80 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center">
          <span className="text-slate-400 font-medium flex items-center gap-2">
            <Camera className="h-5 w-5" /> No images available
          </span>
          {tierBadge}
        </div>
      </div>
    );
  }

  if (images.length === 1) {
    return (
      <div className="mx-auto max-w-7xl px-6 pt-2">
        <div className="relative h-64 md:h-96 rounded-2xl overflow-hidden shadow-sm">
          <SafeImage src={images[0]} alt={property.location.display} onClick={() => onImageClick(0)} />
          {tierBadge}
        </div>
      </div>
    );
  }

  if (images.length === 2) {
    return (
      <div className="mx-auto max-w-7xl px-6 pt-2">
        <div className="relative h-64 md:h-96 rounded-2xl overflow-hidden shadow-sm flex gap-2">
          <div className="w-1/2 h-full relative">
            <SafeImage src={images[0]} alt="View 1" onClick={() => onImageClick(0)} />
            {tierBadge}
          </div>
          <div className="w-1/2 h-full">
            <SafeImage src={images[1]} alt="View 2" onClick={() => onImageClick(1)} />
          </div>
        </div>
      </div>
    );
  }

  // 3+ images: Bento grid
  return (
    <div className="mx-auto max-w-7xl px-6 pt-2">
      <div className="relative h-72 md:h-[450px] rounded-2xl overflow-hidden shadow-sm flex gap-2">
        {/* Left: Hero image */}
        <div className="w-2/3 h-full relative">
          <SafeImage src={images[0]} alt={property.location.display} onClick={() => onImageClick(0)} />
          {tierBadge}
        </div>

        {/* Right: Stacked thumbnails */}
        <div className="w-1/3 h-full flex flex-col gap-2">
          <div className="w-full h-1/2">
            <SafeImage src={images[1]} alt="Secondary View" onClick={() => onImageClick(1)} />
          </div>
          <div className="relative w-full h-1/2 cursor-pointer group" onClick={() => onImageClick(2)}>
            <SafeImage src={images[2]} alt="Tertiary View" />
            {images.length > 3 && (
              <div className="absolute inset-0 z-20 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center transition-all group-hover:bg-slate-900/50">
                <span className="text-white font-bold text-lg md:text-xl flex items-center gap-2">
                  <Camera className="h-6 w-6" /> +{images.length - 3} Photos
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Premium Lightbox (Immersive Viewing Experience)                     */
/* ------------------------------------------------------------------ */

interface LightboxProps {
  images: string[];
  initialIndex?: number;
  isOpen: boolean;
  onClose: () => void;
}

function PremiumLightbox({ images, initialIndex = 0, isOpen, onClose }: LightboxProps) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);

  useEffect(() => {
    setCurrentIndex(initialIndex);
  }, [initialIndex]);

  const handleNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % images.length);
  }, [images.length]);

  const handlePrev = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);
  }, [images.length]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") handleNext();
      if (e.key === "ArrowLeft") handlePrev();
    },
    [onClose, handleNext, handlePrev]
  );

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.body.style.overflow = "auto";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen || !images || images.length === 0) return null;

  return (
    <div className="fixed inset-0 z-[100] flex flex-col bg-slate-950/95 backdrop-blur-2xl">
      {/* Header: Counter + Close */}
      <div className="flex justify-between items-center p-6 text-white absolute top-0 left-0 right-0 z-50">
        <div className="text-sm font-bold tracking-widest text-slate-300">
          {currentIndex + 1} / {images.length}
        </div>
        <button
          onClick={onClose}
          className="p-3 bg-white/10 hover:bg-white/20 rounded-full backdrop-blur-md transition-colors"
        >
          <X className="h-6 w-6 text-white" />
        </button>
      </div>

      {/* Main stage */}
      <div className="flex-1 relative flex items-center justify-center p-4 md:p-12">
        <img
          src={images[currentIndex]}
          alt={`Warehouse view ${currentIndex + 1}`}
          className="w-full h-full object-contain drop-shadow-2xl"
        />

        {/* Nav arrows (desktop) */}
        <button
          onClick={handlePrev}
          className="hidden md:flex absolute left-8 top-1/2 -translate-y-1/2 p-4 bg-white/5 hover:bg-white/20 border border-white/10 rounded-full text-white backdrop-blur-md transition-all hover:scale-110"
        >
          <ChevronLeft className="h-8 w-8" />
        </button>
        <button
          onClick={handleNext}
          className="hidden md:flex absolute right-8 top-1/2 -translate-y-1/2 p-4 bg-white/5 hover:bg-white/20 border border-white/10 rounded-full text-white backdrop-blur-md transition-all hover:scale-110"
        >
          <ChevronRight className="h-8 w-8" />
        </button>
      </div>

      {/* Filmstrip thumbnails */}
      <div className="h-24 md:h-32 w-full px-4 pb-6 flex items-center justify-center gap-2 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        {images.map((img, idx) => (
          <button
            key={idx}
            onClick={() => setCurrentIndex(idx)}
            className={`relative h-16 w-24 md:h-20 md:w-32 flex-shrink-0 rounded-lg overflow-hidden transition-all duration-300 ${
              currentIndex === idx
                ? "ring-2 ring-white opacity-100 scale-105"
                : "opacity-40 hover:opacity-70 grayscale hover:grayscale-0"
            }`}
          >
            <img src={img} alt={`Thumbnail ${idx + 1}`} className="w-full h-full object-cover" />
          </button>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Features Section                                                   */
/* ------------------------------------------------------------------ */

function FeaturesSection({ features }: { features: { key: string; label: string }[] }) {
  if (features.length === 0) return null;

  return (
    <div>
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-3">
        Features
      </h2>
      <div className="flex flex-wrap gap-2">
        {features.map((feat) => {
          const Icon = FEATURE_ICON_MAP[feat.key] || Info;
          return (
            <span
              key={feat.key}
              className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-sm text-slate-700"
            >
              <Icon className="h-3.5 w-3.5" />
              {feat.label}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Specs Section                                                      */
/* ------------------------------------------------------------------ */

function SpecsSection({ specs }: { specs: Record<string, any> }) {
  // Build ordered entries from known spec keys
  const entries: { label: string; value: string }[] = [];
  for (const [key, config] of Object.entries(SPEC_LABELS)) {
    if (key in specs) {
      const formatted = formatSpecValue(key, specs[key]);
      if (formatted !== null) {
        entries.push({ label: config.label, value: formatted });
      }
    }
  }

  if (entries.length === 0) return null;

  return (
    <div>
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-3">
        Building Specs
      </h2>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        {entries.map((entry) => (
          <div key={entry.label}>
            <dt className="text-xs text-slate-400">{entry.label}</dt>
            <dd className="mt-0.5 text-sm font-medium text-slate-800">{entry.value}</dd>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Pricing Card (Sidebar)                                             */
/* ------------------------------------------------------------------ */

interface QualifyFormState {
  sqft_needed: string;
  timing: string;
  name: string;
  phone: string;
  email: string;
}

interface PricingCardProps {
  property: PropertyDetail;
  onBookTour: () => void;
  onInstantBook: () => void;
}

const TIMING_OPTIONS = [
  { value: "asap", label: "ASAP" },
  { value: "1_month", label: "Within 1 month" },
  { value: "3_months", label: "Within 3 months" },
  { value: "6_months", label: "Within 6 months" },
];

function PricingCard({
  property,
  onBookTour,
  onInstantBook,
}: PricingCardProps) {
  const isTier1 = property.tier === 1;

  return (
    <div className="sticky top-24 rounded-xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-200/50">
      {isTier1 ? (
        <>
          {/* Tier 1 Pricing */}
          <div className="mb-5">
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-xs font-medium text-emerald-600">
              <Bolt className="h-3 w-3" />
              Tier 1 Listing
            </span>
          </div>

          {property.sqft_range && (
            <div className="mb-3">
              <p className="text-xs text-slate-400">Available Space</p>
              <p className="text-lg font-semibold text-slate-900">{property.sqft_range.display}</p>
            </div>
          )}

          {property.rate_range && (
            <div className="mb-6">
              <p className="text-xs text-slate-400">Rate</p>
              <p className="text-lg font-semibold text-emerald-600">{property.rate_range.display}</p>
            </div>
          )}

          <div className="space-y-3">
            <button
              onClick={onBookTour}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
            >
              <Calendar className="h-4 w-4" />
              Book Tour
            </button>

            {property.instant_book_eligible && (
              <button
                onClick={onInstantBook}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-600 px-4 py-3 text-sm font-semibold text-emerald-600 transition-all hover:bg-emerald-600/10 active:scale-[0.98]"
              >
                <Bolt className="h-4 w-4" />
                Instant Book
              </button>
            )}
          </div>
        </>
      ) : (
        <>
          {/* Tier 2 Pricing */}
          <div className="mb-5">
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-1 text-xs font-medium text-amber-600">
              Tier 2 Listing
            </span>
          </div>

          {property.sqft_range && (
            <div className="mb-3">
              <p className="text-xs text-slate-400">Available Space</p>
              <p className="text-lg font-semibold text-slate-900">{property.sqft_range.display}</p>
            </div>
          )}

          <div className="mb-6">
            <p className="text-xs text-slate-400">Rate</p>
            <p className="text-sm text-slate-400 italic">Available on request</p>
          </div>

          <button
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-amber-500 active:scale-[0.98]"
          >
            Check Availability
          </button>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Booking Drawer (slide-out panel)                                   */
/* ------------------------------------------------------------------ */

interface BookingDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  property: PropertyDetail;
  qualifyAction: "book_tour" | "instant_book";
  qualifyForm: QualifyFormState;
  qualifying: boolean;
  qualifyResult: any;
  qualifyError: string;
  onFormChange: (field: keyof QualifyFormState, value: string) => void;
  onSubmit: () => void;
  onReset: () => void;
}

function BookingDrawer({
  isOpen,
  onClose,
  property,
  qualifyAction,
  qualifyForm,
  qualifying,
  qualifyResult,
  qualifyError,
  onFormChange,
  onSubmit,
  onReset,
}: BookingDrawerProps) {
  // Lock body scroll when drawer is open
  React.useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-slate-900/20 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div>
                <h2 className="text-xl font-bold text-slate-900">
                  {qualifyAction === "book_tour" ? "Book a Tour" : "Instant Book"}
                </h2>
                <p className="text-sm text-slate-500 mt-1">
                  {property.location.display}
                </p>
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-slate-100 rounded-full text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Scrollable body */}
            <div className="flex-1 overflow-y-auto p-6">
              {qualifyResult ? (
                /* ---------- Result display ---------- */
                <div>
                  {qualifyResult.status === "match" ? (
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
                      <div className="flex items-start gap-3">
                        <CheckCircle className="h-5 w-5 text-emerald-500 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-sm font-semibold text-emerald-700 mb-1">Great match!</p>
                          <p className="text-sm text-slate-700">
                            We&apos;re setting up your {qualifyAction === "book_tour" ? "tour" : "booking"}.
                            {qualifyResult.message && (
                              <span className="block mt-1 text-slate-500">{qualifyResult.message}</span>
                            )}
                          </p>
                          {qualifyResult.engagement_id && (
                            <a
                              href={`/buyer/engagement/${qualifyResult.engagement_id}`}
                              className="inline-flex items-center gap-1.5 mt-4 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
                            >
                              Continue
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-sm font-semibold text-amber-700 mb-1">
                            This space might not be the best fit
                          </p>
                          <p className="text-sm text-slate-700">
                            {qualifyResult.reasons?.[0] || "Your requirements don't quite match this listing."}
                            {qualifyResult.alternatives_count > 0 && (
                              <span className="block mt-1 text-slate-500">
                                We found {qualifyResult.alternatives_count} other option{qualifyResult.alternatives_count !== 1 ? "s" : ""} that might work better.
                              </span>
                            )}
                          </p>
                          <div className="flex gap-2 mt-4">
                            <a
                              href="/buyer/options"
                              className="inline-flex items-center gap-1.5 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-amber-500 active:scale-[0.98]"
                            >
                              View Alternatives
                            </a>
                            <button
                              onClick={onReset}
                              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-all hover:bg-slate-100 active:scale-[0.98]"
                            >
                              Try Again
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                /* ---------- Qualify Form ---------- */
                <div className="space-y-5">
                  {/* Property summary so defaults feel contextual */}
                  <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-1">
                    <p className="text-sm font-semibold text-slate-900">{property.location.display}</p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                      {property.sqft_range && <span>{property.sqft_range.display} available</span>}
                      {property.rate_range && <span>{property.rate_range.display}</span>}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      How much space do you need? <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="number"
                      placeholder="e.g. 5000"
                      value={qualifyForm.sqft_needed}
                      onChange={(e) => onFormChange("sqft_needed", e.target.value)}
                      className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-3 text-sm placeholder-slate-400 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                    {property.sqft_range ? (
                      <p className="text-xs text-slate-400 mt-1">
                        sqft &middot; {property.sqft_range.display} available at this location
                      </p>
                    ) : (
                      <p className="text-xs text-slate-400 mt-1">sqft</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">When do you need it?</label>
                    <select
                      value={qualifyForm.timing}
                      onChange={(e) => onFormChange("timing", e.target.value)}
                      className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-3 text-sm focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    >
                      {TIMING_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Your name <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="Full name"
                      value={qualifyForm.name}
                      onChange={(e) => onFormChange("name", e.target.value)}
                      className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-3 text-sm placeholder-slate-400 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Phone number <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="tel"
                      placeholder="(555) 123-4567"
                      value={qualifyForm.phone}
                      onChange={(e) => onFormChange("phone", e.target.value)}
                      className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-3 text-sm placeholder-slate-400 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Email <span className="text-slate-400">(optional)</span>
                    </label>
                    <input
                      type="email"
                      placeholder="you@company.com"
                      value={qualifyForm.email}
                      onChange={(e) => onFormChange("email", e.target.value)}
                      className="w-full bg-white border border-slate-300 text-slate-900 rounded-xl px-4 py-3 text-sm placeholder-slate-400 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  {qualifyError && (
                    <p className="text-sm text-red-500">{qualifyError}</p>
                  )}
                </div>
              )}
            </div>

            {/* Sticky footer */}
            {!qualifyResult && (
              <div className="p-6 border-t border-slate-100 bg-white">
                <button
                  onClick={onSubmit}
                  disabled={qualifying}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-4 text-sm font-bold text-white shadow-lg shadow-emerald-600/20 transition-all hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {qualifying ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Checking...
                    </>
                  ) : (
                    "Confirm & Continue"
                  )}
                </button>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading Skeleton                                                   */
/* ------------------------------------------------------------------ */

function LoadingSkeleton() {
  return (
    <main className="min-h-screen bg-slate-50">
      <BrowseNavbar />
      <div className="pt-16">
        {/* Hero skeleton */}
        <div className="h-64 md:h-80 w-full bg-slate-200 animate-pulse" />

        <div className="mx-auto max-w-7xl px-6 py-8">
          {/* Back link skeleton */}
          <div className="h-4 w-32 bg-slate-200 rounded animate-pulse mb-8" />

          <div className="grid gap-8 lg:grid-cols-3">
            {/* Left column */}
            <div className="lg:col-span-2 space-y-6">
              <div className="h-8 w-48 bg-slate-200 rounded animate-pulse" />
              <div className="h-5 w-32 bg-slate-200 rounded animate-pulse" />
              <div className="flex gap-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 w-20 bg-slate-200 rounded-full animate-pulse" />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-4">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i}>
                    <div className="h-3 w-16 bg-slate-200 rounded animate-pulse mb-1" />
                    <div className="h-5 w-24 bg-slate-200 rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </div>

            {/* Right column */}
            <div>
              <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4">
                <div className="h-6 w-24 bg-slate-200 rounded-full animate-pulse" />
                <div className="h-5 w-36 bg-slate-200 rounded animate-pulse" />
                <div className="h-5 w-28 bg-slate-200 rounded animate-pulse" />
                <div className="h-12 w-full bg-slate-200 rounded-lg animate-pulse" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  404 / Error State                                                  */
/* ------------------------------------------------------------------ */

function NotFoundState() {
  return (
    <main className="min-h-screen bg-slate-50">
      <BrowseNavbar />
      <div className="flex flex-col items-center justify-center pt-32 px-6">
        <WarehouseIcon className="h-16 w-16 text-slate-300 mb-6" />
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Listing Not Found</h1>
        <p className="text-slate-500 text-sm mb-8 text-center max-w-md">
          This listing may have been removed or is no longer available. Try browsing other spaces.
        </p>
        <Link
          href="/browse"
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Browse
        </Link>
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function PropertyDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const id = params.id as string;

  const [property, setProperty] = useState<PropertyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  // Pre-fill from browse filters passed as query params
  const prefillSqft = searchParams.get("sqft") || "";
  const prefillTiming = searchParams.get("timing") || "asap";

  // Lightbox state
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  function handleImageClick(index: number) {
    setLightboxIndex(index);
    setLightboxOpen(true);
  }

  // Qualify form state
  const [showBookingDrawer, setShowBookingDrawer] = useState(false);
  const [qualifyAction, setQualifyAction] = useState<"book_tour" | "instant_book">("book_tour");
  const [qualifyForm, setQualifyForm] = useState<QualifyFormState>({
    sqft_needed: prefillSqft,
    timing: prefillTiming,
    name: "",
    phone: "",
    email: "",
  });
  const [qualifying, setQualifying] = useState(false);
  const [qualifyResult, setQualifyResult] = useState<any>(null);
  const [qualifyError, setQualifyError] = useState("");

  // Smart-default sqft from the property's min when no filter was provided
  useEffect(() => {
    if (property && !prefillSqft && property.sqft_range) {
      setQualifyForm((prev) => ({
        ...prev,
        sqft_needed: prev.sqft_needed || String(property.sqft_range!.min),
      }));
    }
  }, [property, prefillSqft]);

  function handleFormChange(field: keyof QualifyFormState, value: string) {
    setQualifyForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleBookTour() {
    setQualifyAction("book_tour");
    setShowBookingDrawer(true);
    setQualifyResult(null);
    setQualifyError("");
  }

  function handleInstantBook() {
    setQualifyAction("instant_book");
    setShowBookingDrawer(true);
    setQualifyResult(null);
    setQualifyError("");
  }

  async function handleQualify() {
    if (!qualifyForm.sqft_needed || !qualifyForm.name || !qualifyForm.phone) {
      setQualifyError("Please fill in all required fields");
      return;
    }
    if (!property) return;
    setQualifying(true);
    setQualifyError("");
    try {
      const result = await api.browseQualify(property.id, {
        sqft_needed: parseInt(qualifyForm.sqft_needed),
        timing: qualifyForm.timing,
        name: qualifyForm.name,
        phone: qualifyForm.phone,
        email: qualifyForm.email || undefined,
        action: qualifyAction,
      });
      setQualifyResult(result);
    } catch (err) {
      setQualifyError("Something went wrong. Please try again.");
    } finally {
      setQualifying(false);
    }
  }

  function handleQualifyReset() {
    setQualifyResult(null);
    setQualifyError("");
  }

  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setNotFound(false);
      try {
        const data = await api.browseListingDetail(id);
        if (!cancelled) {
          setProperty(data);
        }
      } catch (err) {
        console.error("Failed to fetch property detail:", err);
        if (!cancelled) {
          setNotFound(true);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (notFound || !property) {
    return <NotFoundState />;
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <BrowseNavbar />

      {/* Spacer for fixed navbar */}
      <div className="pt-16">
        {/* Back bar */}
        <div className="mx-auto max-w-7xl px-6 pt-6 pb-2">
          <Link
            href="/browse"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Browse Spaces
          </Link>
        </div>

        {/* Hero */}
        <HeroSection property={property} onImageClick={handleImageClick} />

        {/* Content */}
        <div className="mx-auto max-w-7xl px-6 py-8">

          <div className="grid gap-8 lg:grid-cols-3">
            {/* Left Column (2/3) */}
            <div className="lg:col-span-2 space-y-8">
              {/* Location + Type */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <MapPin className="h-5 w-5 text-emerald-500 shrink-0" />
                  <h1 className="text-3xl font-bold text-slate-900 md:text-4xl">
                    {property.location.display}
                  </h1>
                </div>
                <p className="text-slate-500 text-base ml-7">
                  {property.building_type}
                </p>
              </div>

              {/* Features */}
              <FeaturesSection features={property.features} />

              {/* Specs */}
              <SpecsSection specs={property.specs} />

              {/* Approximate Location Map */}
              {property.approximate_location && (
                <ApproximateLocationMap
                  lat={property.approximate_location.lat}
                  lng={property.approximate_location.lng}
                  label={property.location.display}
                />
              )}
            </div>

            {/* Right Column (1/3) */}
            <div>
              <PricingCard
                property={property}
                onBookTour={handleBookTour}
                onInstantBook={handleInstantBook}
              />
            </div>
          </div>
        </div>

        <BookingDrawer
          isOpen={showBookingDrawer}
          onClose={() => {
            setShowBookingDrawer(false);
            setQualifyResult(null);
            setQualifyError("");
          }}
          property={property}
          qualifyAction={qualifyAction}
          qualifyForm={qualifyForm}
          qualifying={qualifying}
          qualifyResult={qualifyResult}
          qualifyError={qualifyError}
          onFormChange={handleFormChange}
          onSubmit={handleQualify}
          onReset={handleQualifyReset}
        />

        {/* Lightbox */}
        <PremiumLightbox
          images={
            property.image_urls?.length > 0
              ? property.image_urls
              : property.image_url
              ? [property.image_url]
              : []
          }
          initialIndex={lightboxIndex}
          isOpen={lightboxOpen}
          onClose={() => setLightboxOpen(false)}
        />
      </div>
    </main>
  );
}
