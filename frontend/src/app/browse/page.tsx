"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  MapPin,
  Warehouse as WarehouseIcon,
  X,
  Truck,
  Building2,
  Zap,
  Clock,
  ParkingSquare,
  Loader2,
  ArrowRight,
  Menu,
  RotateCcw,
  Calendar,
  Infinity,
  SlidersHorizontal,
  Ruler,
  Box,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ListingFeature {
  key: string;
  label: string;
}

interface Listing {
  id: string;
  tier: 1 | 2;
  location: {
    city: string;
    state: string;
    display: string;
  };
  sqft_range: {
    min: number;
    max: number;
    display: string;
  } | null;
  rate_range: {
    min: number;
    max: number;
    display: string;
  } | null;
  building_type: string;
  features: ListingFeature[];
  has_image: boolean;
  image_url?: string | null;
}

interface BrowseResponse {
  listings: Listing[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

interface LocationSuggestion {
  city: string;
  state: string;
  display: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const USE_TYPE_OPTIONS = [
  { label: "Storage", value: "storage" },
  { label: "Light Ops", value: "light_ops" },
  { label: "Distribution", value: "distribution" },
];

const MUST_HAVE_OPTIONS = [
  { key: "office", label: "Office Space", icon: Building2 },
  { key: "dock", label: "Dock Doors", icon: Truck },
  { key: "power", label: "High Power", icon: Zap },
  { key: "24_7", label: "24/7 Access", icon: Clock },
  { key: "parking", label: "Parking", icon: ParkingSquare },
];

const FEATURE_ICON_MAP: Record<string, typeof Truck> = {
  dock: Truck,
  office: Building2,
  power: Zap,
  "24_7": Clock,
  parking: ParkingSquare,
};

const PER_PAGE = 12;

/* ------------------------------------------------------------------ */
/*  Navbar (reused from homepage pattern)                              */
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
/*  Command Pill (Primary Filters)                                     */
/* ------------------------------------------------------------------ */

interface CommandPillProps {
  location: string;
  sqft: string;
  setSqft: (v: string) => void;
  useType: string;
  setUseType: (v: string) => void;
  onSearch: () => void;
  onOpenFilters: () => void;
  hasSecondaryFilters: boolean;
  locationSuggestions: LocationSuggestion[];
  showSuggestions: boolean;
  setShowSuggestions: (v: boolean) => void;
  onLocationInput: (v: string) => void;
  onSelectLocation: (loc: LocationSuggestion) => void;
  total: number;
  showingCount: number;
}

function CommandPill({
  location,
  sqft,
  setSqft,
  useType,
  setUseType,
  onSearch,
  onOpenFilters,
  hasSecondaryFilters,
  locationSuggestions,
  showSuggestions,
  setShowSuggestions,
  onLocationInput,
  onSelectLocation,
  total,
  showingCount,
}: CommandPillProps) {
  const locationRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (locationRef.current && !locationRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [setShowSuggestions]);

  return (
    <div className="w-full bg-slate-50 border-b border-slate-200 py-6 sticky top-[73px] z-40">
      <div className="max-w-7xl mx-auto px-6">
        {/* THE COMMAND PILL */}
        <div className="flex flex-col md:flex-row items-center bg-white border border-slate-200 shadow-md rounded-2xl md:rounded-full overflow-visible transition-all focus-within:shadow-lg focus-within:border-emerald-300">
          {/* 1. Location */}
          <div className="relative flex-1 w-full" ref={locationRef}>
            <div className="flex items-center px-6 py-4 md:py-3.5 border-b md:border-b-0 md:border-r border-slate-200 hover:bg-slate-50 transition-colors md:rounded-l-full">
              <MapPin size={18} className="text-emerald-600 mr-3 flex-shrink-0" />
              <div className="flex-1">
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Location</label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => onLocationInput(e.target.value)}
                  onFocus={() => {
                    if (locationSuggestions.length > 0) setShowSuggestions(true);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      setShowSuggestions(false);
                      onSearch();
                    }
                  }}
                  placeholder="e.g. Carson, CA"
                  className="w-full bg-transparent outline-none text-slate-900 font-medium placeholder-slate-300 text-sm"
                />
              </div>
            </div>

            {/* Location autocomplete dropdown */}
            <AnimatePresence>
              {showSuggestions && locationSuggestions.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="absolute z-50 mt-1 left-0 right-0 rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden"
                >
                  {locationSuggestions.map((loc) => (
                    <button
                      key={`${loc.city}-${loc.state}`}
                      onClick={() => onSelectLocation(loc)}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
                    >
                      <MapPin className="h-3.5 w-3.5 text-slate-400" />
                      {loc.display}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* 2. Size */}
          <div className="flex-1 w-full flex items-center px-6 py-4 md:py-3.5 border-b md:border-b-0 md:border-r border-slate-200 hover:bg-slate-50 transition-colors">
            <Ruler size={18} className="text-emerald-600 mr-3 flex-shrink-0" />
            <div className="flex-1">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Size (Sqft)</label>
              <input
                type="number"
                value={sqft}
                onChange={(e) => setSqft(e.target.value)}
                min={500}
                step={500}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSearch();
                }}
                placeholder="5,000"
                className="w-full bg-transparent outline-none text-slate-900 font-medium placeholder-slate-300 text-sm"
              />
            </div>
          </div>

          {/* 3. Use Type */}
          <div className="flex-1 w-full flex items-center px-6 py-4 md:py-3.5 hover:bg-slate-50 transition-colors">
            <Box size={18} className="text-emerald-600 mr-3 flex-shrink-0" />
            <div className="flex-1">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Use Type</label>
              <select
                value={useType}
                onChange={(e) => setUseType(e.target.value)}
                className="w-full bg-transparent outline-none text-slate-900 font-medium appearance-none cursor-pointer text-sm"
              >
                <option value="any">Any</option>
                {USE_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* 4. Actions */}
          <div className="w-full md:w-auto flex items-center p-2 gap-2 bg-slate-50 md:bg-white border-t md:border-t-0 border-slate-200 md:border-none md:rounded-r-full">
            <button
              onClick={onOpenFilters}
              className={`flex-1 md:flex-none flex items-center justify-center gap-2 bg-white md:bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-3 rounded-xl md:rounded-full font-bold text-sm transition-colors border border-slate-200 md:border-none relative ${
                hasSecondaryFilters ? "ring-2 ring-emerald-500 ring-offset-1" : ""
              }`}
            >
              <SlidersHorizontal size={16} />
              <span className="md:hidden">More Filters</span>
              {hasSecondaryFilters && (
                <span className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full md:block hidden" />
              )}
            </button>

            <button
              onClick={onSearch}
              className="flex-1 md:flex-none flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3 rounded-xl md:rounded-full font-bold text-sm shadow-md shadow-emerald-600/20 transition-all active:scale-[0.98]"
            >
              <Search size={16} /> Search
            </button>
          </div>
        </div>

        {/* Results count */}
        {total > 0 && (
          <div className="mt-5 text-sm font-medium text-slate-500">
            Showing {showingCount} of {total} space{total !== 1 ? "s" : ""}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Filter Drawer (Secondary Filters)                                  */
/* ------------------------------------------------------------------ */

interface FilterDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  timing: string;
  setTiming: (v: string) => void;
  isImmediate: boolean;
  setIsImmediate: (v: boolean) => void;
  durationMonths: number;
  setDurationMonths: (v: number) => void;
  isFlexible: boolean;
  setIsFlexible: (v: boolean) => void;
  selectedFeatures: string[];
  toggleFeature: (key: string) => void;
  onClear: () => void;
  onApply: () => void;
}

function FilterDrawer({
  isOpen,
  onClose,
  timing,
  setTiming,
  isImmediate,
  setIsImmediate,
  durationMonths,
  setDurationMonths,
  isFlexible,
  setIsFlexible,
  selectedFeatures,
  toggleFeature,
  onClear,
  onApply,
}: FilterDrawerProps) {
  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-slate-900/20 backdrop-blur-sm"
          />

          {/* Drawer */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-white shadow-2xl flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100">
              <h2 className="text-lg font-bold text-slate-900">More Filters</h2>
              <button
                onClick={onClose}
                className="p-2 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8">
              {/* Move-in Date */}
              <div>
                <label className="mb-3 block text-xs font-bold text-slate-400 uppercase tracking-widest">
                  <Calendar className="inline h-3.5 w-3.5 mr-1.5 -mt-0.5" /> Move-in Date
                </label>
                <div className="space-y-2">
                  <button
                    onClick={() => {
                      setIsImmediate(true);
                      setTiming("Immediately");
                    }}
                    className={`w-full flex items-center justify-between p-3 rounded-xl border-2 transition-all text-sm ${
                      isImmediate
                        ? "border-emerald-500 bg-emerald-50 text-emerald-600"
                        : "border-slate-200 bg-white text-slate-500 hover:border-slate-400"
                    }`}
                  >
                    <span className="font-bold flex items-center gap-2">
                      <Zap size={14} /> Immediately
                    </span>
                    {isImmediate && <div className="w-2 h-2 bg-emerald-500 rounded-full" />}
                  </button>
                  <div className={`relative p-3 rounded-xl border-2 transition-all ${
                    !isImmediate && timing
                      ? "border-emerald-500 bg-white"
                      : "border-slate-200 bg-white"
                  }`}>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">
                      Or select a date
                    </label>
                    <input
                      type="date"
                      value={!isImmediate ? timing : ""}
                      min={new Date().toISOString().split("T")[0]}
                      onChange={(e) => {
                        setIsImmediate(false);
                        setTiming(e.target.value);
                      }}
                      className="w-full bg-transparent font-bold text-sm text-slate-900 outline-none cursor-pointer"
                    />
                  </div>
                </div>
              </div>

              {/* Term Length */}
              <div>
                <label className="mb-3 block text-xs font-bold text-slate-400 uppercase tracking-widest">
                  <Clock className="inline h-3.5 w-3.5 mr-1.5 -mt-0.5" /> Term Length
                </label>
                <div className={`bg-slate-50 rounded-xl border-2 p-5 text-center transition-all ${
                  isFlexible ? "border-slate-200 opacity-60" : "border-emerald-500"
                }`}>
                  <div className="text-3xl font-bold text-slate-900 mb-3">
                    {isFlexible ? (
                      <span className="text-slate-400">Flexible</span>
                    ) : (
                      <>
                        {durationMonths}{" "}
                        <span className="text-sm text-slate-500 font-medium">
                          {durationMonths === 1 ? "Month" : "Months"}
                        </span>
                      </>
                    )}
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="36"
                    value={durationMonths}
                    onChange={(e) => {
                      setDurationMonths(parseInt(e.target.value));
                      setIsFlexible(false);
                    }}
                    disabled={isFlexible}
                    className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400 font-bold mt-1">
                    <span>1</span><span>12</span><span>24</span><span>36</span>
                  </div>
                </div>
                <button
                  onClick={() => setIsFlexible(!isFlexible)}
                  className={`mt-3 w-full flex items-center justify-center gap-2 p-2.5 rounded-xl border-2 font-bold text-xs transition-all ${
                    isFlexible
                      ? "bg-slate-800 text-white border-slate-800"
                      : "bg-white text-slate-500 border-slate-200 hover:border-slate-400"
                  }`}
                >
                  <Infinity size={14} /> I&apos;m Flexible
                </button>
              </div>

              {/* Must-Haves */}
              <div>
                <label className="mb-3 block text-xs font-bold text-slate-400 uppercase tracking-widest">
                  Must-Haves
                </label>
                <div className="flex flex-wrap gap-2">
                  {MUST_HAVE_OPTIONS.map(({ key, label, icon: Icon }) => {
                    const active = selectedFeatures.includes(key);
                    return (
                      <button
                        key={key}
                        onClick={() => toggleFeature(key)}
                        className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-all ${
                          active
                            ? "bg-emerald-600 text-white border border-emerald-500"
                            : "bg-slate-100 text-slate-600 border border-slate-200 hover:border-slate-400 hover:text-slate-700"
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button
                onClick={onClear}
                className="flex-1 flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition-all hover:bg-slate-50"
              >
                <RotateCcw className="h-4 w-4" />
                Clear All
              </button>
              <button
                onClick={() => {
                  onApply();
                  onClose();
                }}
                className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
              >
                Apply Filters
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/* ------------------------------------------------------------------ */
/*  Listing Card                                                       */
/* ------------------------------------------------------------------ */

interface ListingCardProps {
  listing: Listing;
  index: number;
  onClick: () => void;
}

function ListingCard({ listing, index, onClick }: ListingCardProps) {
  const isTier2 = listing.tier === 2;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3) }}
      onClick={onClick}
      className={`group cursor-pointer overflow-hidden rounded-xl border bg-white transition-all hover:shadow-lg ${
        isTier2
          ? "border-slate-200/80 opacity-85 hover:opacity-100 hover:border-slate-300 hover:shadow-amber-200/20"
          : "border-slate-200 hover:border-slate-300 hover:shadow-emerald-200/20"
      }`}
    >
      {/* Property image or gradient placeholder */}
      <div className="relative h-40 bg-gradient-to-br from-slate-100 to-slate-200 flex items-center justify-center overflow-hidden">
        {listing.image_url ? (
          <img
            src={listing.image_url}
            alt={listing.location.display}
            className="absolute inset-0 h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <MapPin className="h-10 w-10 text-slate-400 group-hover:text-slate-500 transition-colors" />
        )}
        {/* Tier badge — top left */}
        {isTier2 ? (
          <span className="absolute top-3 left-3 inline-flex items-center gap-1 rounded-full bg-amber-600/90 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-white">
            &#9203; Check Availability
          </span>
        ) : (
          <span className="absolute top-3 left-3 inline-flex items-center gap-1 rounded-full bg-emerald-600/90 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-white">
            &#9889; Instant Book
          </span>
        )}
      </div>

      <div className="p-5">
        {/* City / neighborhood */}
        <div className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-emerald-500 shrink-0" />
          <h3 className="text-lg font-semibold text-slate-900 truncate">
            {listing.location.display}
          </h3>
        </div>

        {/* Sqft range + Rate range */}
        <div className="mt-3 space-y-1.5 text-sm">
          {listing.sqft_range ? (
            <p className="text-slate-600">{listing.sqft_range.display}</p>
          ) : null}
          {isTier2 ? (
            <p className="text-slate-400 italic">Rate available on request</p>
          ) : listing.rate_range ? (
            <p className="text-emerald-600 font-medium">{listing.rate_range.display}</p>
          ) : null}
        </div>

        {/* Feature pills */}
        {listing.features.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {listing.features.map((feat) => {
              const Icon = FEATURE_ICON_MAP[feat.key] || MapPin;
              return (
                <span
                  key={feat.key}
                  className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                >
                  <Icon className="h-3 w-3" />
                  {feat.label}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Interest Modal                                                     */
/* ------------------------------------------------------------------ */

interface InterestModalProps {
  listing: Listing;
  onClose: () => void;
  hasExistingSearch: boolean;
}

function InterestModal({ listing, onClose, hasExistingSearch }: InterestModalProps) {
  const router = useRouter();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Location badge */}
        <div className="mb-4 flex items-center gap-2 text-emerald-500">
          <MapPin className="h-5 w-5" />
          <span className="font-medium">{listing.location.display}</span>
        </div>

        <h2 className="text-xl font-bold text-slate-900">
          Interested in this space?
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Tell us what you need and we&apos;ll check availability.
        </p>

        {/* Space details */}
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
          {listing.sqft_range && (
            <div className="flex justify-between text-sm">
              <span className="text-slate-500">Available Space</span>
              <span className="text-slate-900 font-medium">{listing.sqft_range.display}</span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Rate</span>
            {listing.rate_range ? (
              <span className="text-emerald-600 font-medium">{listing.rate_range.display}</span>
            ) : (
              <span className="text-slate-400 italic">On request</span>
            )}
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Type</span>
            <span className="text-slate-900">{listing.building_type}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-6 space-y-3">
          <button
            onClick={() => router.push("/buyer")}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
          >
            Start My Search
            <ArrowRight className="h-4 w-4" />
          </button>

          {hasExistingSearch && (
            <button
              onClick={() => {
                // In a full implementation, this would call the API to add to matches
                onClose();
              }}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition-all hover:border-slate-400 hover:text-slate-900"
            >
              Add to My Matches
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tier 2 Interest Modal                                              */
/* ------------------------------------------------------------------ */

interface Tier2InterestModalProps {
  listing: Listing;
  onClose: () => void;
}

function Tier2InterestModal({ listing, onClose }: Tier2InterestModalProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!name.trim() || !email.trim() || !phone.trim()) {
      setError("Please fill in all required fields.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      await api.browseListingInterest(listing.id, {
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim(),
        note: note.trim() || undefined,
      });
      setSubmitted(true);
    } catch (err) {
      console.error("Failed to submit interest:", err);
      setError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Location badge */}
        <div className="mb-4 flex items-center gap-2 text-amber-400">
          <MapPin className="h-5 w-5" />
          <span className="font-medium">{listing.location.display}</span>
        </div>

        {submitted ? (
          <div className="py-6 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 border border-emerald-200">
              <ArrowRight className="h-6 w-6 text-emerald-400" />
            </div>
            <h2 className="text-xl font-bold text-slate-900">Request Sent</h2>
            <p className="mt-2 text-sm text-slate-500">
              We&apos;ll check availability and get back to you shortly.
            </p>
            <button
              onClick={onClose}
              className="mt-6 inline-flex items-center justify-center rounded-lg bg-slate-100 px-6 py-2.5 text-sm font-medium text-slate-700 transition-all hover:bg-slate-200 hover:text-slate-900"
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <h2 className="text-xl font-bold text-slate-900">
              Check Availability
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Leave your details and we&apos;ll confirm availability and pricing for this space.
            </p>

            {/* Form */}
            <div className="mt-5 space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your full name"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Email <span className="text-red-400">*</span>
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Phone <span className="text-red-400">*</span>
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="(555) 123-4567"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">
                  Note <span className="text-slate-400">(optional)</span>
                </label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Any details about your needs..."
                  rows={3}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors resize-none"
                />
              </div>
            </div>

            {error && (
              <p className="mt-3 text-sm text-red-400">{error}</p>
            )}

            {/* Submit */}
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-amber-500 active:scale-[0.98] disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  Check Availability
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </>
        )}
      </motion.div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function BrowsePage() {
  const router = useRouter();
  const [listings, setListings] = useState<Listing[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // Filters
  const [location, setLocation] = useState("");
  const [sqft, setSqft] = useState("");
  const [useType, setUseType] = useState("any");
  const [timing, setTiming] = useState("");
  const [isImmediate, setIsImmediate] = useState(false);
  const [durationMonths, setDurationMonths] = useState(6);
  const [isFlexible, setIsFlexible] = useState(true);
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);

  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false);

  const hasActiveFilters = !!(location || sqft || useType !== "any" || timing || isImmediate || !isFlexible || selectedFeatures.length > 0);
  const hasSecondaryFilters = !!(timing || isImmediate || !isFlexible || selectedFeatures.length > 0);

  const clearAllFilters = useCallback(() => {
    setLocation("");
    setSqft("");
    setUseType("any");
    setTiming("");
    setIsImmediate(false);
    setDurationMonths(6);
    setIsFlexible(true);
    setSelectedFeatures([]);
  }, []);

  // Location autocomplete
  const [locationSuggestions, setLocationSuggestions] = useState<LocationSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Modal
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null);
  const [hasExistingSearch, setHasExistingSearch] = useState(false);

  // Check localStorage for existing buyer search
  useEffect(() => {
    try {
      const buyerId = localStorage.getItem("wex_buyer_id");
      setHasExistingSearch(!!buyerId);
    } catch {
      // localStorage not available
    }
  }, []);

  // Build query params from filters
  const buildParams = useCallback(() => {
    const params: Record<string, string | number> = {};
    if (location) params.city = location;
    if (sqft) {
      const val = parseInt(sqft);
      if (val > 0) params.min_sqft = val;
    }
    if (useType && useType !== "any") params.use_type = useType;
    if (selectedFeatures.length > 0) params.features = selectedFeatures.join(",");
    return params;
  }, [location, sqft, useType, selectedFeatures]);

  // Fetch listings
  const fetchListings = useCallback(
    async (pageNum: number, append: boolean = false) => {
      try {
        if (append) {
          setLoadingMore(true);
        } else {
          setLoading(true);
        }

        const params = buildParams();
        const data: BrowseResponse = await api.browseListings({
          ...params,
          page: pageNum,
          per_page: PER_PAGE,
        } as any);

        if (append) {
          setListings((prev) => [...prev, ...data.listings]);
        } else {
          setListings(data.listings);
        }
        setTotal(data.total);
        setPage(pageNum);
      } catch (err) {
        console.error("Failed to fetch listings:", err);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [buildParams]
  );

  // Initial load
  useEffect(() => {
    fetchListings(1);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Search triggered by filter changes
  const handleSearch = useCallback(() => {
    fetchListings(1);
  }, [fetchListings]);

  // Auto-search on filter changes (debounced)
  useEffect(() => {
    // Skip initial render
    const timer = setTimeout(() => {
      fetchListings(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [sqft, useType, timing, isImmediate, durationMonths, isFlexible, selectedFeatures]); // eslint-disable-line react-hooks/exhaustive-deps

  // Location autocomplete
  const handleLocationInput = useCallback(
    (value: string) => {
      setLocation(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (value.length < 2) {
        setLocationSuggestions([]);
        setShowSuggestions(false);
        return;
      }
      debounceRef.current = setTimeout(async () => {
        try {
          const data = await api.browseLocations(value);
          setLocationSuggestions(data.locations || []);
          setShowSuggestions(true);
        } catch {
          setLocationSuggestions([]);
        }
      }, 250);
    },
    []
  );

  const handleSelectLocation = useCallback(
    (loc: LocationSuggestion) => {
      setLocation(loc.display);
      setShowSuggestions(false);
      // Trigger search with the selected city
      setTimeout(() => fetchListings(1), 100);
    },
    [fetchListings]
  );

  const toggleFeature = useCallback((key: string) => {
    setSelectedFeatures((prev) =>
      prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key]
    );
  }, []);

  const handleLoadMore = useCallback(() => {
    fetchListings(page + 1, true);
  }, [fetchListings, page]);

  const showingCount = listings.length;
  const hasMore = showingCount < total;

  return (
    <main className="min-h-screen bg-slate-50">
      <BrowseNavbar />

      {/* Header */}
      <div className="pt-24 pb-2 px-6">
        <div className="mx-auto max-w-7xl">
          <h1 className="text-3xl font-bold text-slate-900 sm:text-4xl">
            Browse Spaces
          </h1>
          <p className="mt-2 text-slate-600 text-sm sm:text-base">
            Explore in-network warehouse spaces available through WEx.
          </p>
        </div>
      </div>

      {/* Command Pill */}
      <CommandPill
        location={location}
        sqft={sqft}
        setSqft={setSqft}
        useType={useType}
        setUseType={setUseType}
        onSearch={handleSearch}
        onOpenFilters={() => setFilterDrawerOpen(true)}
        hasSecondaryFilters={hasSecondaryFilters}
        locationSuggestions={locationSuggestions}
        showSuggestions={showSuggestions}
        setShowSuggestions={setShowSuggestions}
        onLocationInput={handleLocationInput}
        onSelectLocation={handleSelectLocation}
        total={total}
        showingCount={showingCount}
      />

      {/* Grid */}
      <div className="px-6 pb-16 pt-6">
        <div className="mx-auto max-w-7xl">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24">
              <Loader2 className="h-8 w-8 text-emerald-500 animate-spin" />
              <p className="mt-4 text-sm text-slate-500">Loading spaces...</p>
            </div>
          ) : listings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <WarehouseIcon className="h-12 w-12 text-slate-300" />
              <h3 className="mt-4 text-lg font-semibold text-slate-700">
                No spaces found
              </h3>
              <p className="mt-2 text-sm text-slate-500 text-center max-w-md">
                Try adjusting your filters or search for a different location.
              </p>
            </div>
          ) : (
            <>
              {/* Grid */}
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {listings.map((listing, i) => (
                  <ListingCard
                    key={listing.id}
                    listing={listing}
                    index={i}
                    onClick={() => {
                      const params = new URLSearchParams();
                      if (sqft) params.set("sqft", sqft);
                      if (isImmediate) params.set("timing", "asap");
                      else if (timing) params.set("timing", timing);
                      if (!isFlexible) params.set("duration", String(durationMonths));
                      const qs = params.toString();
                      router.push(`/browse/${listing.id}${qs ? `?${qs}` : ""}`);
                    }}
                  />
                ))}
              </div>

              {/* Load More */}
              {hasMore && (
                <div className="mt-10 flex justify-center">
                  <button
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-3 text-sm font-medium text-slate-700 transition-all hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
                  >
                    {loadingMore ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Loading...
                      </>
                    ) : (
                      "Load More"
                    )}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Filter Drawer */}
      <FilterDrawer
        isOpen={filterDrawerOpen}
        onClose={() => setFilterDrawerOpen(false)}
        timing={timing}
        setTiming={setTiming}
        isImmediate={isImmediate}
        setIsImmediate={setIsImmediate}
        durationMonths={durationMonths}
        setDurationMonths={setDurationMonths}
        isFlexible={isFlexible}
        setIsFlexible={setIsFlexible}
        selectedFeatures={selectedFeatures}
        toggleFeature={toggleFeature}
        onClear={clearAllFilters}
        onApply={handleSearch}
      />

      {/* Interest Modal */}
      <AnimatePresence>
        {selectedListing && (
          <InterestModal
            listing={selectedListing}
            onClose={() => setSelectedListing(null)}
            hasExistingSearch={hasExistingSearch}
          />
        )}
      </AnimatePresence>
    </main>
  );
}
