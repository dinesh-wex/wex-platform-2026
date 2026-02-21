"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  Users,
  FileText,
  DollarSign,
  Activity,
  Loader2,
  AlertCircle,
  ArrowRight,
  CircleDot,
  Zap,
  BookOpen,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface OverviewStats {
  active_warehouses: number;
  total_sqft: number;
  active_buyers: number;
  active_deals: number;
  monthly_revenue: number;
}

interface RecentDeal {
  id: string;
  warehouse_city: string;
  buyer_company: string;
  sqft: number;
  supplier_rate: number;
  buyer_rate: number;
  spread_pct: number;
  monthly_wex_revenue: number;
  status: string;
  deal_type: string;
}

interface AgentAction {
  id: string;
  agent: string;
  action: string;
  timestamp: string;
  latency_ms: number;
}

interface LedgerSummary {
  total_buyer_payments: number;
  total_supplier_payments: number;
  net_wex_revenue: number;
}

interface ClearingNode {
  id: string;
  label: string;
  detail: string;
  status: "matched" | "searching" | "pending";
}

/* ------------------------------------------------------------------ */
/*  Agent color map                                                    */
/* ------------------------------------------------------------------ */
const AGENT_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  activation: { bg: "bg-blue-100", text: "text-blue-700", border: "border-blue-300" },
  memory: { bg: "bg-purple-100", text: "text-purple-700", border: "border-purple-300" },
  clearing: { bg: "bg-green-100", text: "text-green-700", border: "border-green-300" },
  buyer: { bg: "bg-amber-100", text: "text-amber-700", border: "border-amber-300" },
  pricing: { bg: "bg-indigo-100", text: "text-indigo-700", border: "border-indigo-300" },
  settlement: { bg: "bg-rose-100", text: "text-rose-700", border: "border-rose-300" },
};

function getAgentColor(agent: string) {
  const key = agent.toLowerCase();
  for (const [k, v] of Object.entries(AGENT_COLORS)) {
    if (key.includes(k)) return v;
  }
  return { bg: "bg-gray-100", text: "text-gray-700", border: "border-gray-300" };
}

/* ------------------------------------------------------------------ */
/*  Status colors for clearing nodes                                   */
/* ------------------------------------------------------------------ */
const STATUS_DOT: Record<string, string> = {
  matched: "text-green-500",
  searching: "text-blue-500",
  pending: "text-amber-500",
};

/* ------------------------------------------------------------------ */
/*  Demo data                                                          */
/* ------------------------------------------------------------------ */
const DEMO_OVERVIEW: OverviewStats = {
  active_warehouses: 12,
  total_sqft: 485000,
  active_buyers: 8,
  active_deals: 5,
  monthly_revenue: 18750,
};

const DEMO_SUPPLY: ClearingNode[] = [
  { id: "s1", label: "Downtown Distribution", detail: "35,000 sqft @ $8.50", status: "matched" },
  { id: "s2", label: "Airport Logistics Hub", detail: "80,000 sqft @ $9.00", status: "matched" },
  { id: "s3", label: "Northside Warehouse", detail: "75,000 sqft @ $7.25", status: "searching" },
  { id: "s4", label: "Eastgate Cold Storage", detail: "22,000 sqft @ $12.00", status: "pending" },
];

const DEMO_DEMAND: ClearingNode[] = [
  { id: "d1", label: "Acme Logistics", detail: "25,000 sqft e-commerce", status: "matched" },
  { id: "d2", label: "FreshCo Foods", detail: "60,000 sqft cold chain", status: "matched" },
  { id: "d3", label: "QuickShip Inc", detail: "40,000 sqft distribution", status: "searching" },
  { id: "d4", label: "TechParts Co", detail: "15,000 sqft storage", status: "pending" },
];

const DEMO_DEALS: RecentDeal[] = [
  { id: "d-1", warehouse_city: "Dallas", buyer_company: "Acme Logistics", sqft: 25000, supplier_rate: 8.50, buyer_rate: 9.75, spread_pct: 14.7, monthly_wex_revenue: 3125, status: "active", deal_type: "standard" },
  { id: "d-2", warehouse_city: "Fort Worth", buyer_company: "FreshCo Foods", sqft: 60000, supplier_rate: 9.00, buyer_rate: 10.25, spread_pct: 13.9, monthly_wex_revenue: 7500, status: "active", deal_type: "instant_book" },
  { id: "d-3", warehouse_city: "Plano", buyer_company: "QuickShip Inc", sqft: 40000, supplier_rate: 7.25, buyer_rate: 8.50, spread_pct: 17.2, monthly_wex_revenue: 5000, status: "pending", deal_type: "standard" },
  { id: "d-4", warehouse_city: "Irving", buyer_company: "TechParts Co", sqft: 15000, supplier_rate: 10.00, buyer_rate: 11.50, spread_pct: 15.0, monthly_wex_revenue: 2250, status: "tour_scheduled", deal_type: "standard" },
  { id: "d-5", warehouse_city: "Arlington", buyer_company: "MedSupply LLC", sqft: 20000, supplier_rate: 11.00, buyer_rate: 12.75, spread_pct: 15.9, monthly_wex_revenue: 3500, status: "terms_accepted", deal_type: "instant_book" },
];

const DEMO_AGENTS: AgentAction[] = [
  { id: "a1", agent: "Clearing Agent", action: "Matched Acme Logistics with Downtown Distribution - score 94", timestamp: "2 min ago", latency_ms: 1240 },
  { id: "a2", agent: "Pricing Agent", action: "Set buyer rate $9.75/sqft for match M-1042", timestamp: "3 min ago", latency_ms: 890 },
  { id: "a3", agent: "Activation Agent", action: "Completed warehouse activation for Eastgate Cold Storage", timestamp: "5 min ago", latency_ms: 2100 },
  { id: "a4", agent: "Buyer Agent", action: "Intake complete for QuickShip Inc - 40,000 sqft needed", timestamp: "8 min ago", latency_ms: 1560 },
  { id: "a5", agent: "Memory Agent", action: "Updated truth core for Airport Logistics Hub", timestamp: "10 min ago", latency_ms: 450 },
  { id: "a6", agent: "Settlement Agent", action: "Tour confirmed for TechParts Co at Irving facility", timestamp: "12 min ago", latency_ms: 980 },
  { id: "a7", agent: "Clearing Agent", action: "Re-scored 3 matches after rate update", timestamp: "15 min ago", latency_ms: 1800 },
  { id: "a8", agent: "Pricing Agent", action: "Adjusted supplier rate for Northside Warehouse", timestamp: "18 min ago", latency_ms: 720 },
  { id: "a9", agent: "Activation Agent", action: "Started activation for Southside Flex Space", timestamp: "22 min ago", latency_ms: 340 },
  { id: "a10", agent: "Buyer Agent", action: "Registered new buyer MedSupply LLC", timestamp: "25 min ago", latency_ms: 670 },
];

const DEMO_LEDGER: LedgerSummary = {
  total_buyer_payments: 127500,
  total_supplier_payments: 108750,
  net_wex_revenue: 18750,
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function AdminDashboard() {
  const [overview, setOverview] = useState<OverviewStats>(DEMO_OVERVIEW);
  const [supply, setSupply] = useState<ClearingNode[]>(DEMO_SUPPLY);
  const [demand, setDemand] = useState<ClearingNode[]>(DEMO_DEMAND);
  const [deals, setDeals] = useState<RecentDeal[]>(DEMO_DEALS);
  const [agents, setAgents] = useState<AgentAction[]>(DEMO_AGENTS);
  const [ledger, setLedger] = useState<LedgerSummary>(DEMO_LEDGER);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [overviewData, dealsData, agentsData, ledgerData] = await Promise.allSettled([
        api.adminOverview(),
        api.adminDeals(),
        api.adminAgents(),
        api.adminLedger(),
      ]);

      if (overviewData.status === "fulfilled") {
        setOverview(overviewData.value);
        if (overviewData.value.supply_nodes) setSupply(overviewData.value.supply_nodes);
        if (overviewData.value.demand_nodes) setDemand(overviewData.value.demand_nodes);
      }
      if (dealsData.status === "fulfilled") {
        const dd = dealsData.value;
        setDeals(Array.isArray(dd) ? dd : dd.deals || DEMO_DEALS);
      }
      if (agentsData.status === "fulfilled") {
        const ad = agentsData.value;
        setAgents(Array.isArray(ad) ? ad : ad.actions || DEMO_AGENTS);
      }
      if (ledgerData.status === "fulfilled") {
        setLedger(ledgerData.value);
      }

      // If all failed, show error
      const allFailed = [overviewData, dealsData, agentsData, ledgerData].every(
        (r) => r.status === "rejected"
      );
      if (allFailed) {
        setError("Could not connect to backend");
      }
    } catch {
      setError("Could not connect to backend");
    } finally {
      setLoading(false);
    }
  }

  function formatCurrency(amount: number): string {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
  }

  function formatNumber(num: number): string {
    return new Intl.NumberFormat("en-US").format(num);
  }

  function getStatusBadge(status: string) {
    const styles: Record<string, string> = {
      active: "bg-green-100 text-green-700",
      confirmed: "bg-green-100 text-green-700",
      pending: "bg-amber-100 text-amber-700",
      terms_accepted: "bg-emerald-100 text-emerald-700",
      tour_scheduled: "bg-sky-100 text-sky-700",
    };
    return (
      <span
        className={`px-2 py-0.5 rounded-full text-xs font-medium ${
          styles[status] || "bg-gray-100 text-gray-700"
        }`}
      >
        {status.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
      </span>
    );
  }

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Bar */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-slate-400 hover:text-slate-600 transition-colors">
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900">
                  W<span className="text-blue-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">Admin Dashboard</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {!loading && !error && (
                <span className="flex items-center gap-1.5 text-xs font-medium text-green-600 bg-green-50 border border-green-200 px-2.5 py-1 rounded-full">
                  <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                  Live
                </span>
              )}
              {error && (
                <span className="flex items-center gap-1.5 text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full">
                  <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
                  Demo Mode
                </span>
              )}
              <nav className="hidden md:flex items-center gap-1">
                <Link href="/admin/clearing" className="text-sm text-slate-500 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
                  Clearing
                </Link>
                <Link href="/admin/agents" className="text-sm text-slate-500 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
                  Agents
                </Link>
                <Link href="/admin/ledger" className="text-sm text-slate-500 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
                  Ledger
                </Link>
              </nav>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mb-4" />
            <p className="text-slate-500">Loading admin dashboard...</p>
          </div>
        )}

        {/* Error Banner */}
        {error && !loading && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3 mb-6">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">Could not connect to backend</p>
              <p className="text-xs text-amber-600 mt-1">
                Showing demo data. Start the FastAPI backend for live data.
              </p>
            </div>
          </div>
        )}

        {!loading && (
          <>
            {/* Stats Cards Row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-blue-100 p-2 rounded-lg">
                    <Building2 className="w-5 h-5 text-blue-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Active Supply</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{overview.active_warehouses}</p>
                <p className="text-xs text-slate-400 mt-1">{formatNumber(overview.total_sqft)} total sqft</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-green-100 p-2 rounded-lg">
                    <Users className="w-5 h-5 text-green-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Active Demand</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{overview.active_buyers}</p>
                <p className="text-xs text-slate-400 mt-1">Buyers with active needs</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-purple-100 p-2 rounded-lg">
                    <FileText className="w-5 h-5 text-purple-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Active Deals</span>
                </div>
                <p className="text-2xl font-bold text-slate-900">{overview.active_deals}</p>
                <p className="text-xs text-slate-400 mt-1">Across all stages</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm bg-gradient-to-br from-white to-emerald-50">
                <div className="flex items-center gap-3 mb-2">
                  <div className="bg-emerald-100 p-2 rounded-lg">
                    <DollarSign className="w-5 h-5 text-emerald-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Monthly Revenue</span>
                </div>
                <p className="text-2xl font-bold text-emerald-700">{formatCurrency(overview.monthly_revenue)}</p>
                <p className="text-xs text-slate-400 mt-1">WEx spread captured</p>
              </div>
            </div>

            {/* Two-column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              {/* Left Column (3/5 = 60%) */}
              <div className="lg:col-span-3 space-y-6">
                {/* Clearing Engine Visualization */}
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                  <div className="flex items-center justify-between mb-5">
                    <div className="flex items-center gap-2">
                      <Zap className="w-5 h-5 text-blue-600" />
                      <h2 className="text-lg font-semibold text-slate-900">Clearing Engine</h2>
                    </div>
                    <Link
                      href="/admin/clearing"
                      className="text-sm text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
                    >
                      Full View <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>

                  {/* Supply → WEx → Demand visualization */}
                  <div className="grid grid-cols-3 gap-4">
                    {/* Supply Side */}
                    <div>
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Supply</p>
                      <div className="space-y-2">
                        {supply.map((node) => (
                          <div key={node.id} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                            <div className="flex items-center gap-1.5 mb-1">
                              <CircleDot className={`w-3 h-3 ${STATUS_DOT[node.status] || "text-gray-400"}`} />
                              <span className="text-xs font-medium text-slate-700 truncate">{node.label}</span>
                            </div>
                            <p className="text-xs text-slate-400 pl-4.5">{node.detail}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Center - WEx Clearing */}
                    <div className="flex flex-col items-center justify-center">
                      <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-200 mb-3">
                        <span className="text-white font-bold text-sm">WEx</span>
                      </div>
                      <p className="text-xs font-semibold text-slate-500 mb-2">Clearing House</p>
                      {/* Connection lines visualization */}
                      <div className="space-y-1.5 w-full">
                        {supply.filter((n) => n.status === "matched").map((_, i) => (
                          <div key={i} className="flex items-center gap-1">
                            <div className="h-px flex-1 bg-green-300" />
                            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                            <div className="h-px flex-1 bg-green-300" />
                          </div>
                        ))}
                        {supply.filter((n) => n.status === "searching").map((_, i) => (
                          <div key={`s-${i}`} className="flex items-center gap-1">
                            <div className="h-px flex-1 bg-blue-200 border-dashed" />
                            <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                            <div className="h-px flex-1 bg-blue-200 border-dashed" />
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 flex gap-3 text-xs text-slate-400">
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> Matched</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400" /> Searching</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400" /> Pending</span>
                      </div>
                    </div>

                    {/* Demand Side */}
                    <div>
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Demand</p>
                      <div className="space-y-2">
                        {demand.map((node) => (
                          <div key={node.id} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                            <div className="flex items-center gap-1.5 mb-1">
                              <CircleDot className={`w-3 h-3 ${STATUS_DOT[node.status] || "text-gray-400"}`} />
                              <span className="text-xs font-medium text-slate-700 truncate">{node.label}</span>
                            </div>
                            <p className="text-xs text-slate-400 pl-4.5">{node.detail}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Recent Deals Table */}
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-slate-900">Recent Deals</h2>
                    <span className="text-xs text-slate-400">{deals.length} deals</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">City</th>
                          <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Buyer</th>
                          <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Sqft</th>
                          <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Supplier</th>
                          <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Buyer</th>
                          <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Spread</th>
                          <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">WEx Rev</th>
                          <th className="text-center py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                          <th className="text-center py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {deals.slice(0, 10).map((deal) => (
                          <tr key={deal.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                            <td className="py-2.5 px-2 text-slate-700">{deal.warehouse_city}</td>
                            <td className="py-2.5 px-2 text-slate-700">{deal.buyer_company}</td>
                            <td className="py-2.5 px-2 text-right text-slate-600">{formatNumber(deal.sqft)}</td>
                            <td className="py-2.5 px-2 text-right text-slate-600">${deal.supplier_rate.toFixed(2)}</td>
                            <td className="py-2.5 px-2 text-right text-slate-600">${deal.buyer_rate.toFixed(2)}</td>
                            <td className="py-2.5 px-2 text-right font-medium text-emerald-600">{deal.spread_pct.toFixed(1)}%</td>
                            <td className="py-2.5 px-2 text-right font-medium text-emerald-600">{formatCurrency(deal.monthly_wex_revenue)}</td>
                            <td className="py-2.5 px-2 text-center">{getStatusBadge(deal.status)}</td>
                            <td className="py-2.5 px-2 text-center">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${deal.deal_type === "instant_book" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600"}`}>
                                {deal.deal_type === "instant_book" ? "Instant" : "Standard"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Right Column (2/5 = 40%) */}
              <div className="lg:col-span-2 space-y-6">
                {/* Agent Activity Feed */}
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Activity className="w-5 h-5 text-purple-600" />
                      <h2 className="text-lg font-semibold text-slate-900">Agent Activity</h2>
                    </div>
                    <Link
                      href="/admin/agents"
                      className="text-sm text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
                    >
                      View All <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                  <div className="space-y-3 max-h-[480px] overflow-y-auto">
                    {agents.slice(0, 10).map((action) => {
                      const color = getAgentColor(action.agent);
                      return (
                        <div key={action.id} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
                          <span className={`${color.bg} ${color.text} text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap mt-0.5`}>
                            {action.agent.replace(" Agent", "")}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-slate-700 leading-snug">{action.action}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs text-slate-400">{action.timestamp}</span>
                              <span className="text-xs text-slate-300">|</span>
                              <span className="text-xs text-slate-400">{action.latency_ms}ms</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Principal Ledger Summary */}
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <BookOpen className="w-5 h-5 text-emerald-600" />
                      <h2 className="text-lg font-semibold text-slate-900">Principal Ledger</h2>
                    </div>
                    <Link
                      href="/admin/ledger"
                      className="text-sm text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
                    >
                      Full Ledger <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>

                  <div className="space-y-4">
                    {/* Buyer Payments In */}
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm text-slate-600">Buyer Payments In</span>
                        <span className="text-sm font-semibold text-green-600">{formatCurrency(ledger.total_buyer_payments)}</span>
                      </div>
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div className="h-full bg-green-400 rounded-full" style={{ width: "100%" }} />
                      </div>
                    </div>

                    {/* Supplier Payments Out */}
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm text-slate-600">Supplier Payments Out</span>
                        <span className="text-sm font-semibold text-blue-600">{formatCurrency(ledger.total_supplier_payments)}</span>
                      </div>
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-400 rounded-full"
                          style={{
                            width: ledger.total_buyer_payments > 0
                              ? `${(ledger.total_supplier_payments / ledger.total_buyer_payments) * 100}%`
                              : "0%",
                          }}
                        />
                      </div>
                    </div>

                    {/* Net WEx Revenue */}
                    <div className="pt-3 border-t border-gray-100">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-slate-900">Net WEx Revenue</span>
                        <span className="text-lg font-bold text-emerald-600">{formatCurrency(ledger.net_wex_revenue)}</span>
                      </div>
                      <div className="mt-2 h-3 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500 rounded-full"
                          style={{
                            width: ledger.total_buyer_payments > 0
                              ? `${(ledger.net_wex_revenue / ledger.total_buyer_payments) * 100}%`
                              : "0%",
                          }}
                        />
                      </div>
                      <p className="text-xs text-slate-400 mt-1.5">
                        {ledger.total_buyer_payments > 0
                          ? `${((ledger.net_wex_revenue / ledger.total_buyer_payments) * 100).toFixed(1)}% margin`
                          : "No data"}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="text-center py-6 border-t border-gray-100 mt-8">
              <p className="text-xs text-slate-400">
                Powered by W<span className="text-blue-500 font-semibold">Ex</span> Clearing House | Admin Console
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
