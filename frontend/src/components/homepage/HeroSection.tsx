"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Building2, Clock, DollarSign } from "lucide-react";

const trustBadges = [
  { icon: Building2, label: "500+ Warehouses" },
  { icon: Clock, label: "48hr Average Match Time" },
  { icon: DollarSign, label: "$0 Upfront Cost" },
];

export default function HeroSection() {
  return (
    <section className="relative min-h-[90vh] flex items-center justify-center overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-blue-950" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(59,130,246,0.15),_transparent_60%)]" />

      <div className="relative z-10 mx-auto max-w-5xl px-6 py-24 text-center">
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-4xl font-bold tracking-tight text-white sm:text-5xl md:text-6xl lg:text-7xl"
        >
          Find warehouse space
          <br />
          <span className="text-blue-400">in hours, not months</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.15 }}
          className="mx-auto mt-6 max-w-2xl text-lg text-gray-400 sm:text-xl"
        >
          The marketplace connecting businesses with flexible warehouse space
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row"
        >
          <Link
            href="/buyer"
            className="inline-flex h-12 items-center justify-center rounded-lg bg-blue-600 px-8 text-base font-semibold text-white shadow-lg shadow-blue-600/25 transition-all hover:bg-blue-500 hover:shadow-blue-500/30 hover:scale-[1.02] active:scale-[0.98]"
          >
            Find Space
          </Link>
          <Link
            href="/supplier/earncheck?intent=onboard"
            className="inline-flex h-12 items-center justify-center rounded-lg border border-gray-600 px-8 text-base font-semibold text-gray-200 transition-all hover:border-gray-400 hover:text-white hover:scale-[1.02] active:scale-[0.98]"
          >
            List Your Space
          </Link>
        </motion.div>

        {/* Trust badges */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.5 }}
          className="mt-16 flex flex-wrap items-center justify-center gap-8 sm:gap-12"
        >
          {trustBadges.map((badge) => (
            <div key={badge.label} className="flex items-center gap-2 text-gray-400">
              <badge.icon className="h-5 w-5 text-blue-400" />
              <span className="text-sm font-medium">{badge.label}</span>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
