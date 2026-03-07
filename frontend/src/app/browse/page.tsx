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
          ? "bg-gray-950/90 backdrop-blur-md border-b border-gray-800/50 shadow-lg shadow-black/10"
          : "bg-gray-950 border-b border-gray-800/30"
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2">
          <WarehouseIcon className="h-6 w-6 text-blue-400" />
          <span className="text-lg font-bold text-white">WEx</span>
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          <Link
            href="/browse"
            className="text-sm font-medium text-white"
          >
            Browse Spaces
          </Link>
          <Link
            href="/supplier/earncheck?intent=onboard"
            className="text-sm text-gray-300 hover:text-white transition-colors"
          >
            List Your Space
          </Link>
          <Link
            href="/buyer"
            className="inline-flex h-9 items-center justify-center rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white transition-all hover:bg-blue-500 active:scale-[0.98]"
          >
            Find Space
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="text-gray-300 hover:text-white md:hidden"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-gray-800 bg-gray-950/95 backdrop-blur-md px-6 py-6 md:hidden">
          <div className="flex flex-col gap-4">
            <Link href="/browse" onClick={() => setMobileOpen(false)} className="text-sm font-medium text-white">
              Browse Spaces
            </Link>
            <Link href="/supplier/earncheck?intent=onboard" onClick={() => setMobileOpen(false)} className="text-sm text-gray-300 hover:text-white transition-colors">
              List Your Space
            </Link>
            <Link href="/buyer" onClick={() => setMobileOpen(false)} className="inline-flex h-10 items-center justify-center rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white transition-all hover:bg-blue-500">
              Find Space
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/*  Filter Bar                                                         */
/* ------------------------------------------------------------------ */

interface FilterBarProps {
  location: string;
  sqft: string;
  setSqft: (v: string) => void;
  useType: string;
  setUseType: (v: string) => void;
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
  onSearch: () => void;
  onClear: () => void;
  hasActiveFilters: boolean;
  locationSuggestions: LocationSuggestion[];
  showSuggestions: boolean;
  setShowSuggestions: (v: boolean) => void;
  onLocationInput: (v: string) => void;
  onSelectLocation: (loc: LocationSuggestion) => void;
}

function FilterBar({
  location,
  sqft,
  setSqft,
  useType,
  setUseType,
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
  onSearch,
  onClear,
  hasActiveFilters,
  locationSuggestions,
  showSuggestions,
  setShowSuggestions,
  onLocationInput,
  onSelectLocation,
}: FilterBarProps) {
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
    <div className="rounded-xl border border-gray-800 bg-gray-900/80 backdrop-blur-sm p-4 md:p-6 space-y-5">
      {/* Row 1: Location + Size (sqft) */}
      <div className="grid gap-3 md:grid-cols-2">
        {/* Location with autocomplete */}
        <div className="relative" ref={locationRef}>
          <label className="mb-1.5 block text-xs font-bold text-gray-400 uppercase tracking-widest">
            <MapPin className="inline h-3 w-3 mr-1 -mt-0.5" /> Location
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
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
              className="w-full rounded-lg border border-gray-700 bg-gray-800 py-2.5 pl-10 pr-3 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>
          <AnimatePresence>
            {showSuggestions && locationSuggestions.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="absolute z-20 mt-1 w-full rounded-lg border border-gray-700 bg-gray-800 shadow-xl overflow-hidden"
              >
                {locationSuggestions.map((loc) => (
                  <button
                    key={`${loc.city}-${loc.state}`}
                    onClick={() => onSelectLocation(loc)}
                    className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                  >
                    <MapPin className="h-3.5 w-3.5 text-gray-500" />
                    {loc.display}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Size (sqft number input) */}
        <div>
          <label className="mb-1.5 block text-xs font-bold text-gray-400 uppercase tracking-widest">
            <WarehouseIcon className="inline h-3 w-3 mr-1 -mt-0.5" /> Size (sqft)
          </label>
          <input
            type="number"
            value={sqft}
            onChange={(e) => setSqft(e.target.value)}
            min={500}
            step={500}
            placeholder="e.g. 5000"
            className="w-full rounded-lg border border-gray-700 bg-gray-800 py-2.5 px-3 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
          />
        </div>
      </div>

      {/* Row 2: Use Type (3 button tabs) */}
      <div>
        <label className="mb-1.5 block text-xs font-bold text-gray-400 uppercase tracking-widest">
          Use Type
        </label>
        <div className="flex gap-2">
          {USE_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setUseType(useType === opt.value ? "any" : opt.value)}
              className={`flex-1 rounded-lg border-2 py-2 text-sm font-bold transition-all ${
                useType === opt.value
                  ? "border-blue-500 bg-blue-950/50 text-blue-400"
                  : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Row 3: Move-in Date + Term Length */}
      <div className="grid gap-3 md:grid-cols-2">
        {/* Move-in Date */}
        <div>
          <label className="mb-1.5 block text-xs font-bold text-gray-400 uppercase tracking-widest">
            <Calendar className="inline h-3 w-3 mr-1 -mt-0.5" /> Move-in Date
          </label>
          <div className="space-y-2">
            <button
              onClick={() => {
                setIsImmediate(true);
                setTiming("Immediately");
              }}
              className={`w-full flex items-center justify-between p-2.5 rounded-lg border-2 transition-all text-sm ${
                isImmediate
                  ? "border-blue-500 bg-blue-950/50 text-blue-400"
                  : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
              }`}
            >
              <span className="font-bold flex items-center gap-2">
                <Zap size={14} /> Immediately
              </span>
              {isImmediate && <div className="w-2 h-2 bg-blue-500 rounded-full" />}
            </button>
            <div className={`relative p-2.5 rounded-lg border-2 transition-all ${
              !isImmediate && timing
                ? "border-blue-500 bg-gray-800"
                : "border-gray-700 bg-gray-800"
            }`}>
              <label className="block text-[10px] font-bold text-gray-500 uppercase mb-1">
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
                className="w-full bg-transparent font-bold text-sm text-white outline-none cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Term Length */}
        <div>
          <label className="mb-1.5 block text-xs font-bold text-gray-400 uppercase tracking-widest">
            <Clock className="inline h-3 w-3 mr-1 -mt-0.5" /> Term Length
          </label>
          <div className={`bg-gray-800 rounded-lg border-2 p-4 text-center transition-all ${
            isFlexible ? "border-gray-700 opacity-60" : "border-blue-500"
          }`}>
            <div className="text-2xl font-bold text-white mb-2">
              {isFlexible ? (
                <span className="text-gray-500">Flexible</span>
              ) : (
                <>
                  {durationMonths}{" "}
                  <span className="text-sm text-gray-400 font-medium">
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
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
            <div className="flex justify-between text-[10px] text-gray-500 font-bold mt-1">
              <span>1</span><span>12</span><span>24</span><span>36</span>
            </div>
          </div>
          <button
            onClick={() => setIsFlexible(!isFlexible)}
            className={`mt-2 w-full flex items-center justify-center gap-2 p-2 rounded-lg border-2 font-bold text-xs transition-all ${
              isFlexible
                ? "bg-gray-700 text-white border-gray-600"
                : "bg-gray-800 text-gray-500 border-gray-700 hover:border-gray-600"
            }`}
          >
            <Infinity size={14} /> I&apos;m Flexible
          </button>
        </div>
      </div>

      {/* Row 4: Must-Haves + Clear All */}
      <div>
        <label className="mb-2 block text-xs font-bold text-gray-400 uppercase tracking-widest">
          Must-Haves
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {MUST_HAVE_OPTIONS.map(({ key, label, icon: Icon }) => {
            const active = selectedFeatures.includes(key);
            return (
              <button
                key={key}
                onClick={() => toggleFeature(key)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
                  active
                    ? "bg-blue-600 text-white border border-blue-500"
                    : "bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-600 hover:text-gray-300"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            );
          })}

          {hasActiveFilters && (
            <button
              onClick={onClear}
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-red-400 border border-red-800/50 bg-red-950/30 hover:bg-red-900/40 hover:text-red-300 transition-all ml-auto"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Clear All
            </button>
          )}
        </div>
      </div>
    </div>
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
      className={`group cursor-pointer overflow-hidden rounded-xl border bg-gray-900 transition-all hover:shadow-lg ${
        isTier2
          ? "border-gray-800/60 opacity-85 hover:opacity-100 hover:border-gray-700 hover:shadow-amber-900/10"
          : "border-gray-800 hover:border-gray-700 hover:shadow-blue-900/10"
      }`}
    >
      {/* Property image or gradient placeholder */}
      <div className="relative h-40 bg-gradient-to-br from-gray-800 to-gray-700 flex items-center justify-center overflow-hidden">
        {listing.image_url ? (
          <img
            src={listing.image_url}
            alt={listing.location.display}
            className="absolute inset-0 h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <MapPin className="h-10 w-10 text-gray-600 group-hover:text-gray-500 transition-colors" />
        )}
        {/* Building type badge */}
        <span className="absolute top-3 right-3 rounded-full bg-gray-900/80 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-gray-300 border border-gray-700">
          {listing.building_type}
        </span>
        {/* Tier 2: Check Availability badge */}
        {isTier2 && (
          <span className="absolute top-3 left-3 rounded-full bg-amber-600/90 px-2.5 py-1 text-xs font-medium text-white">
            Check Availability
          </span>
        )}
      </div>

      <div className="p-5">
        {/* City / neighborhood */}
        <div className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-blue-400 shrink-0" />
          <h3 className="text-lg font-semibold text-white truncate">
            {listing.location.display}
          </h3>
        </div>

        {/* Sqft range + Rate range */}
        <div className="mt-3 space-y-1.5 text-sm">
          {listing.sqft_range ? (
            <p className="text-gray-400">{listing.sqft_range.display}</p>
          ) : null}
          {isTier2 ? (
            <p className="text-gray-500 italic">Rate available on request</p>
          ) : listing.rate_range ? (
            <p className="text-emerald-400 font-medium">{listing.rate_range.display}</p>
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
                  className="inline-flex items-center gap-1 rounded-full bg-gray-800 px-2 py-0.5 text-xs text-gray-400"
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
        className="relative w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl"
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-500 hover:text-gray-300 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Location badge */}
        <div className="mb-4 flex items-center gap-2 text-blue-400">
          <MapPin className="h-5 w-5" />
          <span className="font-medium">{listing.location.display}</span>
        </div>

        <h2 className="text-xl font-bold text-white">
          Interested in this space?
        </h2>
        <p className="mt-2 text-sm text-gray-400">
          Tell us what you need and we&apos;ll check availability.
        </p>

        {/* Space details */}
        <div className="mt-4 rounded-lg border border-gray-800 bg-gray-800/50 p-4 space-y-2">
          {listing.sqft_range && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Available Space</span>
              <span className="text-white font-medium">{listing.sqft_range.display}</span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Rate</span>
            {listing.rate_range ? (
              <span className="text-emerald-400 font-medium">{listing.rate_range.display}</span>
            ) : (
              <span className="text-gray-500 italic">On request</span>
            )}
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Type</span>
            <span className="text-white">{listing.building_type}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-6 space-y-3">
          <button
            onClick={() => router.push("/buyer")}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-blue-500 active:scale-[0.98]"
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
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-sm font-medium text-gray-300 transition-all hover:border-gray-600 hover:text-white"
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
        className="relative w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl"
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-500 hover:text-gray-300 transition-colors"
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
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-900/50 border border-emerald-700">
              <ArrowRight className="h-6 w-6 text-emerald-400" />
            </div>
            <h2 className="text-xl font-bold text-white">Request Sent</h2>
            <p className="mt-2 text-sm text-gray-400">
              We&apos;ll check availability and get back to you shortly.
            </p>
            <button
              onClick={onClose}
              className="mt-6 inline-flex items-center justify-center rounded-lg bg-gray-800 px-6 py-2.5 text-sm font-medium text-gray-300 transition-all hover:bg-gray-700 hover:text-white"
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <h2 className="text-xl font-bold text-white">
              Check Availability
            </h2>
            <p className="mt-2 text-sm text-gray-400">
              Leave your details and we&apos;ll confirm availability and pricing for this space.
            </p>

            {/* Form */}
            <div className="mt-5 space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your full name"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Email <span className="text-red-400">*</span>
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Phone <span className="text-red-400">*</span>
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="(555) 123-4567"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Note <span className="text-gray-600">(optional)</span>
                </label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Any details about your needs..."
                  rows={3}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-colors resize-none"
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

  const hasActiveFilters = !!(location || sqft || useType !== "any" || timing || isImmediate || !isFlexible || selectedFeatures.length > 0);

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
    <main className="min-h-screen bg-gray-950">
      <BrowseNavbar />

      {/* Header */}
      <div className="pt-24 pb-6 px-6">
        <div className="mx-auto max-w-7xl">
          <h1 className="text-3xl font-bold text-white sm:text-4xl">
            Browse Spaces
          </h1>
          <p className="mt-2 text-gray-400 text-sm sm:text-base">
            Explore in-network warehouse spaces available through WEx.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="px-6 pb-6">
        <div className="mx-auto max-w-7xl">
          <FilterBar
            location={location}
            sqft={sqft}
            setSqft={setSqft}
            useType={useType}
            setUseType={setUseType}
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
            onSearch={handleSearch}
            onClear={clearAllFilters}
            hasActiveFilters={hasActiveFilters}
            locationSuggestions={locationSuggestions}
            showSuggestions={showSuggestions}
            setShowSuggestions={setShowSuggestions}
            onLocationInput={handleLocationInput}
            onSelectLocation={handleSelectLocation}
          />
        </div>
      </div>

      {/* Grid */}
      <div className="px-6 pb-16">
        <div className="mx-auto max-w-7xl">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24">
              <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
              <p className="mt-4 text-sm text-gray-400">Loading spaces...</p>
            </div>
          ) : listings.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <WarehouseIcon className="h-12 w-12 text-gray-700" />
              <h3 className="mt-4 text-lg font-semibold text-gray-300">
                No spaces found
              </h3>
              <p className="mt-2 text-sm text-gray-500 text-center max-w-md">
                Try adjusting your filters or search for a different location.
              </p>
            </div>
          ) : (
            <>
              {/* Count */}
              <p className="mb-4 text-sm text-gray-400">
                Showing {showingCount} of {total} space{total !== 1 ? "s" : ""}
              </p>

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
                    className="inline-flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-6 py-3 text-sm font-medium text-gray-300 transition-all hover:border-gray-600 hover:text-white disabled:opacity-50"
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
