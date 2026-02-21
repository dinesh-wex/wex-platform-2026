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
  ChevronDown,
  Truck,
  Building2,
  Thermometer,
  Zap,
  Clock,
  ParkingSquare,
  Loader2,
  ArrowRight,
  Menu,
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
  location: {
    city: string;
    state: string;
    display: string;
  };
  sqft_range: {
    min: number;
    max: number;
    display: string;
  };
  rate_range: {
    min: number;
    max: number;
    display: string;
  };
  building_type: string;
  features: ListingFeature[];
  has_image: boolean;
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

const SIZE_OPTIONS = [
  { label: "Any Size", value: "" },
  { label: "Under 5,000 sqft", value: "0-5000" },
  { label: "5,000 - 10,000 sqft", value: "5000-10000" },
  { label: "10,000 - 25,000 sqft", value: "10000-25000" },
  { label: "25,000 - 50,000 sqft", value: "25000-50000" },
  { label: "50,000+ sqft", value: "50000-" },
];

const USE_TYPE_OPTIONS = [
  { label: "Any Use", value: "any" },
  { label: "Storage", value: "storage" },
  { label: "Light Ops", value: "light_ops" },
  { label: "Distribution", value: "distribution" },
];

const FEATURE_OPTIONS = [
  { key: "dock", label: "Dock Doors", icon: Truck },
  { key: "office", label: "Office", icon: Building2 },
  { key: "climate", label: "Climate", icon: Thermometer },
  { key: "power", label: "Power", icon: Zap },
  { key: "24_7", label: "24/7", icon: Clock },
  { key: "parking", label: "Parking", icon: ParkingSquare },
];

const FEATURE_ICON_MAP: Record<string, typeof Truck> = {
  dock: Truck,
  office: Building2,
  climate: Thermometer,
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
  setLocation: (v: string) => void;
  sizeRange: string;
  setSizeRange: (v: string) => void;
  useType: string;
  setUseType: (v: string) => void;
  selectedFeatures: string[];
  toggleFeature: (key: string) => void;
  onSearch: () => void;
  locationSuggestions: LocationSuggestion[];
  showSuggestions: boolean;
  setShowSuggestions: (v: boolean) => void;
  onLocationInput: (v: string) => void;
  onSelectLocation: (loc: LocationSuggestion) => void;
}

function FilterBar({
  location,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  setLocation,
  sizeRange,
  setSizeRange,
  useType,
  setUseType,
  selectedFeatures,
  toggleFeature,
  onSearch,
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
    <div className="rounded-xl border border-gray-800 bg-gray-900/80 backdrop-blur-sm p-4 md:p-6">
      {/* Row 1: Location + Size + Use Type */}
      <div className="grid gap-3 md:grid-cols-3">
        {/* Location with autocomplete */}
        <div className="relative" ref={locationRef}>
          <label className="mb-1.5 block text-xs font-medium text-gray-400">
            Location
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
              placeholder="City or State..."
              className="w-full rounded-lg border border-gray-700 bg-gray-800 py-2.5 pl-10 pr-3 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>

          {/* Autocomplete dropdown */}
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

        {/* Size range */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-gray-400">
            Size
          </label>
          <div className="relative">
            <select
              value={sizeRange}
              onChange={(e) => setSizeRange(e.target.value)}
              className="w-full appearance-none rounded-lg border border-gray-700 bg-gray-800 py-2.5 pl-3 pr-10 text-sm text-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            >
              {SIZE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
          </div>
        </div>

        {/* Use type */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-gray-400">
            Use Type
          </label>
          <div className="relative">
            <select
              value={useType}
              onChange={(e) => setUseType(e.target.value)}
              className="w-full appearance-none rounded-lg border border-gray-700 bg-gray-800 py-2.5 pl-3 pr-10 text-sm text-white outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            >
              {USE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
          </div>
        </div>
      </div>

      {/* Row 2: Feature pills */}
      <div className="mt-4 flex flex-wrap gap-2">
        {FEATURE_OPTIONS.map(({ key, label, icon: Icon }) => {
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
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3) }}
      onClick={onClick}
      className="group cursor-pointer overflow-hidden rounded-xl border border-gray-800 bg-gray-900 transition-all hover:border-gray-700 hover:shadow-lg hover:shadow-blue-900/10"
    >
      {/* Gradient placeholder for satellite image */}
      <div className="relative h-40 bg-gradient-to-br from-gray-800 to-gray-700 flex items-center justify-center">
        <MapPin className="h-10 w-10 text-gray-600 group-hover:text-gray-500 transition-colors" />
        {/* Building type badge */}
        <span className="absolute top-3 right-3 rounded-full bg-gray-900/80 backdrop-blur-sm px-2.5 py-1 text-xs font-medium text-gray-300 border border-gray-700">
          {listing.building_type}
        </span>
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
          <p className="text-gray-400">{listing.sqft_range.display}</p>
          <p className="text-emerald-400 font-medium">{listing.rate_range.display}</p>
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
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Available Space</span>
            <span className="text-white font-medium">{listing.sqft_range.display}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Rate</span>
            <span className="text-emerald-400 font-medium">{listing.rate_range.display}</span>
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
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function BrowsePage() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // Filters
  const [location, setLocation] = useState("");
  const [sizeRange, setSizeRange] = useState("");
  const [useType, setUseType] = useState("any");
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);

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
    if (sizeRange) {
      const [min, max] = sizeRange.split("-");
      if (min) params.min_sqft = parseInt(min);
      if (max) params.max_sqft = parseInt(max);
    }
    if (useType && useType !== "any") params.use_type = useType;
    if (selectedFeatures.length > 0) params.features = selectedFeatures.join(",");
    return params;
  }, [location, sizeRange, useType, selectedFeatures]);

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
  }, [sizeRange, useType, selectedFeatures]); // eslint-disable-line react-hooks/exhaustive-deps

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
            setLocation={setLocation}
            sizeRange={sizeRange}
            setSizeRange={setSizeRange}
            useType={useType}
            setUseType={setUseType}
            selectedFeatures={selectedFeatures}
            toggleFeature={toggleFeature}
            onSearch={handleSearch}
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
                    onClick={() => setSelectedListing(listing)}
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
