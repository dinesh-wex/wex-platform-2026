"use client";

import React, { useState, useEffect } from "react";
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
} from "lucide-react";
import { api } from "@/lib/api";

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
/*  Hero Image / Gradient                                              */
/* ------------------------------------------------------------------ */

function HeroSection({ property }: { property: PropertyDetail }) {
  const hasImages = property.image_urls && property.image_urls.length > 0;
  const heroImage = hasImages ? property.image_urls[0] : property.image_url;

  return (
    <div className="relative h-64 md:h-80 w-full overflow-hidden bg-gradient-to-br from-gray-800 via-gray-800 to-gray-700">
      {heroImage ? (
        <img
          src={heroImage}
          alt={property.location.display}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <WarehouseIcon className="h-16 w-16 text-gray-600" />
        </div>
      )}
      {/* Gradient overlay at the bottom */}
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-gray-950 to-transparent" />
      {/* Building type badge */}
      <span className="absolute top-4 right-4 rounded-full bg-gray-900/80 backdrop-blur-sm px-3 py-1.5 text-xs font-medium text-gray-300 border border-gray-700">
        {property.building_type}
      </span>
      {/* Tier badge */}
      {property.tier === 2 && (
        <span className="absolute top-4 left-4 rounded-full bg-amber-600/90 px-3 py-1.5 text-xs font-medium text-white">
          Check Availability
        </span>
      )}
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
      <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-3">
        Features
      </h2>
      <div className="flex flex-wrap gap-2">
        {features.map((feat) => {
          const Icon = FEATURE_ICON_MAP[feat.key] || Info;
          return (
            <span
              key={feat.key}
              className="inline-flex items-center gap-1.5 rounded-full bg-gray-800 px-3 py-1.5 text-sm text-gray-300"
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
      <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-3">
        Building Specs
      </h2>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        {entries.map((entry) => (
          <div key={entry.label}>
            <dt className="text-xs text-gray-500">{entry.label}</dt>
            <dd className="mt-0.5 text-sm font-medium text-gray-200">{entry.value}</dd>
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
  showQualifyForm: boolean;
  qualifyAction: "book_tour" | "instant_book";
  qualifyForm: QualifyFormState;
  qualifying: boolean;
  qualifyResult: any;
  qualifyError: string;
  onBookTour: () => void;
  onInstantBook: () => void;
  onFormChange: (field: keyof QualifyFormState, value: string) => void;
  onSubmit: () => void;
  onReset: () => void;
}

const TIMING_OPTIONS = [
  { value: "asap", label: "ASAP" },
  { value: "1_month", label: "Within 1 month" },
  { value: "3_months", label: "Within 3 months" },
  { value: "6_months", label: "Within 6 months" },
];

function PricingCard({
  property,
  showQualifyForm,
  qualifyAction,
  qualifyForm,
  qualifying,
  qualifyResult,
  qualifyError,
  onBookTour,
  onInstantBook,
  onFormChange,
  onSubmit,
  onReset,
}: PricingCardProps) {
  const isTier1 = property.tier === 1;

  return (
    <div className="sticky top-24 rounded-xl border border-gray-800 bg-gray-900 p-6 shadow-xl">
      {isTier1 ? (
        <>
          {/* Tier 1 Pricing */}
          <div className="mb-5">
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/40 border border-emerald-800/50 px-2.5 py-1 text-xs font-medium text-emerald-400">
              <Bolt className="h-3 w-3" />
              Tier 1 Listing
            </span>
          </div>

          {property.sqft_range && (
            <div className="mb-3">
              <p className="text-xs text-gray-500">Available Space</p>
              <p className="text-lg font-semibold text-white">{property.sqft_range.display}</p>
            </div>
          )}

          {property.rate_range && (
            <div className="mb-6">
              <p className="text-xs text-gray-500">Rate</p>
              <p className="text-lg font-semibold text-emerald-400">{property.rate_range.display}</p>
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
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-600 px-4 py-3 text-sm font-semibold text-emerald-400 transition-all hover:bg-emerald-600/10 active:scale-[0.98]"
              >
                <Bolt className="h-4 w-4" />
                Instant Book
              </button>
            )}
          </div>

          {/* Inline Qualify Form */}
          <div
            className={`overflow-hidden transition-all duration-300 ease-in-out ${
              showQualifyForm && !qualifyResult
                ? "max-h-[600px] opacity-100 mt-5"
                : showQualifyForm && qualifyResult
                ? "max-h-[300px] opacity-100 mt-5"
                : "max-h-0 opacity-0"
            }`}
          >
            {qualifyResult ? (
              /* ---------- Result display ---------- */
              <div>
                {qualifyResult.status === "match" ? (
                  <div className="rounded-lg border border-emerald-800/50 bg-emerald-900/20 p-4">
                    <div className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-emerald-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-semibold text-emerald-400 mb-1">Great match!</p>
                        <p className="text-sm text-gray-300">
                          We&apos;re setting up your {qualifyAction === "book_tour" ? "tour" : "booking"}.
                          {qualifyResult.message && (
                            <span className="block mt-1 text-gray-400">{qualifyResult.message}</span>
                          )}
                        </p>
                        {qualifyResult.engagement_id && (
                          <a
                            href={`/buyer/engagement/${qualifyResult.engagement_id}`}
                            className="inline-flex items-center gap-1.5 mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
                          >
                            Continue
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-amber-800/50 bg-amber-900/20 p-4">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-semibold text-amber-400 mb-1">
                          This space might not be the best fit
                        </p>
                        <p className="text-sm text-gray-300">
                          {qualifyResult.reasons?.[0] || "Your requirements don't quite match this listing."}
                          {qualifyResult.alternatives_count > 0 && (
                            <span className="block mt-1 text-gray-400">
                              We found {qualifyResult.alternatives_count} other option{qualifyResult.alternatives_count !== 1 ? "s" : ""} that might work better.
                            </span>
                          )}
                        </p>
                        <div className="flex gap-2 mt-3">
                          <a
                            href="/buyer/options"
                            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-amber-500 active:scale-[0.98]"
                          >
                            View Alternatives
                          </a>
                          <button
                            onClick={onReset}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-all hover:bg-gray-800 active:scale-[0.98]"
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
              <div className="border-t border-gray-800 pt-5">
                <p className="text-sm font-semibold text-white mb-4">
                  {qualifyAction === "book_tour" ? "Book a Tour" : "Instant Book"}
                </p>

                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      How much space do you need? <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="number"
                      placeholder="e.g. 5000"
                      value={qualifyForm.sqft_needed}
                      onChange={(e) => onFormChange("sqft_needed", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2.5 text-sm placeholder-gray-500 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                    <p className="text-[11px] text-gray-500 mt-0.5">sqft</p>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-400 mb-1">When do you need it?</label>
                    <select
                      value={qualifyForm.timing}
                      onChange={(e) => onFormChange("timing", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2.5 text-sm focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    >
                      {TIMING_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Your name <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="Full name"
                      value={qualifyForm.name}
                      onChange={(e) => onFormChange("name", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2.5 text-sm placeholder-gray-500 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Phone number <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="tel"
                      placeholder="(555) 123-4567"
                      value={qualifyForm.phone}
                      onChange={(e) => onFormChange("phone", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2.5 text-sm placeholder-gray-500 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Email</label>
                    <input
                      type="email"
                      placeholder="you@company.com"
                      value={qualifyForm.email}
                      onChange={(e) => onFormChange("email", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2.5 text-sm placeholder-gray-500 focus:ring-emerald-500 focus:border-emerald-500 focus:outline-none"
                    />
                  </div>

                  {qualifyError && (
                    <p className="text-sm text-red-400">{qualifyError}</p>
                  )}

                  <button
                    onClick={onSubmit}
                    disabled={qualifying}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed mt-2"
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
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          {/* Tier 2 Pricing */}
          <div className="mb-5">
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-900/40 border border-amber-800/50 px-2.5 py-1 text-xs font-medium text-amber-400">
              Tier 2 Listing
            </span>
          </div>

          {property.sqft_range && (
            <div className="mb-3">
              <p className="text-xs text-gray-500">Available Space</p>
              <p className="text-lg font-semibold text-white">{property.sqft_range.display}</p>
            </div>
          )}

          <div className="mb-6">
            <p className="text-xs text-gray-500">Rate</p>
            <p className="text-sm text-gray-500 italic">Available on request</p>
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
/*  Loading Skeleton                                                   */
/* ------------------------------------------------------------------ */

function LoadingSkeleton() {
  return (
    <main className="min-h-screen bg-gray-950">
      <BrowseNavbar />
      <div className="pt-16">
        {/* Hero skeleton */}
        <div className="h-64 md:h-80 w-full bg-gray-800 animate-pulse" />

        <div className="mx-auto max-w-7xl px-6 py-8">
          {/* Back link skeleton */}
          <div className="h-4 w-32 bg-gray-800 rounded animate-pulse mb-8" />

          <div className="grid gap-8 lg:grid-cols-3">
            {/* Left column */}
            <div className="lg:col-span-2 space-y-6">
              <div className="h-8 w-48 bg-gray-800 rounded animate-pulse" />
              <div className="h-5 w-32 bg-gray-800 rounded animate-pulse" />
              <div className="flex gap-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 w-20 bg-gray-800 rounded-full animate-pulse" />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-4">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i}>
                    <div className="h-3 w-16 bg-gray-800 rounded animate-pulse mb-1" />
                    <div className="h-5 w-24 bg-gray-800 rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </div>

            {/* Right column */}
            <div>
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 space-y-4">
                <div className="h-6 w-24 bg-gray-800 rounded-full animate-pulse" />
                <div className="h-5 w-36 bg-gray-800 rounded animate-pulse" />
                <div className="h-5 w-28 bg-gray-800 rounded animate-pulse" />
                <div className="h-12 w-full bg-gray-800 rounded-lg animate-pulse" />
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
    <main className="min-h-screen bg-gray-950">
      <BrowseNavbar />
      <div className="flex flex-col items-center justify-center pt-32 px-6">
        <WarehouseIcon className="h-16 w-16 text-gray-700 mb-6" />
        <h1 className="text-2xl font-bold text-white mb-2">Listing Not Found</h1>
        <p className="text-gray-400 text-sm mb-8 text-center max-w-md">
          This listing may have been removed or is no longer available. Try browsing other spaces.
        </p>
        <Link
          href="/browse"
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition-all hover:bg-blue-500 active:scale-[0.98]"
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

  // Qualify form state
  const [showQualifyForm, setShowQualifyForm] = useState(false);
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

  function handleFormChange(field: keyof QualifyFormState, value: string) {
    setQualifyForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleBookTour() {
    setQualifyAction("book_tour");
    setShowQualifyForm(true);
    setQualifyResult(null);
    setQualifyError("");
  }

  function handleInstantBook() {
    setQualifyAction("instant_book");
    setShowQualifyForm(true);
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
    <main className="min-h-screen bg-gray-950">
      <BrowseNavbar />

      {/* Spacer for fixed navbar */}
      <div className="pt-16">
        {/* Hero */}
        <HeroSection property={property} />

        {/* Content */}
        <div className="mx-auto max-w-7xl px-6 py-8">
          {/* Back link */}
          <Link
            href="/browse"
            className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors mb-8"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Browse
          </Link>

          <div className="grid gap-8 lg:grid-cols-3">
            {/* Left Column (2/3) */}
            <div className="lg:col-span-2 space-y-8">
              {/* Location + Type */}
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <MapPin className="h-5 w-5 text-blue-400 shrink-0" />
                  <h1 className="text-2xl font-bold text-white md:text-3xl">
                    {property.location.display}
                  </h1>
                </div>
                <p className="text-gray-400 text-sm ml-7">
                  {property.building_type}
                </p>
              </div>

              {/* Features */}
              <FeaturesSection features={property.features} />

              {/* Specs */}
              <SpecsSection specs={property.specs} />
            </div>

            {/* Right Column (1/3) */}
            <div>
              <PricingCard
                property={property}
                showQualifyForm={showQualifyForm}
                qualifyAction={qualifyAction}
                qualifyForm={qualifyForm}
                qualifying={qualifying}
                qualifyResult={qualifyResult}
                qualifyError={qualifyError}
                onBookTour={handleBookTour}
                onInstantBook={handleInstantBook}
                onFormChange={handleFormChange}
                onSubmit={handleQualify}
                onReset={handleQualifyReset}
              />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
