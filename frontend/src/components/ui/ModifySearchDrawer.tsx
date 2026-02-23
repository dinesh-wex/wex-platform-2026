"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  MapPin,
  Ruler,
  Calendar,
  Clock,
  Settings2,
  Box,
  Zap,
  Infinity,
  Loader2,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
export interface SearchIntent {
  location: string;
  sqft: number;
  useType: string;
  goodsType: string;
  timing: string;
  duration: string;
  amenities: string[];
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  currentIntent: SearchIntent;
  onUpdate: (intent: SearchIntent) => Promise<void>;
}

const USE_TYPE_OPTIONS = [
  { value: "storage", label: "Storage" },
  { value: "light_ops", label: "Light Ops" },
  { value: "distribution", label: "Distribution" },
];

const MUST_HAVE_OPTIONS = [
  "Office Space",
  "Dock Doors",
  "High Power",
  "Climate Control",
  "24/7 Access",
  "Sprinkler System",
  "Parking",
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function ModifySearchDrawer({
  isOpen,
  onClose,
  currentIntent,
  onUpdate,
}: Props) {
  const [draft, setDraft] = useState<SearchIntent>(currentIntent);
  const [isImmediate, setIsImmediate] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [durationMonths, setDurationMonths] = useState(6);
  const [isFlexible, setIsFlexible] = useState(false);
  const [updating, setUpdating] = useState(false);

  // Sync draft whenever the drawer opens with fresh data
  useEffect(() => {
    if (isOpen) {
      setDraft(currentIntent);

      // Parse timing state from intent
      if (currentIntent.timing === "Immediately") {
        setIsImmediate(true);
        setStartDate("");
      } else if (currentIntent.timing) {
        setIsImmediate(false);
        // Try to parse a date string back to input value
        const parsed = Date.parse(currentIntent.timing);
        if (!isNaN(parsed)) {
          setStartDate(new Date(parsed).toISOString().split("T")[0]);
        }
      }

      // Parse duration state from intent
      const dMatch = currentIntent.duration.match(/^(\d+)\s*Month/i);
      if (dMatch) {
        setDurationMonths(parseInt(dMatch[1]));
        setIsFlexible(false);
      } else if (currentIntent.duration === "Flexible") {
        setIsFlexible(true);
      }
    }
  }, [isOpen, currentIntent]);

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  async function handleSubmit() {
    setUpdating(true);
    try {
      await onUpdate(draft);
    } finally {
      setUpdating(false);
      onClose();
    }
  }

  const patchDraft = (partial: Partial<SearchIntent>) =>
    setDraft((d) => ({ ...d, ...partial }));

  const toggleAmenity = (item: string) => {
    const has = draft.amenities.includes(item);
    patchDraft({
      amenities: has
        ? draft.amenities.filter((a) => a !== item)
        : [...draft.amenities, item],
    });
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Drawer panel */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col"
          >
            {/* ── HEADER ── */}
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <h2 className="text-xl font-bold text-slate-900">
                Modify Search
              </h2>
              <button
                onClick={onClose}
                className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            {/* ── SCROLLABLE BODY ── */}
            <div className="flex-1 overflow-y-auto p-6 space-y-8">
              {/* Location */}
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                  <MapPin size={14} /> Location
                </label>
                <input
                  type="text"
                  value={draft.location}
                  onChange={(e) => patchDraft({ location: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-slate-900 font-medium outline-none focus:border-emerald-500 transition-colors mt-2"
                  placeholder="e.g. Gardena, CA"
                />
              </div>

              {/* Size */}
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                  <Ruler size={14} /> Size (sqft)
                </label>
                <input
                  type="number"
                  value={draft.sqft}
                  onChange={(e) =>
                    patchDraft({ sqft: parseInt(e.target.value) || 0 })
                  }
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-slate-900 font-medium outline-none focus:border-emerald-500 transition-colors mt-2"
                  min={500}
                  step={500}
                />
              </div>

              {/* Use Type */}
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                  <Box size={14} /> Use Type
                </label>
                <div className="flex gap-2 mt-2">
                  {USE_TYPE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => patchDraft({ useType: opt.value })}
                      className={`flex-1 px-3 py-2.5 rounded-lg text-sm font-bold transition-all ${
                        draft.useType === opt.value
                          ? "bg-emerald-100 text-emerald-700 border-2 border-emerald-300"
                          : "bg-white text-slate-600 border border-slate-200 hover:border-slate-400"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Timeline & Term */}
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                  <Calendar size={14} /> Move-in Date
                </label>
                <div className="space-y-3 mt-2">
                  {/* Immediately shortcut */}
                  <button
                    onClick={() => {
                      setIsImmediate(true);
                      setStartDate("");
                      patchDraft({ timing: "Immediately" });
                    }}
                    className={`w-full flex items-center justify-between p-3 rounded-lg border-2 transition-all text-sm ${
                      isImmediate
                        ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                        : "border-slate-200 hover:border-slate-400 bg-white"
                    }`}
                  >
                    <span className="font-bold flex items-center gap-2">
                      <Zap size={16} /> Immediately
                    </span>
                    {isImmediate && (
                      <div className="w-2.5 h-2.5 bg-emerald-500 rounded-full" />
                    )}
                  </button>

                  {/* Date picker */}
                  <div
                    className={`relative p-3 rounded-lg border-2 transition-all ${
                      !isImmediate && startDate
                        ? "border-emerald-500 bg-white ring-1 ring-emerald-500"
                        : "border-slate-200 bg-white"
                    }`}
                  >
                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">
                      Or select a date
                    </label>
                    <input
                      type="date"
                      value={startDate}
                      min={new Date().toISOString().split("T")[0]}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        setIsImmediate(false);
                        const d = new Date(e.target.value);
                        patchDraft({
                          timing: d.toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          }),
                        });
                      }}
                      className="w-full bg-transparent font-bold text-sm text-slate-900 outline-none cursor-pointer"
                    />
                  </div>
                </div>
              </div>

              {/* Term Length */}
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                  <Clock size={14} /> Term Length
                </label>
                <div className="mt-2">
                  <div
                    className={`bg-slate-50 rounded-xl border-2 p-6 text-center transition-all ${
                      isFlexible
                        ? "border-slate-200 opacity-50"
                        : "border-emerald-500"
                    }`}
                  >
                    <div className="text-3xl font-bold text-slate-900 mb-2">
                      {isFlexible ? (
                        <span className="text-slate-400">Flexible</span>
                      ) : (
                        <>
                          {durationMonths}{" "}
                          <span className="text-sm text-slate-400 font-medium">
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
                        const v = parseInt(e.target.value);
                        setDurationMonths(v);
                        setIsFlexible(false);
                        patchDraft({ duration: `${v} Months` });
                      }}
                      disabled={isFlexible}
                      className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-600"
                    />
                    <div className="flex justify-between text-[10px] text-slate-400 font-bold mt-1">
                      <span>1</span>
                      <span>12</span>
                      <span>24</span>
                      <span>36</span>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      const next = !isFlexible;
                      setIsFlexible(next);
                      patchDraft({
                        duration: next
                          ? "Flexible"
                          : `${durationMonths} Months`,
                      });
                    }}
                    className={`mt-3 w-full flex items-center justify-center gap-2 p-2.5 rounded-lg border-2 font-bold text-xs transition-all ${
                      isFlexible
                        ? "bg-slate-800 text-white border-slate-800"
                        : "bg-white text-slate-500 border-slate-200 hover:border-slate-400"
                    }`}
                  >
                    <Infinity size={14} /> I&apos;m Flexible
                  </button>
                </div>
              </div>

              {/* Must-Haves */}
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                  <Settings2 size={14} /> Must-Haves
                </label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {MUST_HAVE_OPTIONS.map((req) => {
                    const selected = draft.amenities.includes(req);
                    return (
                      <button
                        key={req}
                        onClick={() => toggleAmenity(req)}
                        className={`px-3 py-1.5 rounded-md text-sm font-bold transition-all ${
                          selected
                            ? "bg-emerald-100 text-emerald-700 border border-emerald-200"
                            : "bg-white text-slate-600 border border-slate-200 hover:border-slate-400"
                        }`}
                      >
                        {req}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* ── STICKY FOOTER ── */}
            <div className="p-6 border-t border-slate-100 bg-white">
              <button
                onClick={handleSubmit}
                disabled={updating || !draft.location}
                className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-4 rounded-xl shadow-lg shadow-emerald-600/20 transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {updating ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    Updating Matches...
                  </>
                ) : (
                  "Update Matches"
                )}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
