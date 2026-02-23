"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { AnimatePresence } from "framer-motion";
import Phase1Hook from "@/components/activation/Phase1Hook";
import Phase2Processing from "@/components/activation/Phase2Processing";
import Phase3Reveal from "@/components/activation/Phase3Reveal";
import Phase4Configurator from "@/components/activation/Phase4Configurator";
import Phase5Pricing from "@/components/activation/Phase5Pricing";
import Phase6Activation from "@/components/activation/Phase6Activation";
import Phase6Join from "@/components/activation/Phase6Join";
import Phase6AddAsset from "@/components/activation/Phase6AddAsset";
import PhaseRejection from "@/components/activation/PhaseRejection";
import {
  type Phase,
  type TruthCore,
  type BuildingData,
  type RevenueEstimate,
  type ContextualMemoryEntry,
  createDefaultTruthCore,
} from "@/components/activation/types";
import { copy } from "@/config/flowCopy";
import { api } from "@/lib/api";

export default function SupplierActivationWizard() {
  const [step, setStepRaw] = useState<Phase>(1);
  const [entryIntent, setEntryIntent] = useState<'earncheck' | 'onboard' | 'returning'>('earncheck');

  // Scroll to top on every phase transition (fixes mobile scroll position)
  const setStep = (next: Phase) => {
    setStepRaw(next);
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  // Track page view on mount + detect entry intent
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    // Detect entry intent
    if (params.get("returning") === "true") {
      setEntryIntent('returning');
    } else if (params.get("intent") === "onboard" || params.get("onboard") === "true") {
      setEntryIntent('onboard');
    }

    // Detect test mode from ?test=1 and persist in sessionStorage
    if (params.get("test") === "1") {
      sessionStorage.setItem("wex_is_test", "1");
    }
    const isTest = sessionStorage.getItem("wex_is_test") === "1";
    api.trackPageView({
      path: window.location.pathname,
      referrer: document.referrer || undefined,
      utm_source: params.get("utm_source") || undefined,
      utm_medium: params.get("utm_medium") || undefined,
      utm_campaign: params.get("utm_campaign") || undefined,
      session_id: sessionStorage.getItem("wex_session") || undefined,
      is_test: isTest || undefined,
    });
  }, []);
  const [truthCore, setTruthCore] = useState<TruthCore>(createDefaultTruthCore());
  const [buildingData, setBuildingData] = useState<BuildingData | null>(null);
  const [revenueEstimate, setRevenueEstimate] = useState<RevenueEstimate | null>(null);
  const [memories, setMemories] = useState<ContextualMemoryEntry[]>([]);
  const [rejectedAddress, setRejectedAddress] = useState<string | null>(null);

  function resetToSearch() {
    setRejectedAddress(null);
    setTruthCore(createDefaultTruthCore());
    setBuildingData(null);
    setRevenueEstimate(null);
    setMemories([]);
    setStep(1);
  }

  return (
    <div className="min-h-screen flex flex-col bg-white text-slate-900 font-sans selection:bg-emerald-100">
      {/* ═══ HEADER — Trust Anchor ═══ */}
      <header className="sticky top-0 z-[100] bg-white border-b border-slate-100 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <Image
            src={copy.header.logoPath}
            alt="Warehouse Exchange"
            width={310}
            height={62}
            className="h-12 w-auto"
            priority
          />
          {copy.header.showLogin && (
            <a
              href="/supplier?login=true"
              className="text-slate-400 text-sm hover:text-slate-600 transition-colors"
            >
              Login
            </a>
          )}
        </div>
      </header>

      {/* ═══ PHASE CONTENT ═══ */}
      <main className="flex-1 min-h-0 overflow-auto">
        <AnimatePresence mode="wait">
          {step === 1 && (
            <Phase1Hook
              key="p1"
              setTruthCore={setTruthCore}
              setBuildingData={setBuildingData}
              onNext={() => setStep(2)}
            />
          )}
          {step === 2 && !rejectedAddress && (
            <Phase2Processing
              key="p2"
              truthCore={truthCore}
              setTruthCore={setTruthCore}
              buildingData={buildingData}
              setBuildingData={setBuildingData}
              setRevenueEstimate={setRevenueEstimate}
              onComplete={() => setStep(3)}
              onRejected={(addr) => setRejectedAddress(addr)}
              onFailed={resetToSearch}
            />
          )}
          {rejectedAddress && (
            <PhaseRejection
              key="rejected"
              address={rejectedAddress}
              onTryAgain={resetToSearch}
            />
          )}
          {step === 3 && (
            <Phase3Reveal
              key="p3"
              truthCore={truthCore}
              setTruthCore={setTruthCore}
              buildingData={buildingData}
              revenueEstimate={revenueEstimate}
              onNext={() => setStep(4)}
              onSearchAgain={resetToSearch}
            />
          )}
          {step === 4 && (
            <Phase4Configurator
              key="p4"
              truthCore={truthCore}
              setTruthCore={setTruthCore}
              buildingData={buildingData}
              memories={memories}
              setMemories={setMemories}
              onNext={() => setStep(5)}
            />
          )}
          {step === 5 && (
            <Phase5Pricing
              key="p5"
              truthCore={truthCore}
              setTruthCore={setTruthCore}
              buildingData={buildingData}
              revenueEstimate={revenueEstimate}
              memories={memories}
              setMemories={setMemories}
              onNext={() => setStep(6)}
            />
          )}
          {step === 6 && entryIntent === 'onboard' && (
            <Phase6Join
              key="p6-join"
              truthCore={truthCore}
              buildingData={buildingData}
              revenueEstimate={revenueEstimate}
              memories={memories}
              setMemories={setMemories}
            />
          )}
          {step === 6 && entryIntent === 'earncheck' && (
            <Phase6Activation
              key="p6"
              truthCore={truthCore}
              buildingData={buildingData}
              revenueEstimate={revenueEstimate}
              memories={memories}
              setMemories={setMemories}
            />
          )}
          {step === 6 && entryIntent === 'returning' && (
            <Phase6AddAsset
              key="p6-add"
              truthCore={truthCore}
              buildingData={buildingData}
              revenueEstimate={revenueEstimate}
              memories={memories}
              setMemories={setMemories}
            />
          )}
        </AnimatePresence>
      </main>

      {/* ═══ FOOTER — Legal Floor ═══ */}
      <footer className="bg-[#F9FAFB] border-t border-slate-100 py-4 px-6">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="text-slate-400 text-xs">
            {copy.footer.copyright}
          </span>
          <div className="flex items-center gap-4">
            <a
              href={copy.footer.privacyUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 text-xs hover:text-slate-600 transition-colors"
            >
              {copy.footer.privacyLabel}
            </a>
            <a
              href={copy.footer.termsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 text-xs hover:text-slate-600 transition-colors"
            >
              {copy.footer.termsLabel}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
