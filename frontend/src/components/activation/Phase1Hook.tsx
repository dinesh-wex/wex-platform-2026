'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, Loader2, Building2, BarChart3, DollarSign, ChevronDown } from 'lucide-react';
import { BuildingData, TruthCore } from './types';
import { copy } from '@/config/flowCopy';
import { trackEvent } from '@/lib/analytics';

// FAQ data — also used for schema.org structured data
const FAQ_ITEMS = [
  {
    q: 'Does requesting a report commit me to listing my space?',
    a: 'No. The EarnCheck report is a free financial analysis. You are under no obligation to list your space on the Warehouse Exchange network.',
  },
  {
    q: 'How is my potential income calculated?',
    a: 'We analyze public rental listings, local vacancy rates in your specific zip code, and active tenant demand on our platform to estimate your "Unused Capacity Value."',
  },
  {
    q: 'What is the difference between Fixed Rate and Negotiated?',
    a: 'With Fixed Rate, you set your net price and we handle the billing and matching—you get exactly what you ask for. With Negotiated, you review every offer and handle tours yourself.',
  },
  {
    q: 'Can I rent out space for a short time?',
    a: 'Yes. WEx specializes in flexible industrial space. You can monetize space for as little as 1 month or as long as 3 years.',
  },
];

interface Phase1Props {
  setTruthCore: React.Dispatch<React.SetStateAction<TruthCore>>;
  setBuildingData: React.Dispatch<React.SetStateAction<BuildingData | null>>;
  onNext: () => void;
}

export default function Phase1Hook({
  setTruthCore,
  onNext,
}: Phase1Props) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    setLoading(true);
    setError('');

    // Store the address immediately and transition to Phase 2
    // Phase 2 will handle the backend lookup in parallel with the animation
    setTruthCore((prev) => ({
      ...prev,
      address: input.trim(),
    }));

    trackEvent('address_entered', { address: input.trim() });
    onNext();
  }

  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* Schema.org FAQ structured data for SEO */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'FAQPage',
            mainEntity: FAQ_ITEMS.map((item) => ({
              '@type': 'Question',
              name: item.q,
              acceptedAnswer: { '@type': 'Answer', text: item.a },
            })),
          }),
        }}
      />

      {/* ═══════════════════════════════════════════════════════
          HERO FOLD — 100vh, the only thing visible on load
          ═══════════════════════════════════════════════════════ */}
      <div className="min-h-[calc(100vh-8rem)] flex flex-col justify-center items-center px-6 pb-20 bg-white relative">
        {copy.phase1.eyebrow && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1, duration: 0.5 }}
            className="text-xs font-bold uppercase tracking-[0.25em] text-blue-900/60 mb-4"
          >
            {copy.phase1.eyebrow}
          </motion.p>
        )}

        <motion.h1
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2, duration: 0.8 }}
          className="text-5xl md:text-7xl font-serif font-medium text-center mb-12 tracking-tight text-slate-900"
        >
          {copy.phase1.headline}
          <br />
          {copy.phase1.headlineBreak}
        </motion.h1>

        <motion.form
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.6, duration: 0.6 }}
          onSubmit={handleSubmit}
          className="w-full max-w-2xl relative overflow-hidden"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={copy.phase1.placeholder}
            className="w-full text-xl md:text-2xl bg-transparent border-b-2 border-slate-200 focus:border-emerald-500 outline-none py-4 pr-14 placeholder:text-slate-300 transition-colors text-slate-900 text-ellipsis"
            autoFocus
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="absolute right-0 top-3 text-emerald-600 hover:text-emerald-700 disabled:text-slate-300 transition-colors"
          >
            {loading ? (
              <Loader2 size={40} className="animate-spin" />
            ) : (
              <ChevronRight size={40} />
            )}
          </button>
        </motion.form>

        {error && (
          <p className="text-red-500 text-sm mt-4">{error}</p>
        )}

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2, duration: 0.6 }}
          className="text-slate-400 text-sm mt-8"
        >
          {copy.phase1.subtext}
        </motion.p>

        {copy.phase1.loginLink && (
          <motion.a
            href="/supplier?login=true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.6, duration: 0.6 }}
            className="text-slate-400 text-xs mt-4 hover:text-emerald-600 transition-colors underline underline-offset-4"
          >
            {copy.phase1.loginLink}
          </motion.a>
        )}

      </div>

      {/* ═══════════════════════════════════════════════════════
          SECTION 2: "How It Works" — The Trust Band
          ═══════════════════════════════════════════════════════ */}
      <section id="how-it-works" className="bg-[#F9FAFB] py-20 md:py-28 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-serif font-medium text-center text-slate-900 mb-4">
            Turn Empty Space Into Income
          </h2>
          <p className="text-slate-500 text-center mb-16 max-w-2xl mx-auto">
            Three simple steps to start earning from your unused warehouse capacity.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-8">
            {/* Step 1: Identify */}
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 rounded-2xl mb-5">
                <Building2 className="w-8 h-8 text-emerald-600" />
              </div>
              <p className="text-xs font-bold uppercase tracking-widest text-emerald-600 mb-2">Step 1</p>
              <h3 className="text-xl font-bold text-slate-900 mb-2">Enter Your Address</h3>
              <p className="text-slate-500 text-sm leading-relaxed">
                Tell us where your asset is located and how much unused space is currently sitting idle.
              </p>
            </div>

            {/* Step 2: Analyze */}
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-2xl mb-5">
                <BarChart3 className="w-8 h-8 text-blue-600" />
              </div>
              <p className="text-xs font-bold uppercase tracking-widest text-blue-600 mb-2">Step 2</p>
              <h3 className="text-xl font-bold text-slate-900 mb-2">Get Your EarnCheck™</h3>
              <p className="text-slate-500 text-sm leading-relaxed">
                Our engine scans local listings and WEx tenant demand to calculate your maximum potential revenue.
              </p>
            </div>

            {/* Step 3: Earn */}
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-amber-100 rounded-2xl mb-5">
                <DollarSign className="w-8 h-8 text-amber-600" />
              </div>
              <p className="text-xs font-bold uppercase tracking-widest text-amber-600 mb-2">Step 3</p>
              <h3 className="text-xl font-bold text-slate-900 mb-2">Choose Your Payout</h3>
              <p className="text-slate-500 text-sm leading-relaxed">
                Select Fixed Rate for guaranteed pricing or Negotiate to handle deals yourself. We bring the tenants to you.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════
          SECTION 3: FAQ — The SEO Honey
          ═══════════════════════════════════════════════════════ */}
      <section className="bg-white py-20 md:py-28 px-6">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-serif font-medium text-center text-slate-900 mb-4">
            Common Questions about EarnCheck™
          </h2>
          <p className="text-slate-500 text-center mb-12">
            Everything you need to know about monetizing your unused warehouse space.
          </p>

          <div className="divide-y divide-slate-200 border-t border-b border-slate-200">
            {FAQ_ITEMS.map((item, i) => (
              <div key={i}>
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between py-5 text-left group"
                >
                  <span className="text-base font-medium text-slate-900 pr-4 group-hover:text-emerald-700 transition-colors">
                    {item.q}
                  </span>
                  <ChevronDown
                    className={`w-5 h-5 text-slate-400 flex-shrink-0 transition-transform duration-200 ${
                      openFaq === i ? 'rotate-180' : ''
                    }`}
                  />
                </button>
                {openFaq === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    transition={{ duration: 0.2 }}
                    className="pb-5"
                  >
                    <p className="text-slate-600 text-sm leading-relaxed">
                      {item.a}
                    </p>
                  </motion.div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>
    </motion.div>
  );
}
