"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { MapPin, Maximize2, Thermometer, Truck, ArrowRight } from "lucide-react";

const mockListings = [
  {
    id: "1",
    city: "Dallas, TX",
    sqftRange: "10,000 - 25,000 sqft",
    rateRange: "$4.50 - $6.00 /sqft/yr",
    features: ["Climate Controlled", "Dock High"],
    gradient: "from-blue-900/40 to-gray-800/60",
  },
  {
    id: "2",
    city: "Atlanta, GA",
    sqftRange: "5,000 - 15,000 sqft",
    rateRange: "$5.00 - $7.50 /sqft/yr",
    features: ["Cross-Dock", "24/7 Access"],
    gradient: "from-indigo-900/40 to-gray-800/60",
  },
  {
    id: "3",
    city: "Chicago, IL",
    sqftRange: "20,000 - 50,000 sqft",
    rateRange: "$3.75 - $5.25 /sqft/yr",
    features: ["Rail Access", "Dock High"],
    gradient: "from-slate-800/60 to-gray-900/60",
  },
  {
    id: "4",
    city: "Phoenix, AZ",
    sqftRange: "8,000 - 20,000 sqft",
    rateRange: "$3.50 - $5.00 /sqft/yr",
    features: ["Climate Controlled", "Yard Space"],
    gradient: "from-cyan-900/40 to-gray-800/60",
  },
  {
    id: "5",
    city: "Memphis, TN",
    sqftRange: "15,000 - 40,000 sqft",
    rateRange: "$3.00 - $4.50 /sqft/yr",
    features: ["Rail Access", "Cross-Dock"],
    gradient: "from-purple-900/30 to-gray-800/60",
  },
  {
    id: "6",
    city: "Los Angeles, CA",
    sqftRange: "5,000 - 12,000 sqft",
    rateRange: "$8.00 - $12.00 /sqft/yr",
    features: ["Climate Controlled", "24/7 Access"],
    gradient: "from-rose-900/30 to-gray-800/60",
  },
];

const featureIcons: Record<string, typeof MapPin> = {
  "Climate Controlled": Thermometer,
  "Dock High": Truck,
  "Cross-Dock": Truck,
  "24/7 Access": Maximize2,
  "Rail Access": Truck,
  "Yard Space": Maximize2,
};

const fadeInUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.1 },
  }),
};

export default function FeaturedListings() {
  return (
    <section className="bg-gray-900 py-24">
      <div className="mx-auto max-w-7xl px-6">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center text-3xl font-bold text-white sm:text-4xl"
        >
          Available Spaces
        </motion.h2>

        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {mockListings.map((listing, i) => (
            <motion.div
              key={listing.id}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-30px" }}
              variants={fadeInUp}
              className="group overflow-hidden rounded-xl border border-gray-800 bg-gray-850 transition-all hover:border-gray-700 hover:shadow-lg hover:shadow-blue-900/10"
            >
              {/* Placeholder satellite image */}
              <div
                className={`h-40 bg-gradient-to-br ${listing.gradient} flex items-center justify-center`}
              >
                <MapPin className="h-10 w-10 text-gray-600" />
              </div>

              <div className="p-5">
                <div className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-blue-400" />
                  <h3 className="text-lg font-semibold text-white">
                    {listing.city}
                  </h3>
                </div>

                <div className="mt-3 space-y-1.5 text-sm text-gray-400">
                  <p>{listing.sqftRange}</p>
                  <p className="text-emerald-400 font-medium">{listing.rateRange}</p>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {listing.features.map((feature) => {
                    const Icon = featureIcons[feature] || MapPin;
                    return (
                      <span
                        key={feature}
                        className="inline-flex items-center gap-1 rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-300"
                      >
                        <Icon className="h-3 w-3" />
                        {feature}
                      </span>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4 }}
          className="mt-12 text-center"
        >
          <Link
            href="/browse"
            className="inline-flex items-center gap-2 text-blue-400 font-medium hover:text-blue-300 transition-colors"
          >
            Browse All Spaces
            <ArrowRight className="h-4 w-4" />
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
