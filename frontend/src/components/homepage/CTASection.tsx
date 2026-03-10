"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

export default function CTASection() {
  const router = useRouter();
  const [address, setAddress] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (address.trim()) {
      router.push(`/supplier/earncheck?address=${encodeURIComponent(address.trim())}`);
    }
  }

  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-slate-50 via-emerald-50 to-slate-50 py-24">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,_rgba(59,130,246,0.06),_transparent_60%)]" />

      <div className="relative z-10 mx-auto max-w-3xl px-6 text-center">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-3xl font-bold text-slate-900 sm:text-4xl"
        >
          What could your space earn?
        </motion.h2>

        <motion.form
          onSubmit={handleSubmit}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-10 flex flex-col gap-3 sm:flex-row"
        >
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Enter your warehouse address..."
            className="flex-1 rounded-lg border border-slate-300 bg-white px-5 py-3.5 text-slate-900 placeholder-slate-400 outline-none transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
          <button
            type="submit"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-6 py-3.5 font-semibold text-white shadow-lg shadow-emerald-600/25 transition-all hover:bg-emerald-500 hover:shadow-emerald-500/30 active:scale-[0.98]"
          >
            Get Estimate
            <ArrowRight className="h-4 w-4" />
          </button>
        </motion.form>

        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4 }}
          className="mt-6 text-sm text-slate-500"
        >
          Already know you want to list?{" "}
          <Link
            href="/supplier/onboard"
            className="text-emerald-600 hover:text-emerald-500 underline underline-offset-2 transition-colors"
          >
            Skip straight to onboarding
          </Link>
        </motion.p>
      </div>
    </section>
  );
}
