"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  Users,
  Loader2,
  AlertCircle,
  CircleDot,
  Zap,
  Target,
  BarChart3,
  CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface SupplyNode {
  id: string;
  name: string;
  city: string;
  state: string;
  available_sqft: number;
  supplier_rate: number;
  status: string;
  activated: boolean;
}

interface DemandNode {
  id: string;
  buyer_company: string;
  location: string;
  sqft_needed: number;
  use_type: string;
  status: string;
}

interface MatchRecord {
  id: string;
  warehouse_name: string;
  buyer_company: string;
  score: number;
  status: string;
  reasoning: string;
  created_at: string;
}

interface ClearingStats {
  total_matches: number;
  acceptance_rate: number;
  average_score: number;
  instant_book_rate: number;
}

/* ------------------------------------------------------------------ */
/*  Status styling                                                     */
/* ------------------------------------------------------------------ */
const STATUS_COLORS: Record<string, string> = {
  active: "text-green-500",
  matched: "text-green-500",
  searching: "text-blue-500",
  pending: "text-amber-500",
  inactive: "text-red-400",
  intake: "text-purple-500",
};

/* ------------------------------------------------------------------ */
/*  Demo data                                                          */
/* ------------------------------------------------------------------ */
const DEMO_SUPPLY: SupplyNode[] = [
  { id: "w1", name: "Downtown Distribution Center", city: "Dallas", state: "TX", available_sqft: 35000, supplier_rate: 8.50, status: "matched", activated: true },
  { id: "w2", name: "Airport Logistics Hub", city: "Fort Worth", state: "TX", available_sqft: 80000, supplier_rate: 9.00, status: "matched", activated: true },
  { id: "w3", name: "Northside Warehouse", city: "Plano", state: "TX", available_sqft: 75000, supplier_rate: 7.25, status: "searching", activated: true },
  { id: "w4", name: "Eastgate Cold Storage", city: "Dallas", state: "TX", available_sqft: 22000, supplier_rate: 12.00, status: "active", activated: true },
  { id: "w5", name: "Southside Flex Space", city: "Arlington", state: "TX", available_sqft: 45000, supplier_rate: 8.00, status: "pending", activated: false },
  { id: "w6", name: "Commerce Park", city: "Irving", state: "TX", available_sqft: 60000, supplier_rate: 10.00, status: "active", activated: true },
];

const DEMO_DEMAND: DemandNode[] = [
  { id: "n1", buyer_company: "Acme Logistics", location: "Dallas, TX", sqft_needed: 25000, use_type: "E-commerce fulfillment", status: "matched" },
  { id: "n2", buyer_company: "FreshCo Foods", location: "DFW Area", sqft_needed: 60000, use_type: "Cold chain distribution", status: "matched" },
  { id: "n3", buyer_company: "QuickShip Inc", location: "Plano, TX", sqft_needed: 40000, use_type: "Distribution center", status: "searching" },
  { id: "n4", buyer_company: "TechParts Co", location: "Irving, TX", sqft_needed: 15000, use_type: "Parts storage", status: "pending" },
  { id: "n5", buyer_company: "MedSupply LLC", location: "Arlington, TX", sqft_needed: 20000, use_type: "Medical supply", status: "intake" },
];

const DEMO_MATCHES: MatchRecord[] = [
  { id: "m1", warehouse_name: "Downtown Distribution", buyer_company: "Acme Logistics", score: 94, status: "accepted", reasoning: "Location match (Dallas), size fit (25k/35k sqft), rate compatible. E-commerce use aligned with warehouse specs.", created_at: "2 hours ago" },
  { id: "m2", warehouse_name: "Airport Logistics Hub", buyer_company: "FreshCo Foods", score: 91, status: "accepted", reasoning: "Proximity to airport for cold chain needs. Large capacity (80k sqft) covers 60k requirement with room to grow.", created_at: "5 hours ago" },
  { id: "m3", warehouse_name: "Northside Warehouse", buyer_company: "QuickShip Inc", score: 87, status: "pending", reasoning: "Plano location matches need. 75k sqft exceeds 40k requirement. Rate of $7.25 within budget.", created_at: "8 hours ago" },
  { id: "m4", warehouse_name: "Commerce Park", buyer_company: "TechParts Co", score: 82, status: "pending", reasoning: "Irving location match. 60k sqft available for 15k need. Flexible space configuration.", created_at: "12 hours ago" },
  { id: "m5", warehouse_name: "Eastgate Cold Storage", buyer_company: "MedSupply LLC", score: 78, status: "reviewing", reasoning: "Climate-controlled storage needed for medical supplies. Premium rate but specialized facilities.", created_at: "1 day ago" },
];

const DEMO_STATS: ClearingStats = {
  total_matches: 47,
  acceptance_rate: 72,
  average_score: 85,
  instant_book_rate: 34,
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function ClearingPage() {
  const [supply, setSupply] = useState<SupplyNode[]>(DEMO_SUPPLY);
  const [demand, setDemand] = useState<DemandNode[]>(DEMO_DEMAND);
  const [matches, setMatches] = useState<MatchRecord[]>(DEMO_MATCHES);
  const [stats, setStats] = useState<ClearingStats>(DEMO_STATS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [warehouseData, clearingData] = await Promise.allSettled([
        api.adminWarehouses(),
        api.adminClearingStats(),
      ]);

      if (warehouseData.status === "fulfilled") {
        const wd = warehouseData.value;
        if (wd.supply) setSupply(wd.supply);
        if (wd.demand) setDemand(wd.demand);
        if (wd.matches) setMatches(wd.matches);
      }
      if (clearingData.status === "fulfilled") {
        setStats(clearingData.value);
      }

      const allFailed = [warehouseData, clearingData].every((r) => r.status === "rejected");
      if (allFailed) {
        setError("Could not connect to backend");
      }
    } catch {
      setError("Could not connect to backend");
    } finally {
      setLoading(false);
    }
  }

  function formatNumber(num: number): string {
    return new Intl.NumberFormat("en-US").format(num);
  }

  function getScoreColor(score: number): string {
    if (score >= 90) return "text-green-600 bg-green-50";
    if (score >= 80) return "text-blue-600 bg-blue-50";
    if (score >= 70) return "text-amber-600 bg-amber-50";
    return "text-red-600 bg-red-50";
  }

  function getMatchStatusBadge(status: string) {
    const styles: Record<string, string> = {
      accepted: "bg-green-100 text-green-700",
      pending: "bg-amber-100 text-amber-700",
      reviewing: "bg-blue-100 text-blue-700",
      rejected: "bg-red-100 text-red-700",
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || "bg-gray-100 text-gray-700"}`}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/admin" className="text-slate-400 hover:text-slate-600 transition-colors">
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900">
                  W<span className="text-blue-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">Clearing Engine</span>
              </div>
            </div>
            {error && (
              <span className="flex items-center gap-1.5 text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full">
                <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
                Demo Mode
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mb-4" />
            <p className="text-slate-500">Loading clearing engine data...</p>
          </div>
        )}

        {/* Error Banner */}
        {error && !loading && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3 mb-6">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">Could not connect to backend</p>
              <p className="text-xs text-amber-600 mt-1">Showing demo data. Start the FastAPI backend for live data.</p>
            </div>
          </div>
        )}

        {!loading && (
          <>
            {/* Three-column visualization */}
            <div className="grid grid-cols-1 lg:grid-cols-7 gap-6 mb-8">
              {/* Supply Side (left panel) */}
              <div className="lg:col-span-3">
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <Building2 className="w-5 h-5 text-blue-600" />
                    <h2 className="text-lg font-semibold text-slate-900">Supply Side</h2>
                    <span className="text-xs text-slate-400 ml-auto">{supply.length} warehouses</span>
                  </div>
                  <div className="space-y-3">
                    {supply.map((node) => (
                      <div key={node.id} className="bg-gray-50 rounded-lg p-4 border border-gray-100 hover:border-gray-200 transition-colors">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <CircleDot className={`w-3.5 h-3.5 ${STATUS_COLORS[node.status] || "text-gray-400"}`} />
                            <span className="text-sm font-medium text-slate-800">{node.name}</span>
                          </div>
                          <div className={`w-2 h-2 rounded-full ${node.activated ? "bg-green-400" : "bg-gray-300"}`} title={node.activated ? "Activated" : "Not activated"} />
                        </div>
                        <div className="pl-5.5 grid grid-cols-2 gap-2 text-xs text-slate-500">
                          <span>{node.city}, {node.state}</span>
                          <span className="text-right">{formatNumber(node.available_sqft)} sqft</span>
                          <span>${node.supplier_rate.toFixed(2)}/sqft/mo</span>
                          <span className="text-right capitalize">{node.status}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Clearing Engine (center) */}
              <div className="lg:col-span-1 flex flex-col items-center justify-center">
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-200 mb-4">
                  <Zap className="w-10 h-10 text-white" />
                </div>
                <p className="text-sm font-bold text-slate-700 mb-2">WEx Clearing</p>
                <p className="text-xs text-slate-400 text-center mb-4">AI-powered matching engine</p>

                {/* Animated connections */}
                <div className="space-y-2 w-full">
                  {matches.filter((m) => m.status === "accepted").map((_, i) => (
                    <div key={`c-${i}`} className="flex items-center gap-1">
                      <div className="h-px flex-1 bg-green-300" />
                      <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                      <div className="h-px flex-1 bg-green-300" />
                    </div>
                  ))}
                  {matches.filter((m) => m.status === "pending").map((_, i) => (
                    <div key={`p-${i}`} className="flex items-center gap-1">
                      <div className="h-px flex-1 bg-amber-200" />
                      <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                      <div className="h-px flex-1 bg-amber-200" />
                    </div>
                  ))}
                  {matches.filter((m) => m.status === "reviewing").map((_, i) => (
                    <div key={`r-${i}`} className="flex items-center gap-1">
                      <div className="h-px flex-1 bg-blue-200" />
                      <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                      <div className="h-px flex-1 bg-blue-200" />
                    </div>
                  ))}
                </div>

                <div className="mt-4 flex flex-col gap-1.5 text-xs text-slate-400">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> Accepted</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400" /> Pending</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400" /> Reviewing</span>
                </div>
              </div>

              {/* Demand Side (right panel) */}
              <div className="lg:col-span-3">
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <Users className="w-5 h-5 text-green-600" />
                    <h2 className="text-lg font-semibold text-slate-900">Demand Side</h2>
                    <span className="text-xs text-slate-400 ml-auto">{demand.length} needs</span>
                  </div>
                  <div className="space-y-3">
                    {demand.map((node) => (
                      <div key={node.id} className="bg-gray-50 rounded-lg p-4 border border-gray-100 hover:border-gray-200 transition-colors">
                        <div className="flex items-center gap-2 mb-2">
                          <CircleDot className={`w-3.5 h-3.5 ${STATUS_COLORS[node.status] || "text-gray-400"}`} />
                          <span className="text-sm font-medium text-slate-800">{node.buyer_company}</span>
                        </div>
                        <div className="pl-5.5 grid grid-cols-2 gap-2 text-xs text-slate-500">
                          <span>{node.location}</span>
                          <span className="text-right">{formatNumber(node.sqft_needed)} sqft</span>
                          <span>{node.use_type}</span>
                          <span className="text-right capitalize">{node.status}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Match History */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
              <div className="flex items-center gap-2 mb-4">
                <Target className="w-5 h-5 text-purple-600" />
                <h2 className="text-lg font-semibold text-slate-900">Match History</h2>
                <span className="text-xs text-slate-400 ml-auto">{matches.length} matches</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Warehouse</th>
                      <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Buyer</th>
                      <th className="text-center py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Score</th>
                      <th className="text-center py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                      <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Reasoning</th>
                      <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matches.map((match) => (
                      <tr key={match.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-2 text-slate-700 font-medium">{match.warehouse_name}</td>
                        <td className="py-3 px-2 text-slate-700">{match.buyer_company}</td>
                        <td className="py-3 px-2 text-center">
                          <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-bold ${getScoreColor(match.score)}`}>
                            {match.score}
                          </span>
                        </td>
                        <td className="py-3 px-2 text-center">{getMatchStatusBadge(match.status)}</td>
                        <td className="py-3 px-2 text-slate-500 text-xs max-w-xs truncate">{match.reasoning}</td>
                        <td className="py-3 px-2 text-right text-xs text-slate-400">{match.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Clearing Stats */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-purple-100 p-2 rounded-lg">
                    <Target className="w-5 h-5 text-purple-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Total Matches</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{stats.total_matches}</p>
                <p className="text-xs text-slate-400 mt-1">All time matches generated</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-green-100 p-2 rounded-lg">
                    <CheckCircle2 className="w-5 h-5 text-green-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Acceptance Rate</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{stats.acceptance_rate}%</p>
                <p className="text-xs text-slate-400 mt-1">Matches accepted by buyers</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-blue-100 p-2 rounded-lg">
                    <BarChart3 className="w-5 h-5 text-blue-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Average Score</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{stats.average_score}</p>
                <p className="text-xs text-slate-400 mt-1">Out of 100 match quality</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-amber-100 p-2 rounded-lg">
                    <Zap className="w-5 h-5 text-amber-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Instant Book Rate</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{stats.instant_book_rate}%</p>
                <p className="text-xs text-slate-400 mt-1">Deals using instant book</p>
              </div>
            </div>

            {/* Footer */}
            <div className="text-center py-6 border-t border-gray-100 mt-8">
              <p className="text-xs text-slate-400">
                Powered by W<span className="text-blue-500 font-semibold">Ex</span> Clearing House | Clearing Engine
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
