"use client";

import { useState, useRef, useEffect, useCallback, useImperativeHandle } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Edit2, Check, X, Loader2 } from "lucide-react";

export interface InlineEditHandle {
  startEdit: () => void;
}

interface InlineEditProps {
  value: string | number | boolean;
  label: string;
  type?: "text" | "number" | "toggle" | "select" | "date";
  options?: { value: string; label: string }[];
  inferred?: boolean;
  unit?: string;
  onSave: (newValue: string | number | boolean) => void | Promise<void>;
  onConfirm?: () => void;
  editRef?: React.Ref<InlineEditHandle>;
}

export default function InlineEdit({
  value,
  label,
  type = "text",
  options,
  inferred = false,
  unit,
  onSave,
  onConfirm,
  editRef,
}: InlineEditProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(String(value));
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement | HTMLSelectElement>(null);

  // Sync draft when value changes externally
  useEffect(() => {
    if (!editing) setDraft(String(value));
  }, [value, editing]);

  // Auto-focus input when entering edit mode
  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      if (inputRef.current instanceof HTMLInputElement) {
        inputRef.current.select();
      }
    }
  }, [editing]);

  const startEditing = useCallback(() => {
    if (type === "toggle") return;
    setDraft(String(value));
    setEditing(true);
  }, [type, value]);

  // Expose startEdit to parent via editRef
  useImperativeHandle(editRef, () => ({
    startEdit: () => {
      setDraft(String(value));
      setEditing(true);
    },
  }), [value]);

  const cancel = useCallback(() => {
    setEditing(false);
    setDraft(String(value));
  }, [value]);

  const save = useCallback(async () => {
    const parsed: string | number =
      type === "number" ? Number(draft) : draft;

    setSaving(true);
    try {
      await onSave(parsed);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }, [draft, type, onSave]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        save();
      }
      if (e.key === "Escape") {
        cancel();
      }
    },
    [save, cancel],
  );

  const handleToggle = useCallback(async () => {
    const newVal = !value;
    setSaving(true);
    try {
      await onSave(newVal);
    } finally {
      setSaving(false);
    }
  }, [value, onSave]);

  // ---- Toggle type ----
  if (type === "toggle") {
    const isOn = Boolean(value);
    return (
      <div className="flex items-center justify-between gap-4 py-2 group">
        <span className="text-sm text-slate-500">{label}</span>

        <div className="flex items-center gap-2">
          {inferred && (
            <span className="text-xs text-amber-500 font-medium">
              (inferred)
            </span>
          )}

          <button
            type="button"
            role="switch"
            aria-checked={isOn}
            disabled={saving}
            onClick={handleToggle}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 ${
              isOn ? "bg-emerald-500" : "bg-slate-300"
            } ${saving ? "opacity-60 cursor-wait" : ""}`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ease-in-out ${
                isOn ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>

          {inferred && onConfirm && (
            <button
              type="button"
              onClick={onConfirm}
              className="text-xs font-medium text-emerald-600 border border-emerald-300 rounded px-2 py-0.5 hover:bg-emerald-50 transition-colors"
            >
              Confirm
            </button>
          )}
        </div>
      </div>
    );
  }

  // ---- Date type (always-visible, no edit/display toggle) ----
  if (type === "date") {
    const isImmediate = !value || String(value).toLowerCase() === "immediately" || String(value) === "";
    return (
      <div className="flex items-center justify-between gap-4 py-2 group">
        <span className="text-sm text-slate-500">{label}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={async () => {
              setSaving(true);
              try { await onSave("Immediately"); } finally { setSaving(false); }
            }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              isImmediate
                ? "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300"
                : "bg-slate-50 text-slate-500 hover:bg-slate-100"
            }`}
          >
            Immediately
          </button>
          <input
            type="date"
            value={isImmediate ? "" : String(value)}
            onChange={async (e) => {
              const v = e.target.value;
              if (v) {
                setSaving(true);
                try { await onSave(v); } finally { setSaving(false); }
              }
            }}
            disabled={saving}
            className={`rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent disabled:opacity-60 ${
              !isImmediate ? "ring-1 ring-emerald-300 bg-emerald-50" : "bg-white"
            }`}
          />
        </div>
      </div>
    );
  }

  // ---- Display mode ----
  if (!editing) {
    const displayValue = (() => {
      if (type === "select" && options) {
        const match = options.find((o) => o.value === String(value));
        return match ? match.label : String(value);
      }
      return unit ? `${value} ${unit}` : String(value);
    })();

    return (
      <div
        className="flex items-center justify-between gap-4 py-2 group cursor-pointer rounded-lg hover:bg-slate-50 px-2 -mx-2 transition-colors"
        onClick={startEditing}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") startEditing();
        }}
      >
        <div className="min-w-0">
          <span className="text-sm text-slate-500">{label}</span>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-base text-slate-900">{displayValue}</span>
            {inferred && (
              <span className="text-xs text-amber-500 font-medium">
                (inferred)
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {inferred && onConfirm && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onConfirm();
              }}
              className="text-xs font-medium text-emerald-600 border border-emerald-300 rounded px-2 py-0.5 hover:bg-emerald-50 transition-colors"
            >
              Confirm
            </button>
          )}

          <Edit2 className="w-4 h-4 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>
    );
  }

  // ---- Edit mode ----
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key="edit"
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.15 }}
        className="py-2 px-2 -mx-2"
      >
        <span className="text-sm text-slate-500 mb-1 block">{label}</span>

        <div className="flex items-center gap-2">
          {type === "select" && options ? (
            <select
              ref={inputRef as React.RefObject<HTMLSelectElement>}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={saving}
              className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-base text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent disabled:opacity-60"
            >
              {options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ) : (
            <div className="flex-1 flex items-center gap-1">
              <input
                ref={inputRef as React.RefObject<HTMLInputElement>}
                type={type === "number" ? "number" : "text"}
                min={type === "number" ? 0 : undefined}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={saving}
                className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-base text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent disabled:opacity-60"
              />
              {unit && (
                <span className="text-sm text-slate-400 shrink-0">{unit}</span>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="inline-flex items-center justify-center w-8 h-8 rounded-md bg-emerald-500 text-white hover:bg-emerald-600 transition-colors disabled:opacity-60"
            aria-label="Save"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Check className="w-4 h-4" />
            )}
          </button>

          <button
            type="button"
            onClick={cancel}
            disabled={saving}
            className="inline-flex items-center justify-center w-8 h-8 rounded-md bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors disabled:opacity-60"
            aria-label="Cancel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
