"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  Upload,
  Image as ImageIcon,
  Building2,
  DollarSign,
  Calendar,
  Clock,
  TrendingUp,
  X,
  Star,
} from "lucide-react";

import { api } from "@/lib/api";
import TabBar from "@/components/supplier/TabBar";
import AISuggestionCard from "@/components/supplier/AISuggestionCard";
import InlineEdit, { type InlineEditHandle } from "@/components/supplier/InlineEdit";
import StatusBadge from "@/components/supplier/StatusBadge";
import Timeline from "@/components/supplier/Timeline";
import QRPhotoUpload from "@/components/supplier/QRPhotoUpload";

import type {
  Warehouse,
  AISuggestion,
  Engagement,
  PropertyActivity,
} from "@/types/supplier";

import {
  demoWarehouses,
  demoSuggestions,
  demoEngagements,
  demoPropertyActivity,
} from "@/lib/supplier-demo-data";

// =============================================================================
// Constants
// =============================================================================

const TABS = [
  { key: "photos", label: "Photos" },
  { key: "building", label: "Building Info" },
  { key: "config", label: "Configuration" },
  { key: "pricing", label: "Pricing" },
  { key: "engagements", label: "Engagements" },
  { key: "activity", label: "Activity" },
];

const CONSTRUCTION_OPTIONS = [
  { value: "Tilt-Up Concrete", label: "Tilt-Up Concrete" },
  { value: "Pre-Engineered Metal", label: "Pre-Engineered Metal" },
  { value: "Steel Frame", label: "Steel Frame" },
  { value: "Masonry", label: "Masonry" },
  { value: "Wood Frame", label: "Wood Frame" },
  { value: "Other", label: "Other" },
];

const POWER_OPTIONS = [
  { value: "3-Phase, 480V", label: "3-Phase, 480V" },
  { value: "3-Phase, 208V", label: "3-Phase, 208V" },
  { value: "Single Phase, 240V", label: "Single Phase, 240V" },
  { value: "Single Phase, 120V", label: "Single Phase, 120V" },
  { value: "Other", label: "Other" },
];

const ACTIVITY_TIER_OPTIONS = [
  { value: "storage_only", label: "Storage Only" },
  { value: "storage_light_assembly", label: "Storage + Light Assembly" },
  { value: "full_operations", label: "Full Operations" },
];

// Inferred fields
const INFERRED_FIELDS = new Set([
  "construction_type",
  "zoning",
  "power_supply",
]);

// Mapping from field name to the tab that contains it
const FIELD_TO_TAB: Record<string, string> = {
  photos: "photos",
  building_sqft: "building",
  clear_height_ft: "building",
  dock_doors: "building",
  drive_in_bays: "building",
  year_built: "building",
  construction_type: "building",
  zoning: "building",
  lot_size_acres: "building",
  sprinkler: "building",
  power_supply: "building",
  parking_spaces: "building",
  available_sqft: "config",
  min_rentable_sqft: "config",
  activity_tier: "config",
  has_office: "config",
  weekend_access: "config",
  access_24_7: "config",
  min_term_months: "config",
  available_from: "config",
  // Certification fields (demand-triggered, mapped to config tab)
  food_grade: "config",
  fda_registered: "config",
  hazmat_certified: "config",
  c_tpat: "config",
  temperature_controlled: "config",
  foreign_trade_zone: "config",
  target_rate_sqft: "pricing",
};

// =============================================================================
// Helpers
// =============================================================================

interface CompletenessResult {
  score: number;
  topMissingField: string | null;
}

/**
 * Three-tier weighted profile completeness model.
 *
 * Tier 1 (60 pts): critical listing fields
 * Tier 2 (30 pts): important detail fields
 * Tier 3 (10 pts): supplementary fields
 *
 * Certifications are NOT counted.
 */
function computeCompleteness(w: Warehouse, photoCount: number): CompletenessResult {
  const tc = w.truth_core;
  if (!tc) return { score: 10, topMissingField: "photos" };

  const isFilled = (v: unknown): boolean =>
    v !== undefined && v !== null && v !== "";

  // Each entry: [field name, weight, custom check (optional)]
  type FieldCheck = { field: string; weight: number; filled: boolean };

  const checks: FieldCheck[] = [
    // ---- Tier 1 (60%) ----
    { field: "photos",           weight: 15, filled: photoCount >= 3 },
    { field: "available_sqft",   weight: 10, filled: isFilled(tc.available_sqft) },
    { field: "target_rate_sqft", weight: 10, filled: isFilled(tc.target_rate_sqft) && Number(tc.target_rate_sqft) > 0 },
    { field: "clear_height_ft",  weight: 8,  filled: isFilled(tc.clear_height_ft) },
    { field: "dock_doors",       weight: 7,  filled: isFilled(tc.dock_doors) },
    { field: "activity_tier",    weight: 5,  filled: isFilled(tc.activity_tier) },
    { field: "available_from",   weight: 5,  filled: isFilled(tc.available_from) },

    // ---- Tier 2 (30%) ----
    { field: "has_office",       weight: 5,  filled: isFilled(tc.has_office) },
    { field: "weekend_access",   weight: 5,  filled: isFilled(tc.weekend_access) || isFilled(tc.access_24_7) },
    { field: "min_rentable_sqft",weight: 4,  filled: isFilled(tc.min_rentable_sqft) },
    { field: "min_term_months",  weight: 4,  filled: isFilled(tc.min_term_months) },
    { field: "parking_spaces",   weight: 4,  filled: isFilled(tc.parking_spaces) },
    { field: "power_supply",     weight: 4,  filled: isFilled(tc.power_supply) },
    { field: "sprinkler",        weight: 4,  filled: isFilled(tc.sprinkler) },

    // ---- Tier 3 (10%) — each ~1.67% ----
    { field: "construction_type",weight: 1.67, filled: isFilled(tc.construction_type) },
    { field: "zoning",           weight: 1.67, filled: isFilled(tc.zoning) },
    { field: "lot_size_acres",   weight: 1.67, filled: isFilled(tc.lot_size_acres) },
    { field: "year_built",       weight: 1.67, filled: isFilled(tc.year_built) },
    { field: "building_sqft",    weight: 1.66, filled: isFilled(tc.building_sqft) },
    { field: "drive_in_bays",    weight: 1.66, filled: isFilled(tc.drive_in_bays) },
  ];

  let score = 0;
  let topMissingField: string | null = null;
  let topMissingWeight = -1;

  for (const c of checks) {
    if (c.filled) {
      score += c.weight;
    } else if (c.weight > topMissingWeight) {
      topMissingWeight = c.weight;
      topMissingField = c.field;
    }
  }

  return { score: Math.round(score), topMissingField };
}

function formatCurrency(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// =============================================================================
// Page Component
// =============================================================================

export default function PropertyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  // ---- Core state ----
  const [warehouse, setWarehouse] = useState<Warehouse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("photos");
  const [matchingOn, setMatchingOn] = useState(true);

  // ---- Data per tab ----
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([]);
  const [photos, setPhotos] = useState<{ id: string; url: string }[]>([]);
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [activity, setActivity] = useState<PropertyActivity[]>([]);
  const [completeness, setCompleteness] = useState<number>(0);
  const [topMissingField, setTopMissingField] = useState<string | null>(null);

  // ---- Pricing live state ----
  const [liveRate, setLiveRate] = useState<number>(0);

  // ---- Drag-and-drop (file upload) ----
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- InlineEdit refs for programmatic edit triggering ----
  const fieldRefs = useRef<Record<string, InlineEditHandle | null>>({});
  const fieldElementRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // ---- Photo reorder drag state ----
  const [dragPhotoIdx, setDragPhotoIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  // ===========================================================================
  // Data fetching
  // ===========================================================================

  useEffect(() => {
    let cancelled = false;

    async function load() {
      // 1. Property
      let wh: Warehouse | null = null;
      try {
        wh = await api.getProperty(id);
      } catch {
        wh = demoWarehouses.find((w) => w.id === id) ?? null;
      }
      if (cancelled) return;
      setWarehouse(wh);
      setMatchingOn(wh?.status === "in_network");
      setLiveRate(wh?.truth_core?.target_rate_sqft ?? wh?.supplier_rate ?? 0);

      // Compute completeness (photos not loaded yet — use 0; will recompute after photos load)
      if (wh) {
        try {
          const pc = await api.getProfileCompleteness(id);
          if (!cancelled) {
            const local = computeCompleteness(wh, 0);
            setCompleteness(pc.total ?? local.score);
            setTopMissingField(local.topMissingField);
          }
        } catch {
          if (!cancelled) {
            const local = computeCompleteness(wh, 0);
            setCompleteness(local.score);
            setTopMissingField(local.topMissingField);
          }
        }
      }

      // 2. Suggestions
      try {
        const sug = await api.getPropertySuggestions(id);
        const sugList = sug?.suggestions ?? sug;
        if (!cancelled) setSuggestions(Array.isArray(sugList) ? sugList : []);
      } catch {
        if (!cancelled)
          setSuggestions(
            demoSuggestions.filter(
              (s) => !s.target_property_id || s.target_property_id === id,
            ),
          );
      }

      // 3. Photos
      try {
        const p = await api.getPropertyPhotos(id);
        const photoList = p?.photos ?? p;
        if (!cancelled) setPhotos(Array.isArray(photoList) ? photoList : []);
      } catch {
        if (!cancelled) setPhotos([]);
      }

      // 4. Engagements
      try {
        const eng = await api.getEngagements();
        const list = Array.isArray(eng) ? eng : eng.engagements ?? [];
        if (!cancelled)
          setEngagements(list.filter((e: Engagement) => e.property_id === id));
      } catch {
        if (!cancelled)
          setEngagements(demoEngagements.filter((e) => e.property_id === id));
      }

      // 5. Activity
      try {
        const act = await api.getPropertyActivity(id);
        const actList = act?.activity ?? act;
        if (!cancelled) setActivity(Array.isArray(actList) ? actList : []);
      } catch {
        if (!cancelled) setActivity(demoPropertyActivity);
      }

      if (!cancelled) setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Recompute completeness when photos or warehouse truth_core changes
  useEffect(() => {
    if (!warehouse) return;
    const result = computeCompleteness(warehouse, photos.length);
    setCompleteness(result.score);
    setTopMissingField(result.topMissingField);
  }, [warehouse, photos.length]);

  // ===========================================================================
  // Handlers
  // ===========================================================================

  const handleToggleMatching = useCallback(async () => {
    // Use functional setState to avoid stale closure issues
    setMatchingOn((prev) => {
      const next = !prev;
      const backendStatus = next ? "on" : "off";
      // Update warehouse status optimistically
      setWarehouse((w) =>
        w ? { ...w, status: next ? "in_network" : "in_network_paused" } : w,
      );
      // Fire API call (async, outside setState)
      api.toggleWarehouse(id, backendStatus).catch((err) => {
        console.error("Toggle failed:", err);
        // Revert on failure
        setMatchingOn(prev);
        setWarehouse((w) =>
          w ? { ...w, status: prev ? "in_network" : "in_network_paused" } : w,
        );
      });
      return next;
    });
  }, [id]);

  const handleSaveSpec = useCallback(
    async (field: string, value: string | number | boolean) => {
      try {
        await api.updateSpecs(id, { [field]: value });
      } catch {
        // Optimistic
      }
      setWarehouse((prev) =>
        prev
          ? {
              ...prev,
              truth_core: { ...prev.truth_core, [field]: value },
            }
          : prev,
      );
    },
    [id],
  );

  const handleSaveConfig = useCallback(
    async (field: string, value: string | number | boolean) => {
      try {
        await api.updateConfig(id, { [field]: value });
      } catch {
        // Optimistic
      }
      setWarehouse((prev) =>
        prev
          ? {
              ...prev,
              truth_core: { ...prev.truth_core, [field]: value },
            }
          : prev,
      );
    },
    [id],
  );

  const handleSaveRate = useCallback(
    async (value: string | number | boolean) => {
      const rate = typeof value === "number" ? value : Number(value);
      setLiveRate(rate);
      try {
        await api.updatePricing(id, { rate });
      } catch {
        // Optimistic
      }
      setWarehouse((prev) =>
        prev
          ? {
              ...prev,
              supplier_rate: rate,
              truth_core: { ...prev.truth_core, target_rate_sqft: rate },
            }
          : prev,
      );
    },
    [id],
  );

  const handlePhotosUploaded = useCallback(async () => {
    try {
      const p = await api.getPropertyPhotos(id);
      setPhotos(Array.isArray(p) ? p : []);
    } catch {
      // ignore
    }
  }, [id]);

  const uploadFiles = useCallback(
    async (fileList: File[]) => {
      const images = fileList.filter((f) =>
        /\.(jpe?g|png|heic|webp)$/i.test(f.name),
      );
      if (images.length === 0) return;

      setUploading(true);
      try {
        const { token } = await api.getUploadToken(id);
        const formData = new FormData();
        images.forEach((f) => formData.append("files", f));
        await api.uploadPropertyPhotos(id, token, formData);
        await handlePhotosUploaded();
      } catch (err) {
        console.error("Photo upload failed:", err);
        alert("Photo upload failed. Please try again.");
      } finally {
        setUploading(false);
      }
    },
    [id, handlePhotosUploaded],
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      uploadFiles(Array.from(e.dataTransfer.files));
    },
    [uploadFiles],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        uploadFiles(Array.from(e.target.files));
        // Reset the input so the same file can be selected again
        e.target.value = "";
      }
    },
    [uploadFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragging(false);
  }, []);

  // ---- Photo management handlers ----

  const handleDeletePhoto = useCallback(
    async (photoId: string) => {
      // Optimistic removal
      setPhotos((prev) => prev.filter((p) => p.id !== photoId));
      try {
        await api.deletePropertyPhoto(id, photoId);
      } catch {
        // Re-fetch on failure to restore accurate state
        try {
          const p = await api.getPropertyPhotos(id);
          const photoList = p?.photos ?? p;
          setPhotos(Array.isArray(photoList) ? photoList : []);
        } catch {
          // ignore
        }
      }
    },
    [id],
  );

  const handleSetPrimary = useCallback(
    async (photoId: string) => {
      try {
        await api.setPropertyPrimaryPhoto(id, photoId);
        // Move the selected photo to the front
        setPhotos((prev) => {
          const idx = prev.findIndex((p) => p.id === photoId);
          if (idx <= 0) return prev;
          const next = [...prev];
          const [moved] = next.splice(idx, 1);
          next.unshift(moved);
          return next;
        });
      } catch {
        // ignore
      }
    },
    [id],
  );

  const handlePhotoDragStart = useCallback(
    (e: React.DragEvent, idx: number) => {
      setDragPhotoIdx(idx);
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(idx));
    },
    [],
  );

  const handlePhotoDragOver = useCallback(
    (e: React.DragEvent, idx: number) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setDragOverIdx(idx);
    },
    [],
  );

  const handlePhotoDragEnd = useCallback(() => {
    setDragPhotoIdx(null);
    setDragOverIdx(null);
  }, []);

  const handlePhotoDrop = useCallback(
    async (e: React.DragEvent, targetIdx: number) => {
      e.preventDefault();
      const sourceIdx = dragPhotoIdx;
      setDragPhotoIdx(null);
      setDragOverIdx(null);

      if (sourceIdx === null || sourceIdx === targetIdx) return;

      // Reorder optimistically
      setPhotos((prev) => {
        const next = [...prev];
        const [moved] = next.splice(sourceIdx, 1);
        next.splice(targetIdx, 0, moved);
        return next;
      });

      // Build new order and send to API
      const reordered = [...photos];
      const [moved] = reordered.splice(sourceIdx, 1);
      reordered.splice(targetIdx, 0, moved);
      const newOrder = reordered.map((p) => p.id);

      try {
        await api.reorderPropertyPhotos(id, newOrder);
      } catch {
        // ignore — optimistic state already applied
      }
    },
    [dragPhotoIdx, photos, id],
  );

  // ===========================================================================
  // AI Suggestion → scroll-to-field action
  // ===========================================================================

  const handleSuggestionAction = useCallback(
    (sug: AISuggestion) => {
      // Determine target tab: explicit target_tab, or infer from target_field
      const targetTab =
        sug.target_tab ??
        (sug.target_field ? FIELD_TO_TAB[sug.target_field] : undefined);

      if (!targetTab) {
        // Fallback: navigate if there's a URL
        if (sug.action_url) router.push(sug.action_url);
        return;
      }

      // 1. Switch to the correct tab
      setActiveTab(targetTab);

      // 2. After tab renders, scroll to the field and trigger edit mode
      // Use 200ms to ensure the new tab has fully rendered and refs are populated
      const field = sug.target_field;
      if (field) {
        setTimeout(() => {
          const el = fieldElementRefs.current[field];
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "center" });
            // Flash highlight to draw attention
            el.style.transition = "background-color 0.3s";
            el.style.backgroundColor = "#ecfdf5"; // emerald-50
            setTimeout(() => { el.style.backgroundColor = ""; }, 2000);
          }
          const handle = fieldRefs.current[field];
          if (handle) {
            handle.startEdit();
          }
        }, 200);
      }
    },
    [router],
  );

  // Navigate to the highest-weight missing field when the progress bar is clicked
  const handleProgressBarClick = useCallback(() => {
    if (!topMissingField) return;

    const targetTab = FIELD_TO_TAB[topMissingField];
    if (!targetTab) return;

    setActiveTab(targetTab);

    // For photos tab there is no InlineEdit to trigger
    if (topMissingField === "photos") return;

    setTimeout(() => {
      const el = fieldElementRefs.current[topMissingField];
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.style.transition = "background-color 0.3s";
        el.style.backgroundColor = "#ecfdf5";
        setTimeout(() => { el.style.backgroundColor = ""; }, 2000);
      }
      const handle = fieldRefs.current[topMissingField];
      if (handle) {
        handle.startEdit();
      }
    }, 200);
  }, [topMissingField]);

  // ===========================================================================
  // Derived values
  // ===========================================================================

  const tc = warehouse?.truth_core;

  const projectedAnnual = useMemo(() => {
    const sqft = tc?.available_sqft ?? warehouse?.available_sqft ?? 0;
    return liveRate * sqft * 12;
  }, [liveRate, tc, warehouse]);

  const engagementCount = engagements.length;
  const tabsWithCounts = useMemo(
    () =>
      TABS.map((t) => ({
        ...t,
        count:
          t.key === "engagements" && engagementCount > 0
            ? engagementCount
            : t.key === "photos" && photos.length > 0
              ? photos.length
              : undefined,
      })),
    [engagementCount, photos.length],
  );

  // ===========================================================================
  // Loading skeleton
  // ===========================================================================

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <div className="max-w-5xl mx-auto px-6 py-8">
          {/* Back link skeleton */}
          <div className="h-4 w-36 bg-slate-200 rounded animate-pulse mb-6" />

          {/* Header skeleton */}
          <div className="space-y-3 mb-8">
            <div className="h-8 w-80 bg-slate-200 rounded animate-pulse" />
            <div className="h-4 w-64 bg-slate-200 rounded animate-pulse" />
            <div className="flex items-center gap-3">
              <div className="h-6 w-24 bg-slate-200 rounded-full animate-pulse" />
              <div className="h-6 w-48 bg-slate-200 rounded animate-pulse" />
            </div>
          </div>

          {/* Tab bar skeleton */}
          <div className="flex gap-4 border-b border-slate-200 pb-2 mb-8">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="h-5 w-20 bg-slate-200 rounded animate-pulse"
              />
            ))}
          </div>

          {/* Content skeleton */}
          <div className="grid grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-32 bg-slate-200 rounded-xl animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!warehouse) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <Building2 className="mx-auto mb-4 h-12 w-12 text-slate-300" />
          <h2 className="text-lg font-semibold text-slate-900">
            Property not found
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            The property you are looking for does not exist or has been removed.
          </p>
          <Link
            href="/supplier"
            className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-emerald-600 hover:text-emerald-700"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Portfolio
          </Link>
        </div>
      </div>
    );
  }

  // ===========================================================================
  // Render
  // ===========================================================================

  const fullAddress = `${warehouse.address}, ${warehouse.city}, ${warehouse.state} ${warehouse.zip_code}`;

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* ================================================================
            Header
            ================================================================ */}
        <Link
          href="/supplier"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-700 transition-colors mb-6"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Portfolio
        </Link>

        <div className="mb-8">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                {warehouse.name || fullAddress}
              </h1>
              <p className="mt-1 text-sm text-slate-500">{fullAddress}</p>
            </div>

            {/* Matching toggle */}
            <div className="flex items-center gap-3">
              <StatusBadge status={warehouse.status} />
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500">Matching</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={matchingOn}
                  onClick={handleToggleMatching}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 ${
                    matchingOn ? "bg-emerald-500" : "bg-slate-300"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ${
                      matchingOn ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Profile completeness — clickable to scroll to highest-weight missing field */}
          <button
            type="button"
            onClick={handleProgressBarClick}
            disabled={!topMissingField}
            className="mt-4 flex items-center gap-3 group cursor-pointer disabled:cursor-default"
            title={
              topMissingField
                ? `Next: fill in ${topMissingField.replace(/_/g, " ")}`
                : "Profile complete!"
            }
          >
            <span className="text-sm font-medium text-slate-600 group-hover:text-emerald-700 transition-colors">
              Profile {completeness}% complete
            </span>
            <div className="relative h-2 w-48 overflow-hidden rounded-full bg-slate-200 group-hover:bg-slate-300 transition-colors">
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full bg-emerald-500"
                initial={{ width: 0 }}
                animate={{ width: `${completeness}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
              />
            </div>
          </button>
        </div>

        {/* ================================================================
            AI Suggestions ("Ways to Earn More")
            ================================================================ */}
        {suggestions.length > 0 && (
          <div className="mb-8">
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Recommendations
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {suggestions.slice(0, 3).map((sug) => (
                <AISuggestionCard
                  key={sug.id}
                  suggestion={sug}
                  onAction={() => handleSuggestionAction(sug)}
                  onDismiss={() =>
                    setSuggestions((prev) =>
                      prev.filter((s) => s.id !== sug.id),
                    )
                  }
                />
              ))}
            </div>
          </div>
        )}

        {/* ================================================================
            Tabbed Content
            ================================================================ */}
        <TabBar
          tabs={tabsWithCounts}
          activeTab={activeTab}
          onChange={setActiveTab}
        />

        <div className="mt-6">
          <AnimatePresence mode="wait">
            {/* ---- Photos Tab ---- */}
            {activeTab === "photos" && (
              <motion.div
                key="photos"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Photo grid */}
                  <div className="lg:col-span-2">
                    {photos.length > 0 ? (
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        {photos.map((photo, idx) => (
                          <div
                            key={photo.id}
                            draggable
                            onDragStart={(e) => handlePhotoDragStart(e, idx)}
                            onDragOver={(e) => handlePhotoDragOver(e, idx)}
                            onDragEnd={handlePhotoDragEnd}
                            onDrop={(e) => handlePhotoDrop(e, idx)}
                            className={`group relative aspect-[4/3] rounded-lg overflow-hidden bg-slate-100 cursor-grab active:cursor-grabbing transition-all ${
                              dragPhotoIdx === idx
                                ? "opacity-40 scale-95"
                                : ""
                            } ${
                              dragOverIdx === idx && dragPhotoIdx !== idx
                                ? "ring-2 ring-emerald-400 ring-offset-2"
                                : ""
                            }`}
                          >
                            <img
                              src={photo.url}
                              alt="Property photo"
                              className="h-full w-full object-cover pointer-events-none"
                            />

                            {/* Primary badge */}
                            {idx === 0 && (
                              <span className="absolute top-2 left-2 inline-flex items-center gap-1 rounded-full bg-amber-400/90 px-2 py-0.5 text-xs font-semibold text-white shadow">
                                <Star className="h-3 w-3 fill-current" />
                                Primary
                              </span>
                            )}

                            {/* Delete button */}
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeletePhoto(photo.id);
                              }}
                              className="absolute top-2 right-2 flex h-7 w-7 items-center justify-center rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
                              title="Delete photo"
                            >
                              <X className="h-4 w-4" />
                            </button>

                            {/* Set as primary button (non-primary photos only) */}
                            {idx !== 0 && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSetPrimary(photo.id);
                                }}
                                className="absolute bottom-2 left-2 flex items-center gap-1 rounded-full bg-black/50 px-2 py-1 text-xs font-medium text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-amber-500"
                                title="Set as primary photo"
                              >
                                <Star className="h-3 w-3" />
                                Set primary
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-slate-200 bg-white p-12 text-center">
                        <ImageIcon className="mx-auto mb-3 h-10 w-10 text-slate-300" />
                        <h3 className="text-base font-semibold text-slate-900">
                          No photos yet
                        </h3>
                        <p className="mt-1 text-sm text-slate-500">
                          Properties with photos get 2x more tour requests.
                          Upload from your phone or desktop.
                        </p>
                      </div>
                    )}

                    {/* Hidden file input for click-to-browse */}
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept="image/*"
                      className="hidden"
                      onChange={handleFileInputChange}
                    />

                    {/* Desktop drag-drop zone (also clickable) */}
                    <div
                      onDrop={handleDrop}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onClick={() => fileInputRef.current?.click()}
                      className={`mt-4 rounded-xl border-2 border-dashed p-8 text-center transition-colors cursor-pointer ${
                        dragging
                          ? "border-emerald-400 bg-emerald-50"
                          : uploading
                            ? "border-emerald-300 bg-emerald-50/50"
                            : "border-slate-300 bg-white hover:border-slate-400"
                      }`}
                    >
                      {uploading ? (
                        <>
                          <div className="mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-600" />
                          <p className="text-sm font-medium text-emerald-700">
                            Uploading photos...
                          </p>
                        </>
                      ) : (
                        <>
                          <Upload
                            className={`mx-auto mb-2 h-8 w-8 ${
                              dragging ? "text-emerald-500" : "text-slate-400"
                            }`}
                          />
                          <p className="text-sm font-medium text-slate-700">
                            Drag and drop photos here
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            or click to browse
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            JPG, PNG, HEIC, or WebP
                          </p>
                        </>
                      )}
                    </div>
                  </div>

                  {/* QR Upload */}
                  <div>
                    <QRPhotoUpload
                      propertyId={id}
                      onPhotosUploaded={handlePhotosUploaded}
                    />
                  </div>
                </div>
              </motion.div>
            )}

            {/* ---- Building Info Tab ---- */}
            {activeTab === "building" && (
              <motion.div
                key="building"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="rounded-xl border border-slate-200 bg-white p-6">
                  <h3 className="text-lg font-semibold text-slate-900 mb-4">
                    Building Specifications
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1">
                    <div ref={(el) => { fieldElementRefs.current.building_sqft = el; }}>
                      <InlineEdit
                        label="Building Size"
                        value={tc?.building_sqft ?? 0}
                        type="number"
                        unit="sqft"
                        onSave={(v) => handleSaveSpec("building_sqft", v)}
                        editRef={(ref) => { fieldRefs.current.building_sqft = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.clear_height_ft = el; }}>
                      <InlineEdit
                        label="Clear Height"
                        value={tc?.clear_height_ft ?? 0}
                        type="number"
                        unit="ft"
                        onSave={(v) => handleSaveSpec("clear_height_ft", v)}
                        editRef={(ref) => { fieldRefs.current.clear_height_ft = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.dock_doors = el; }}>
                      <InlineEdit
                        label="Dock Doors"
                        value={tc?.dock_doors ?? 0}
                        type="number"
                        onSave={(v) => handleSaveSpec("dock_doors", v)}
                        editRef={(ref) => { fieldRefs.current.dock_doors = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.drive_in_bays = el; }}>
                      <InlineEdit
                        label="Drive-In Bays"
                        value={tc?.drive_in_bays ?? 0}
                        type="number"
                        onSave={(v) => handleSaveSpec("drive_in_bays", v)}
                        editRef={(ref) => { fieldRefs.current.drive_in_bays = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.year_built = el; }}>
                      <InlineEdit
                        label="Year Built"
                        value={tc?.year_built ?? 0}
                        type="number"
                        onSave={(v) => handleSaveSpec("year_built", v)}
                        editRef={(ref) => { fieldRefs.current.year_built = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.construction_type = el; }}>
                      <InlineEdit
                        label="Construction"
                        value={tc?.construction_type ?? ""}
                        type="select"
                        options={CONSTRUCTION_OPTIONS}
                        inferred={INFERRED_FIELDS.has("construction_type")}
                        onSave={(v) => handleSaveSpec("construction_type", v)}
                        editRef={(ref) => { fieldRefs.current.construction_type = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.zoning = el; }}>
                      <InlineEdit
                        label="Zoning"
                        value={tc?.zoning ?? ""}
                        type="text"
                        inferred={INFERRED_FIELDS.has("zoning")}
                        onSave={(v) => handleSaveSpec("zoning", v)}
                        editRef={(ref) => { fieldRefs.current.zoning = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.lot_size_acres = el; }}>
                      <InlineEdit
                        label="Lot Size"
                        value={tc?.lot_size_acres ?? 0}
                        type="number"
                        unit="acres"
                        onSave={(v) => handleSaveSpec("lot_size_acres", v)}
                        editRef={(ref) => { fieldRefs.current.lot_size_acres = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.sprinkler = el; }}>
                      <InlineEdit
                        label="Sprinkler"
                        value={tc?.sprinkler ?? false}
                        type="toggle"
                        onSave={(v) => handleSaveSpec("sprinkler", v)}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.power_supply = el; }}>
                      <InlineEdit
                        label="Power Supply"
                        value={tc?.power_supply ?? ""}
                        type="select"
                        options={POWER_OPTIONS}
                        inferred={INFERRED_FIELDS.has("power_supply")}
                        onSave={(v) => handleSaveSpec("power_supply", v)}
                        editRef={(ref) => { fieldRefs.current.power_supply = ref; }}
                      />
                    </div>
                    <div ref={(el) => { fieldElementRefs.current.parking_spaces = el; }}>
                      <InlineEdit
                        label="Parking Spaces"
                        value={tc?.parking_spaces ?? 0}
                        type="number"
                        onSave={(v) => handleSaveSpec("parking_spaces", v)}
                        editRef={(ref) => { fieldRefs.current.parking_spaces = ref; }}
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* ---- Configuration Tab ---- */}
            {activeTab === "config" && (
              <motion.div
                key="config"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="space-y-6">
                  {/* Space & Access */}
                  <div className="rounded-xl border border-slate-200 bg-white p-6">
                    <h3 className="text-lg font-semibold text-slate-900 mb-4">
                      Space & Access
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1">
                      <div ref={(el) => { fieldElementRefs.current.available_sqft = el; }}>
                        <InlineEdit
                          label="Available Space"
                          value={tc?.available_sqft ?? warehouse.available_sqft ?? 0}
                          type="number"
                          unit="sqft"
                          onSave={(v) => handleSaveConfig("available_sqft", v)}
                          editRef={(ref) => { fieldRefs.current.available_sqft = ref; }}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.min_rentable_sqft = el; }}>
                        <InlineEdit
                          label="Minimum Rentable"
                          value={tc?.min_rentable_sqft ?? warehouse.min_sqft ?? 0}
                          type="number"
                          unit="sqft"
                          onSave={(v) =>
                            handleSaveConfig("min_rentable_sqft", v)
                          }
                          editRef={(ref) => { fieldRefs.current.min_rentable_sqft = ref; }}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.activity_tier = el; }}>
                        <InlineEdit
                          label="Allowed Use"
                          value={tc?.activity_tier ?? "active"}
                          type="select"
                          options={ACTIVITY_TIER_OPTIONS}
                          onSave={(v) => handleSaveConfig("activity_tier", v)}
                          editRef={(ref) => { fieldRefs.current.activity_tier = ref; }}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.has_office = el; }}>
                        <InlineEdit
                          label="Has Office Space"
                          value={tc?.has_office ?? false}
                          type="toggle"
                          onSave={(v) => handleSaveConfig("has_office", v)}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.weekend_access = el; }}>
                        <InlineEdit
                          label="Weekend Access"
                          value={tc?.weekend_access ?? false}
                          type="toggle"
                          onSave={(v) => handleSaveConfig("weekend_access", v)}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.access_24_7 = el; }}>
                        <InlineEdit
                          label="24/7 Access"
                          value={tc?.access_24_7 ?? false}
                          type="toggle"
                          onSave={(v) => handleSaveConfig("access_24_7", v)}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.min_term_months = el; }}>
                        <InlineEdit
                          label="Minimum Term"
                          value={tc?.min_term_months ?? 3}
                          type="number"
                          unit="months"
                          onSave={(v) =>
                            handleSaveConfig("min_term_months", Number(v))
                          }
                          editRef={(ref) => { fieldRefs.current.min_term_months = ref; }}
                        />
                      </div>
                      <div ref={(el) => { fieldElementRefs.current.available_from = el; }}>
                        <InlineEdit
                          label="Available From"
                          value={tc?.available_from ?? ""}
                          type="date"
                          onSave={(v) => handleSaveConfig("available_from", v)}
                          editRef={(ref) => { fieldRefs.current.available_from = ref; }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Certifications — demand-triggered only.
                      They appear here after the supplier responds to an AI
                      suggestion about a specific certification. Not part of
                      profile completeness. Only certifications that have been
                      explicitly answered (value is not null/undefined) are
                      shown. If none have been answered the entire sub-section
                      is hidden. */}
                  {(() => {
                    const certItems = (
                      [
                        { key: "food_grade", label: "Food Grade" },
                        { key: "fda_registered", label: "FDA Registered" },
                        { key: "hazmat_certified", label: "Hazmat Certified" },
                        { key: "c_tpat", label: "C-TPAT" },
                        { key: "temperature_controlled", label: "Temperature Controlled" },
                        { key: "foreign_trade_zone", label: "Foreign Trade Zone" },
                      ] as const
                    ).filter(({ key }) => tc?.[key] !== undefined && tc?.[key] !== null);

                    if (certItems.length === 0) return null;

                    return (
                      <div className="rounded-xl border border-slate-200 bg-white p-6">
                        <h3 className="text-lg font-semibold text-slate-900 mb-4">
                          Certifications
                        </h3>
                        <div className="space-y-4">
                          {certItems.map(({ key, label }) => {
                            const val = tc?.[key];
                            return (
                              <div
                                key={key}
                                className="flex items-center justify-between py-2"
                              >
                                <span className="text-sm text-slate-600">
                                  {label}
                                </span>
                                <div className="flex gap-2">
                                  {(
                                    [
                                      { v: true, l: "Yes" },
                                      { v: false, l: "No" },
                                      { v: null, l: "Not Sure" },
                                    ] as const
                                  ).map(({ v, l }) => (
                                    <button
                                      key={l}
                                      onClick={() => handleSaveConfig(key, v as any)}
                                      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                                        val === v
                                          ? v === true
                                            ? "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300"
                                            : v === false
                                              ? "bg-red-50 text-red-700 ring-1 ring-red-300"
                                              : "bg-slate-200 text-slate-700 ring-1 ring-slate-300"
                                          : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                                      }`}
                                    >
                                      {l}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </motion.div>
            )}

            {/* ---- Pricing Tab ---- */}
            {activeTab === "pricing" && (
              <motion.div
                key="pricing"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="rounded-xl border border-slate-200 bg-white p-6">
                  <h3 className="text-lg font-semibold text-slate-900 mb-4">
                    Pricing
                  </h3>

                  <div className="divide-y divide-slate-100">
                    {/* Current rate */}
                    <div ref={(el) => { fieldElementRefs.current.target_rate_sqft = el; }}>
                      <InlineEdit
                        label="Your Rate"
                        value={liveRate}
                        type="number"
                        unit="/sqft/mo"
                        onSave={handleSaveRate}
                        editRef={(ref) => { fieldRefs.current.target_rate_sqft = ref; }}
                      />
                    </div>

                    {/* Market range (display only) */}
                    <div className="flex items-center justify-between py-3">
                      <div>
                        <span className="text-sm text-slate-500">
                          Market Range (area median)
                        </span>
                        <p className="text-base text-slate-900 mt-0.5">
                          $0.55 &ndash; $0.95/sqft
                        </p>
                      </div>
                      <TrendingUp className="h-5 w-5 text-slate-400" />
                    </div>
                  </div>

                  {/* Projected Annual Revenue */}
                  <div className="mt-6 rounded-lg bg-emerald-50 border border-emerald-100 p-5">
                    <div className="flex items-center gap-2 mb-1">
                      <DollarSign className="h-5 w-5 text-emerald-600" />
                      <span className="text-sm font-semibold text-emerald-800">
                        Projected Annual Revenue
                      </span>
                    </div>
                    <p className="text-3xl font-bold text-emerald-700">
                      {formatCurrency(projectedAnnual)}
                      <span className="text-base font-normal text-emerald-500">
                        /yr
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-emerald-600">
                      Based on{" "}
                      {(
                        tc?.available_sqft ??
                        warehouse.available_sqft ??
                        0
                      ).toLocaleString()}{" "}
                      sqft at ${liveRate.toFixed(2)}/sqft/mo
                    </p>
                  </div>
                </div>
              </motion.div>
            )}

            {/* ---- Engagements Tab ---- */}
            {activeTab === "engagements" && (
              <motion.div
                key="engagements"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
                  {engagements.length === 0 ? (
                    <div className="p-12 text-center">
                      <Clock className="mx-auto mb-3 h-10 w-10 text-slate-300" />
                      <h3 className="text-base font-semibold text-slate-900">
                        No engagements yet
                      </h3>
                      <p className="mt-1 text-sm text-slate-500">
                        When buyers match with your property, engagements will
                        appear here.
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* Mobile card layout */}
                      <div className="md:hidden divide-y divide-slate-100">
                        {engagements.map((eng) => (
                          <div
                            key={eng.id}
                            onClick={() =>
                              router.push(
                                `/supplier/engagements/${eng.id}`,
                              )
                            }
                            className="p-4 cursor-pointer hover:bg-slate-50 transition-colors"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-sm font-medium text-slate-900">
                                #{eng.id.replace("eng-", "")}
                              </span>
                              <StatusBadge
                                status={eng.status}
                                size="sm"
                              />
                            </div>
                            <div className="grid grid-cols-2 gap-y-1.5 text-sm">
                              <div>
                                <span className="text-slate-500">Use Type</span>
                              </div>
                              <div className="text-right">
                                <span className="text-slate-700 capitalize">{eng.use_type}</span>
                              </div>
                              <div>
                                <span className="text-slate-500">Sqft</span>
                              </div>
                              <div className="text-right">
                                <span className="text-slate-700">{eng.sqft.toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-500">Rate</span>
                              </div>
                              <div className="text-right">
                                <span className="text-slate-700">${eng.supplier_rate.toFixed(2)}</span>
                              </div>
                              <div>
                                <span className="text-slate-500">Term</span>
                              </div>
                              <div className="text-right">
                                <span className="text-slate-700">{eng.term_months}mo</span>
                              </div>
                              <div>
                                <span className="text-slate-500">Date</span>
                              </div>
                              <div className="text-right">
                                <span className="text-slate-700">{formatDate(eng.created_at)}</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Desktop table layout */}
                      <div className="hidden md:block overflow-x-auto">
                        <table className="w-full text-left">
                          <thead>
                            <tr className="border-b border-slate-100 bg-slate-50">
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                                Engagement
                              </th>
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                                Use Type
                              </th>
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">
                                Sqft
                              </th>
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">
                                Rate
                              </th>
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                                Term
                              </th>
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                                Status
                              </th>
                              <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                                Date
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {engagements.map((eng) => (
                              <tr
                                key={eng.id}
                                onClick={() =>
                                  router.push(
                                    `/supplier/engagements/${eng.id}`,
                                  )
                                }
                                className="cursor-pointer hover:bg-slate-50 transition-colors"
                              >
                                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                                  #{eng.id.replace("eng-", "")}
                                </td>
                                <td className="px-4 py-3 text-sm text-slate-600 capitalize">
                                  {eng.use_type}
                                </td>
                                <td className="px-4 py-3 text-sm text-slate-600 text-right">
                                  {eng.sqft.toLocaleString()}
                                </td>
                                <td className="px-4 py-3 text-sm text-slate-600 text-right">
                                  ${eng.supplier_rate.toFixed(2)}
                                </td>
                                <td className="px-4 py-3 text-sm text-slate-600">
                                  {eng.term_months}mo
                                </td>
                                <td className="px-4 py-3">
                                  <StatusBadge
                                    status={eng.status}
                                    size="sm"
                                  />
                                </td>
                                <td className="px-4 py-3 text-sm text-slate-500">
                                  {formatDate(eng.created_at)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              </motion.div>
            )}

            {/* ---- Activity Tab ---- */}
            {activeTab === "activity" && (
              <motion.div
                key="activity"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="rounded-xl border border-slate-200 bg-white p-6">
                  <h3 className="text-lg font-semibold text-slate-900 mb-6">
                    Property Activity
                  </h3>

                  {activity.length > 0 ? (
                    <Timeline
                      events={activity.map((a) => ({
                        id: a.id,
                        type: a.type,
                        description: a.description,
                        timestamp: a.timestamp,
                        completed: true,
                        metadata: a.metadata,
                      }))}
                    />
                  ) : (
                    <div className="py-8 text-center">
                      <Calendar className="mx-auto mb-3 h-8 w-8 text-slate-300" />
                      <p className="text-sm text-slate-500">
                        No activity recorded yet.
                      </p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
