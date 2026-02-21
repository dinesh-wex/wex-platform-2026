"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Loader2, Shield, Mail, Phone } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { fetchAPI } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Schema                                                              */
/* ------------------------------------------------------------------ */
const contactSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
  phone: z
    .string()
    .min(7, "Please enter a valid phone number")
    .regex(/^[\d\s\-\(\)\+]+$/, "Please enter a valid phone number"),
});

type ContactFormData = z.infer<typeof contactSchema>;

/* ------------------------------------------------------------------ */
/*  Props                                                               */
/* ------------------------------------------------------------------ */
export interface ContactCaptureModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: ContactFormData) => void;
  /** Contextual headline shown in the modal */
  headline?: string;
  /** Contextual subtitle */
  subtitle?: string;
  /** Label for the submit button */
  submitLabel?: string;
  /** Trust copy shown below the form */
  trustText?: string;
  /** If true, only show email (no phone) */
  emailOnly?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */
export default function ContactCaptureModal({
  open,
  onClose,
  onSubmit,
  headline = "How should we reach you?",
  subtitle = "We need your contact info to coordinate next steps.",
  submitLabel = "Continue",
  trustText = "We'll only use this to coordinate your tour. No spam, ever.",
  emailOnly = false,
}: ContactCaptureModalProps) {
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<ContactFormData>({
    resolver: zodResolver(
      emailOnly
        ? contactSchema.pick({ email: true })
        : contactSchema
    ),
  });

  async function handleFormSubmit(data: ContactFormData) {
    setSubmitting(true);
    try {
      // Persist contact to API (stubbed for now)
      await fetchAPI("/api/buyer/contact", {
        method: "POST",
        body: JSON.stringify(data),
      });
    } catch {
      // Silently continue -- the contact is also stored client-side
    }

    // Store locally for downstream use
    localStorage.setItem("wex_buyer_contact", JSON.stringify(data));

    setSubmitting(false);
    onSubmit(data);
    reset();
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="contact-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            key="contact-modal"
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 350 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full max-w-md bg-slate-900 rounded-2xl shadow-2xl border border-slate-700 overflow-hidden">
              {/* Header */}
              <div className="px-6 pt-6 pb-2 flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-bold text-white">{headline}</h3>
                  <p className="text-sm text-slate-400 mt-1">{subtitle}</p>
                </div>
                <button
                  onClick={onClose}
                  className="text-slate-500 hover:text-slate-300 transition-colors p-1 -mr-1 -mt-1"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Form */}
              <form
                onSubmit={handleSubmit(handleFormSubmit)}
                className="px-6 pt-4 pb-6 space-y-4"
              >
                {/* Email */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="email"
                      autoFocus
                      {...register("email")}
                      placeholder="you@company.com"
                      className="w-full bg-slate-800 border border-slate-600 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                  {errors.email && (
                    <p className="text-xs text-red-400 mt-1">
                      {errors.email.message}
                    </p>
                  )}
                </div>

                {/* Phone */}
                {!emailOnly && (
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1.5">
                      Phone number
                    </label>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input
                        type="tel"
                        {...register("phone")}
                        placeholder="(555) 123-4567"
                        className="w-full bg-slate-800 border border-slate-600 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                    {errors.phone && (
                      <p className="text-xs text-red-400 mt-1">
                        {errors.phone.message}
                      </p>
                    )}
                  </div>
                )}

                {/* Submit */}
                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full bg-blue-600 text-white py-3 rounded-xl font-semibold hover:bg-blue-700 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    submitLabel
                  )}
                </button>

                {/* Trust text */}
                <div className="flex items-center justify-center gap-1.5 pt-1">
                  <Shield className="w-3.5 h-3.5 text-emerald-400" />
                  <p className="text-xs text-slate-500">{trustText}</p>
                </div>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
