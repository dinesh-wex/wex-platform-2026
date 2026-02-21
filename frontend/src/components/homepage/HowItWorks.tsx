"use client";

import { motion } from "framer-motion";
import {
  ClipboardList,
  Cpu,
  Building,
  BarChart3,
  Network,
  Banknote,
} from "lucide-react";

const buyerSteps = [
  {
    icon: ClipboardList,
    title: "Tell us what you need",
    description: "Complete our quick 7-step wizard with your space requirements",
  },
  {
    icon: Cpu,
    title: "Get matched instantly",
    description: "Our AI finds the best warehouses that fit your criteria",
  },
  {
    icon: Building,
    title: "Tour and move in",
    description: "Schedule a tour and move into your new space fast",
  },
];

const supplierSteps = [
  {
    icon: BarChart3,
    title: "Check your earning potential",
    description: "Get a free estimate of what your space could earn",
  },
  {
    icon: Network,
    title: "Join the network",
    description: "Complete onboarding and list your warehouse on WEx",
  },
  {
    icon: Banknote,
    title: "Start earning",
    description: "Receive vetted tenants and automated monthly deposits",
  },
];

const fadeInUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.15 },
  }),
};

function StepCard({
  step,
  index,
  color,
}: {
  step: (typeof buyerSteps)[0];
  index: number;
  color: string;
}) {
  return (
    <motion.div
      custom={index}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-50px" }}
      variants={fadeInUp}
      className="flex gap-4"
    >
      <div
        className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${color}`}
      >
        <step.icon className="h-6 w-6 text-white" />
      </div>
      <div>
        <h4 className="text-lg font-semibold text-white">{step.title}</h4>
        <p className="mt-1 text-sm text-gray-400">{step.description}</p>
      </div>
    </motion.div>
  );
}

export default function HowItWorks() {
  return (
    <section className="bg-gray-950 py-24">
      <div className="mx-auto max-w-6xl px-6">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center text-3xl font-bold text-white sm:text-4xl"
        >
          How It Works
        </motion.h2>

        <div className="mt-16 grid gap-16 md:grid-cols-2 md:gap-12">
          {/* Buyer path */}
          <div>
            <motion.h3
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              className="mb-8 text-center text-xl font-semibold text-blue-400"
            >
              Looking for Space
            </motion.h3>
            <div className="space-y-8">
              {buyerSteps.map((step, i) => (
                <StepCard key={step.title} step={step} index={i} color="bg-blue-600" />
              ))}
            </div>
          </div>

          {/* Supplier path */}
          <div>
            <motion.h3
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              className="mb-8 text-center text-xl font-semibold text-emerald-400"
            >
              Have Space to Offer
            </motion.h3>
            <div className="space-y-8">
              {supplierSteps.map((step, i) => (
                <StepCard
                  key={step.title}
                  step={step}
                  index={i}
                  color="bg-emerald-600"
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
