"use client";

import { motion } from "framer-motion";
import {
  BarChart3,
  ShieldCheck,
  Wallet,
  Users,
  Cpu,
  Tag,
  Clock,
  CalendarRange,
} from "lucide-react";

const supplierBenefits = [
  { icon: BarChart3, title: "Free property valuation", description: "Know exactly what your space is worth in today's market" },
  { icon: ShieldCheck, title: "Vetted buyers only", description: "Every tenant is screened and verified before introduction" },
  { icon: Wallet, title: "Automated monthly deposits", description: "Payments collected and deposited on schedule, every time" },
  { icon: Users, title: "Keep your existing tenants", description: "List only your vacant or underused space, no disruption" },
];

const buyerBenefits = [
  { icon: Cpu, title: "AI-powered matching", description: "Our algorithms find the best space for your exact requirements" },
  { icon: Tag, title: "Pre-negotiated rates", description: "Competitive pricing already locked in, no back-and-forth" },
  { icon: Clock, title: "Tour within 48 hours", description: "Schedule and visit matched spaces in days, not weeks" },
  { icon: CalendarRange, title: "Flexible terms from 1 month", description: "Short or long term leases that adapt to your business" },
];

const fadeInUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.1 },
  }),
};

function BenefitItem({
  benefit,
  index,
  accentColor,
}: {
  benefit: (typeof supplierBenefits)[0];
  index: number;
  accentColor: string;
}) {
  return (
    <motion.div
      custom={index}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-40px" }}
      variants={fadeInUp}
      className="flex gap-4"
    >
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${accentColor}`}>
        <benefit.icon className="h-5 w-5 text-white" />
      </div>
      <div>
        <h4 className="font-semibold text-white">{benefit.title}</h4>
        <p className="mt-1 text-sm text-gray-400">{benefit.description}</p>
      </div>
    </motion.div>
  );
}

export default function ValueProps() {
  return (
    <section className="bg-gray-950 py-24">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-16 md:grid-cols-2 md:gap-12">
          {/* Supplier column */}
          <div>
            <motion.h3
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4 }}
              className="mb-8 text-2xl font-bold text-white"
            >
              For Suppliers
            </motion.h3>
            <div className="space-y-6">
              {supplierBenefits.map((b, i) => (
                <BenefitItem key={b.title} benefit={b} index={i} accentColor="bg-emerald-600" />
              ))}
            </div>
          </div>

          {/* Buyer column */}
          <div>
            <motion.h3
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4 }}
              className="mb-8 text-2xl font-bold text-white"
            >
              For Buyers
            </motion.h3>
            <div className="space-y-6">
              {buyerBenefits.map((b, i) => (
                <BenefitItem key={b.title} benefit={b} index={i} accentColor="bg-blue-600" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
