"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  MapPin,
  Ruler,
  Thermometer,
  Truck,
  DollarSign,
  TrendingUp,
  ToggleLeft,
  ToggleRight,
  Loader2,
  AlertCircle,
  Shield,
  Send,
  Zap,
  CheckCircle2,
  Calendar,
  User,
  Camera,
  ClipboardCheck,
  X,
  Pencil,
  ImagePlus,
  ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface WarehouseDetail {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  total_sqft: number;
  available_sqft: number;
  status: string;
  supplier_rate: number | null;
  image_url: string | null;
  truth_core: TruthCore | null;
  placements: Placement[];
}

interface TruthCore {
  address: string;
  total_sqft: string;
  clear_height: string;
  dock_doors: string;
  climate_control: string;
  available_sqft: string;
  yard_space: string;
  power_amps: string;
  supplier_rate: string;
  [key: string]: string;
}

interface Placement {
  id: string;
  buyer_name: string;
  sqft: number;
  rate: number;
  start_date: string;
  status: string;
}

interface EnrichmentQuestion {
  id: string;
  question: string;
  type: string;
  priority: number;
}

interface ProfileCompletenessData {
  total_questions: number;
  answered: number;
  percentage: number;
  missing: string[];
}

interface EnrichmentHistoryItem {
  id: string;
  question_id: string;
  question_text: string;
  response: string;
  created_at: string | null;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function WarehouseDetailPage() {
  const params = useParams();
  const warehouseId = params.id as string;

  const [warehouse, setWarehouse] = useState<WarehouseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const [updateText, setUpdateText] = useState("");
  const [updating, setUpdating] = useState(false);
  const [updateSuccess, setUpdateSuccess] = useState(false);

  // Enrichment state
  const [nextQuestion, setNextQuestion] = useState<EnrichmentQuestion | null>(null);
  const [enrichmentAnswer, setEnrichmentAnswer] = useState("");
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [answerSuccess, setAnswerSuccess] = useState(false);
  const [completeness, setCompleteness] = useState<ProfileCompletenessData | null>(null);
  const [enrichmentHistory, setEnrichmentHistory] = useState<EnrichmentHistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // Photo upload state
  const [photoUrl, setPhotoUrl] = useState("");
  const [photoUrls, setPhotoUrls] = useState<string[]>([]);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const [existingPhotos, setExistingPhotos] = useState<string[]>([]);

  const loadEnrichmentData = useCallback(async () => {
    try {
      const [questionRes, completenessRes, historyRes] = await Promise.allSettled([
        api.getNextEnrichmentQuestion(warehouseId),
        api.getProfileCompleteness(warehouseId),
        api.getEnrichmentHistory(warehouseId),
      ]);
      if (questionRes.status === "fulfilled") {
        setNextQuestion(questionRes.value.next_question);
      }
      if (completenessRes.status === "fulfilled") {
        setCompleteness(completenessRes.value);
      }
      if (historyRes.status === "fulfilled") {
        setEnrichmentHistory(historyRes.value.history || []);
      }
    } catch {
      // Fallback demo data for enrichment
      setCompleteness({ total_questions: 10, answered: 3, percentage: 30, missing: ["photos", "ceiling_height", "loading_docks", "power", "security", "parking", "access_hours"] });
      setNextQuestion({ id: "ceiling_height", question: "What's the clear ceiling height in your warehouse?", type: "text", priority: 2 });
      setEnrichmentHistory([
        { id: "1", question_id: "photos", question_text: "Can you share a few photos of your warehouse?", response: "Photos uploaded: 3 images", created_at: "2026-02-15T10:30:00Z" },
        { id: "2", question_id: "loading_docks", question_text: "How many loading dock doors does your space have?", response: "8 dock-high, 2 grade-level", created_at: "2026-02-12T14:15:00Z" },
        { id: "3", question_id: "office_sqft", question_text: "Does your space include office area?", response: "Yes, approximately 2,500 sqft", created_at: "2026-02-08T09:00:00Z" },
      ]);
    }
  }, [warehouseId]);

  useEffect(() => {
    loadWarehouse();
    loadEnrichmentData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouseId]);

  async function loadWarehouse() {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getWarehouse(warehouseId);
      setWarehouse(data);
    } catch (err: any) {
      setError(err.message || "Failed to load warehouse");
      // Demo data
      setWarehouse({
        id: warehouseId,
        name: "Downtown Distribution Center",
        address: "1200 Industrial Blvd",
        city: "Dallas",
        state: "TX",
        zip_code: "75201",
        total_sqft: 50000,
        available_sqft: 35000,
        status: "active",
        supplier_rate: 8.5,
        image_url: null,
        truth_core: {
          address: "1200 Industrial Blvd, Dallas, TX 75201",
          total_sqft: "50,000 sqft",
          clear_height: "32 ft",
          dock_doors: "8 dock-high, 2 grade-level",
          climate_control: "Partial - 10,000 sqft cooled",
          available_sqft: "35,000 sqft",
          yard_space: "Yes, fenced",
          power_amps: "800A, 3-phase",
          supplier_rate: "$8.50/sqft/mo",
        },
        placements: [
          {
            id: "pl-1",
            buyer_name: "TechLogistics Co.",
            sqft: 15000,
            rate: 11.48,
            start_date: "2025-01-15",
            status: "active",
          },
        ],
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle() {
    if (!warehouse) return;
    const newStatus = warehouse.status === "active" ? "inactive" : "active";
    setToggling(true);
    try {
      await api.toggleWarehouse(warehouse.id, newStatus);
      setWarehouse((prev) => (prev ? { ...prev, status: newStatus } : null));
    } catch {
      // Optimistic update for prototype
      setWarehouse((prev) => (prev ? { ...prev, status: newStatus } : null));
    } finally {
      setToggling(false);
    }
  }

  async function handleUpdate() {
    if (!updateText.trim()) return;
    setUpdating(true);
    try {
      await api.sendActivationMessage({
        warehouse_id: warehouseId,
        message: updateText,
        type: "update",
      });
    } catch {
      // Prototype: just show success
    }
    setUpdating(false);
    setUpdateSuccess(true);
    setUpdateText("");
    setTimeout(() => setUpdateSuccess(false), 3000);
  }

  async function handleEnrichmentSubmit() {
    if (!enrichmentAnswer.trim() || !nextQuestion) return;
    setSubmittingAnswer(true);
    try {
      const result = await api.submitEnrichmentResponse(warehouseId, {
        question_id: nextQuestion.id,
        response: enrichmentAnswer,
      });
      setNextQuestion(result.next_question || null);
      setEnrichmentAnswer("");
      setAnswerSuccess(true);
      setTimeout(() => setAnswerSuccess(false), 3000);
      // Refresh completeness + history
      loadEnrichmentData();
    } catch {
      // Optimistic: advance to next question for demo
      setAnswerSuccess(true);
      setEnrichmentAnswer("");
      setTimeout(() => setAnswerSuccess(false), 3000);
    } finally {
      setSubmittingAnswer(false);
    }
  }

  function addPhotoUrl() {
    if (!photoUrl.trim()) return;
    if (!photoUrls.includes(photoUrl.trim())) {
      setPhotoUrls((prev) => [...prev, photoUrl.trim()]);
    }
    setPhotoUrl("");
  }

  function removePhotoUrl(url: string) {
    setPhotoUrls((prev) => prev.filter((u) => u !== url));
  }

  function removeExistingPhoto(url: string) {
    setExistingPhotos((prev) => prev.filter((u) => u !== url));
  }

  async function handlePhotoUpload() {
    if (photoUrls.length === 0) return;
    setUploadingPhotos(true);
    try {
      await api.uploadPhotos(warehouseId, photoUrls);
      setExistingPhotos((prev) => [...prev, ...photoUrls]);
      setPhotoUrls([]);
      loadEnrichmentData();
    } catch {
      // Optimistic for prototype
      setExistingPhotos((prev) => [...prev, ...photoUrls]);
      setPhotoUrls([]);
    } finally {
      setUploadingPhotos(false);
    }
  }

  function formatCurrency(amount: number): string {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
  }

  function formatNumber(num: number): string {
    return new Intl.NumberFormat("en-US").format(num);
  }

  // -- Loading -------------------------------------------------------
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-4" />
          <p className="text-slate-400">Loading warehouse details...</p>
        </div>
      </div>
    );
  }

  if (!warehouse) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-4" />
          <p className="text-white font-medium">Warehouse not found</p>
          <Link href="/supplier" className="text-blue-400 text-sm mt-2 inline-block hover:underline">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  const monthlyRevenue = (warehouse.supplier_rate || 0) * warehouse.available_sqft;
  const annualRevenue = monthlyRevenue * 12;
  const tc = warehouse.truth_core;
  const profilePct = completeness?.percentage ?? 0;

  const truthCoreFields = [
    { label: "Address", value: tc?.address, icon: <MapPin className="w-4 h-4" /> },
    { label: "Total Sq Ft", value: tc?.total_sqft, icon: <Ruler className="w-4 h-4" /> },
    { label: "Clear Height", value: tc?.clear_height, icon: <Building2 className="w-4 h-4" /> },
    { label: "Dock Doors", value: tc?.dock_doors, icon: <Truck className="w-4 h-4" /> },
    { label: "Climate Control", value: tc?.climate_control, icon: <Thermometer className="w-4 h-4" /> },
    { label: "Available Sq Ft", value: tc?.available_sqft, icon: <Ruler className="w-4 h-4" /> },
    { label: "Yard Space", value: tc?.yard_space, icon: <Building2 className="w-4 h-4" /> },
    { label: "Power (Amps)", value: tc?.power_amps, icon: <Zap className="w-4 h-4" /> },
    { label: "Supplier Rate", value: tc?.supplier_rate, icon: <DollarSign className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/supplier" className="text-slate-400 hover:text-slate-200 transition-colors">
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-white">
                  W<span className="text-blue-400">Ex</span>
                </h1>
                <span className="text-slate-600">|</span>
                <span className="text-sm font-medium text-slate-400">Warehouse Detail</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Error Banner */}
        {error && (
          <div className="bg-amber-950/50 border border-amber-800 rounded-lg px-4 py-3 flex items-start gap-3 mb-6">
            <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-300">Demo mode</p>
              <p className="text-xs text-amber-500 mt-1">Showing demo data. Backend not connected.</p>
            </div>
          </div>
        )}

        {/* Hero Section */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden mb-8">
          <div className="h-48 bg-gradient-to-br from-gray-800 to-gray-900 relative">
            {warehouse.image_url ? (
              <img
                src={warehouse.image_url}
                alt={warehouse.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Building2 className="w-20 h-20 text-gray-700" />
              </div>
            )}
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-6">
              <h2 className="text-2xl font-bold text-white">{warehouse.name}</h2>
              <div className="flex items-center gap-1.5 text-slate-300 text-sm mt-1">
                <MapPin className="w-4 h-4" />
                <span>
                  {warehouse.address}, {warehouse.city}, {warehouse.state} {warehouse.zip_code}
                </span>
              </div>
            </div>
          </div>

          {/* Toggle + Stats Bar */}
          <div className="px-6 py-4 flex items-center justify-between border-b border-gray-800">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-slate-400">Listing Status:</span>
                <button
                  onClick={handleToggle}
                  disabled={toggling}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-all ${
                    warehouse.status === "active"
                      ? "bg-green-900/50 text-green-400 hover:bg-green-900/70 border border-green-800"
                      : "bg-red-900/50 text-red-400 hover:bg-red-900/70 border border-red-800"
                  }`}
                >
                  {toggling ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : warehouse.status === "active" ? (
                    <ToggleRight className="w-5 h-5" />
                  ) : (
                    <ToggleLeft className="w-5 h-5" />
                  )}
                  {warehouse.status === "active" ? "Active - Accepting Placements" : "Inactive - Not Listed"}
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Shield className="w-4 h-4 text-emerald-500" />
              <span>WEx Guaranteed</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column: Truth Core + Enrichment */}
          <div className="lg:col-span-2 space-y-6">
            {/* Truth Core */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="bg-gray-800 px-6 py-4">
                <h3 className="text-white font-semibold">Truth Core</h3>
                <p className="text-slate-500 text-xs mt-0.5">Verified warehouse description record</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-gray-800">
                <div className="divide-y divide-gray-800">
                  {truthCoreFields.slice(0, 5).map((field) => (
                    <div key={field.label} className="px-5 py-3.5 flex items-center gap-3">
                      <div className="p-1.5 rounded-md bg-blue-900/50 text-blue-400">{field.icon}</div>
                      <div>
                        <p className="text-xs text-slate-500">{field.label}</p>
                        <p className="text-sm font-medium text-slate-200">{field.value || "N/A"}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="divide-y divide-gray-800">
                  {truthCoreFields.slice(5).map((field) => (
                    <div key={field.label} className="px-5 py-3.5 flex items-center gap-3">
                      <div className="p-1.5 rounded-md bg-blue-900/50 text-blue-400">{field.icon}</div>
                      <div>
                        <p className="text-xs text-slate-500">{field.label}</p>
                        <p className="text-sm font-medium text-slate-200">{field.value || "N/A"}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Active Placements */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-800">
                <h3 className="font-semibold text-white">Active Placements</h3>
                <p className="text-xs text-slate-500 mt-0.5">Current tenants placed by WEx</p>
              </div>
              {warehouse.placements && warehouse.placements.length > 0 ? (
                <div className="divide-y divide-gray-800">
                  {warehouse.placements.map((p) => (
                    <div key={p.id} className="px-6 py-4 flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="bg-green-900/50 p-2 rounded-lg">
                          <User className="w-4 h-4 text-green-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-white">{p.buyer_name}</p>
                          <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
                            <span className="flex items-center gap-1">
                              <Ruler className="w-3 h-3" />
                              {formatNumber(p.sqft)} sqft
                            </span>
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              Since {new Date(p.start_date).toLocaleDateString()}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-green-400">
                          {formatCurrency(p.rate * p.sqft)}/mo
                        </p>
                        <span className="inline-flex items-center gap-1 text-xs text-green-400 bg-green-900/30 px-2 py-0.5 rounded-full">
                          <CheckCircle2 className="w-3 h-3" />
                          {p.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="px-6 py-10 text-center">
                  <User className="w-8 h-8 text-gray-700 mx-auto mb-2" />
                  <p className="text-sm text-slate-500">No active placements yet</p>
                  <p className="text-xs text-slate-600 mt-1">
                    WEx is matching qualified tenants to your space
                  </p>
                </div>
              )}
            </div>

            {/* Profile Completeness + Current Question */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-blue-900/60 to-indigo-900/60 px-6 py-4 border-b border-gray-800">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <ClipboardCheck className="w-5 h-5 text-blue-400" />
                    <div>
                      <h3 className="text-white font-semibold">Profile Completeness</h3>
                      <p className="text-blue-300/70 text-xs mt-0.5">
                        Complete your profile to rank higher in buyer searches
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-blue-400">{profilePct}%</p>
                  </div>
                </div>
                {/* Progress bar */}
                <div className="mt-3 w-full bg-gray-800 rounded-full h-2.5">
                  <div
                    className="bg-gradient-to-r from-blue-500 to-blue-400 rounded-full h-2.5 transition-all duration-500"
                    style={{ width: `${profilePct}%` }}
                  />
                </div>
                <div className="flex justify-between mt-1.5">
                  <span className="text-xs text-slate-500">
                    {completeness?.answered ?? 0} of {completeness?.total_questions ?? 10} answered
                  </span>
                  {profilePct === 100 && (
                    <span className="text-xs text-green-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> All done!
                    </span>
                  )}
                </div>
              </div>

              {/* Current enrichment question */}
              {nextQuestion && (
                <div className="px-6 py-5">
                  <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide font-medium">
                    Quick Question
                  </p>
                  <p className="text-sm text-slate-200 mb-4">{nextQuestion.question}</p>
                  {answerSuccess && (
                    <div className="flex items-center gap-2 text-sm text-green-400 bg-green-900/30 border border-green-800 rounded-lg px-4 py-2.5 mb-3">
                      <CheckCircle2 className="w-4 h-4" />
                      Answer saved! Your profile has been updated.
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <input
                      type="text"
                      value={enrichmentAnswer}
                      onChange={(e) => setEnrichmentAnswer(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleEnrichmentSubmit();
                      }}
                      placeholder="Type your answer..."
                      className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <button
                      onClick={handleEnrichmentSubmit}
                      disabled={!enrichmentAnswer.trim() || submittingAnswer}
                      className="bg-blue-600 text-white px-5 py-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium"
                    >
                      {submittingAnswer ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <>
                          Submit
                          <ChevronRight className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}

              {!nextQuestion && profilePct === 100 && (
                <div className="px-6 py-8 text-center">
                  <CheckCircle2 className="w-10 h-10 text-green-400 mx-auto mb-3" />
                  <p className="text-sm font-medium text-white">Profile 100% complete</p>
                  <p className="text-xs text-slate-500 mt-1">
                    Your warehouse is fully enriched and ranks highest in buyer searches.
                  </p>
                </div>
              )}
            </div>

            {/* Photo Upload Section */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-800">
                <div className="flex items-center gap-3">
                  <Camera className="w-5 h-5 text-blue-400" />
                  <div>
                    <h3 className="font-semibold text-white">Photos</h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Add photos to help buyers visualize your space
                    </p>
                  </div>
                </div>
              </div>
              <div className="px-6 py-5">
                {/* Existing photos grid */}
                {existingPhotos.length > 0 && (
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    {existingPhotos.map((url, idx) => (
                      <div key={idx} className="relative group aspect-video bg-gray-800 rounded-lg overflow-hidden">
                        <img
                          src={url}
                          alt={`Warehouse photo ${idx + 1}`}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                        <button
                          onClick={() => removeExistingPhoto(url)}
                          className="absolute top-2 right-2 bg-red-600 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Drag-drop area / URL input */}
                <div className="border-2 border-dashed border-gray-700 rounded-xl p-6 text-center mb-4 hover:border-blue-600 transition-colors">
                  <ImagePlus className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">
                    Add photo URLs below
                  </p>
                  <p className="text-xs text-slate-600 mt-1">
                    Direct upload coming in Phase 2
                  </p>
                </div>

                {/* URL input */}
                <div className="flex items-center gap-3 mb-3">
                  <input
                    type="url"
                    value={photoUrl}
                    onChange={(e) => setPhotoUrl(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") addPhotoUrl();
                    }}
                    placeholder="Paste image URL..."
                    className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <button
                    onClick={addPhotoUrl}
                    disabled={!photoUrl.trim()}
                    className="bg-gray-800 text-slate-300 px-4 py-2.5 rounded-xl hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm border border-gray-700"
                  >
                    Add
                  </button>
                </div>

                {/* Staged URLs */}
                {photoUrls.length > 0 && (
                  <div className="space-y-2 mb-4">
                    {photoUrls.map((url, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between bg-gray-800/50 rounded-lg px-3 py-2 text-xs"
                      >
                        <span className="text-slate-400 truncate mr-3">{url}</span>
                        <button
                          onClick={() => removePhotoUrl(url)}
                          className="text-red-400 hover:text-red-300 flex-shrink-0"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={handlePhotoUpload}
                      disabled={uploadingPhotos}
                      className="w-full bg-blue-600 text-white py-2.5 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 text-sm font-medium flex items-center justify-center gap-2"
                    >
                      {uploadingPhotos ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <>
                          <Camera className="w-4 h-4" />
                          Upload {photoUrls.length} Photo{photoUrls.length !== 1 ? "s" : ""}
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Enrichment History */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="w-full px-6 py-4 border-b border-gray-800 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Pencil className="w-4 h-4 text-slate-400" />
                  <div className="text-left">
                    <h3 className="font-semibold text-white text-sm">Enrichment History</h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {enrichmentHistory.length} question{enrichmentHistory.length !== 1 ? "s" : ""} answered
                    </p>
                  </div>
                </div>
                <ChevronRight
                  className={`w-5 h-5 text-slate-500 transition-transform ${showHistory ? "rotate-90" : ""}`}
                />
              </button>
              {showHistory && (
                <div className="divide-y divide-gray-800">
                  {enrichmentHistory.length > 0 ? (
                    enrichmentHistory.map((item) => (
                      <div key={item.id} className="px-6 py-4">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <p className="text-xs text-slate-500 mb-1">{item.question_text}</p>
                            <p className="text-sm text-white">{item.response}</p>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            {item.created_at && (
                              <span className="text-xs text-slate-600">
                                {new Date(item.created_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="px-6 py-8 text-center">
                      <p className="text-sm text-slate-500">No enrichment responses yet</p>
                      <p className="text-xs text-slate-600 mt-1">
                        Answer questions above to build your profile
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Update Chat Section */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-800">
                <h3 className="font-semibold text-white">Update Your Listing</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Tell the WEx agent what you&apos;d like to change
                </p>
              </div>
              <div className="px-6 py-4">
                {updateSuccess && (
                  <div className="flex items-center gap-2 text-sm text-green-400 bg-green-900/30 border border-green-800 rounded-lg px-4 py-2.5 mb-3">
                    <CheckCircle2 className="w-4 h-4" />
                    Update request sent to WEx agent
                  </div>
                )}
                <div className="flex items-center gap-3">
                  <input
                    type="text"
                    value={updateText}
                    onChange={(e) => setUpdateText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleUpdate();
                    }}
                    placeholder='e.g., "Update my rate to $9.00/sqft" or "Add forklift availability"'
                    className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <button
                    onClick={handleUpdate}
                    disabled={!updateText.trim() || updating}
                    className="bg-blue-600 text-white p-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {updating ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Rate Card + Revenue + Profile */}
          <div className="space-y-6">
            {/* Profile Completeness Mini Card */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-indigo-900/60 to-blue-900/60 px-5 py-4">
                <div className="flex items-center gap-2">
                  <ClipboardCheck className="w-5 h-5 text-blue-400" />
                  <h3 className="text-white font-semibold text-sm">Profile Score</h3>
                </div>
              </div>
              <div className="p-5">
                <div className="flex items-end gap-2 mb-3">
                  <p className="text-3xl font-bold text-blue-400">{profilePct}%</p>
                  <p className="text-sm text-slate-500 mb-1">complete</p>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-2 mb-3">
                  <div
                    className="bg-gradient-to-r from-blue-500 to-blue-400 rounded-full h-2 transition-all duration-500"
                    style={{ width: `${profilePct}%` }}
                  />
                </div>
                {profilePct < 100 ? (
                  <p className="text-xs text-slate-500">
                    Answer {completeness?.total_questions ? completeness.total_questions - (completeness?.answered ?? 0) : "a few"} more questions to boost your ranking
                  </p>
                ) : (
                  <p className="text-xs text-green-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    Maximum visibility in buyer searches
                  </p>
                )}
              </div>
            </div>

            {/* Rate Card */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-blue-800 to-blue-900 px-5 py-4">
                <div className="flex items-center gap-2">
                  <DollarSign className="w-5 h-5 text-white" />
                  <h3 className="text-white font-semibold text-sm">Rate Card</h3>
                </div>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <p className="text-xs text-slate-500 mb-1">Your Supplier Rate</p>
                  <p className="text-3xl font-bold text-white">
                    ${warehouse.supplier_rate?.toFixed(2) || "0.00"}
                    <span className="text-sm font-normal text-slate-500">/sqft/mo</span>
                  </p>
                </div>
                <div className="border-t border-gray-800 pt-3">
                  <p className="text-xs text-slate-500 mb-1">WEx Buyer Rate (est.)</p>
                  <p className="text-xl font-semibold text-slate-300">
                    ${((warehouse.supplier_rate || 0) * 1.35).toFixed(2)}
                    <span className="text-sm font-normal text-slate-500">/sqft/mo</span>
                  </p>
                  <p className="text-xs text-slate-600 mt-1">
                    Includes WEx clearing fee, insurance, and management
                  </p>
                </div>
              </div>
            </div>

            {/* Revenue Projection */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-green-800 to-emerald-900 px-5 py-4">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-white" />
                  <h3 className="text-white font-semibold text-sm">Revenue Projection</h3>
                </div>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <p className="text-xs text-slate-500 mb-1">Monthly Revenue</p>
                  <p className="text-2xl font-bold text-green-400">{formatCurrency(monthlyRevenue)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Annual Revenue</p>
                  <p className="text-xl font-semibold text-green-400">{formatCurrency(annualRevenue)}</p>
                </div>
                <div className="border-t border-gray-800 pt-3 text-xs text-slate-500">
                  Based on {formatNumber(warehouse.available_sqft)} available sqft at $
                  {warehouse.supplier_rate?.toFixed(2)}/sqft/mo
                </div>
                <div className="flex items-center gap-2 bg-emerald-900/30 rounded-lg px-3 py-2 border border-emerald-800">
                  <Shield className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs text-emerald-400">
                    Protected by WEx Occupancy Guarantee
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Stats */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 shadow-sm p-5">
              <h4 className="text-sm font-medium text-white mb-3">Quick Stats</h4>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-500">Total Space</span>
                  <span className="text-sm font-medium text-white">
                    {formatNumber(warehouse.total_sqft)} sqft
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-500">Available</span>
                  <span className="text-sm font-medium text-white">
                    {formatNumber(warehouse.available_sqft)} sqft
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-500">Occupancy</span>
                  <span className="text-sm font-medium text-white">
                    {Math.round(
                      ((warehouse.total_sqft - warehouse.available_sqft) / warehouse.total_sqft) * 100
                    )}
                    %
                  </span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-2">
                  <div
                    className="bg-blue-500 rounded-full h-2 transition-all"
                    style={{
                      width: `${Math.round(
                        ((warehouse.total_sqft - warehouse.available_sqft) / warehouse.total_sqft) * 100
                      )}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
