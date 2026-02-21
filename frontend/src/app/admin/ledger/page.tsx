"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  DollarSign,
  Loader2,
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  TrendingUp,
  BookOpen,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface LedgerSummary {
  total_buyer_payments: number;
  total_supplier_payments: number;
  net_wex_revenue: number;
}

interface SpreadEntry {
  deal_id: string;
  warehouse_city: string;
  buyer_company: string;
  sqft: number;
  supplier_rate: number;
  buyer_rate: number;
  spread_pct: number;
  monthly_spread: number;
}

interface LedgerEntry {
  id: string;
  date: string;
  amount: number;
  description: string;
  deal_ref: string;
  status: string;
}

/* ------------------------------------------------------------------ */
/*  Demo data                                                          */
/* ------------------------------------------------------------------ */
const DEMO_SUMMARY: LedgerSummary = {
  total_buyer_payments: 127500,
  total_supplier_payments: 108750,
  net_wex_revenue: 18750,
};

const DEMO_SPREADS: SpreadEntry[] = [
  { deal_id: "D-1042", warehouse_city: "Dallas", buyer_company: "Acme Logistics", sqft: 25000, supplier_rate: 8.50, buyer_rate: 9.75, spread_pct: 14.7, monthly_spread: 3125 },
  { deal_id: "D-1038", warehouse_city: "Fort Worth", buyer_company: "FreshCo Foods", sqft: 60000, supplier_rate: 9.00, buyer_rate: 10.25, spread_pct: 13.9, monthly_spread: 7500 },
  { deal_id: "D-1035", warehouse_city: "Plano", buyer_company: "QuickShip Inc", sqft: 40000, supplier_rate: 7.25, buyer_rate: 8.50, spread_pct: 17.2, monthly_spread: 5000 },
  { deal_id: "D-1031", warehouse_city: "Irving", buyer_company: "TechParts Co", sqft: 15000, supplier_rate: 10.00, buyer_rate: 11.50, spread_pct: 15.0, monthly_spread: 2250 },
  { deal_id: "D-1028", warehouse_city: "Arlington", buyer_company: "MedSupply LLC", sqft: 20000, supplier_rate: 11.00, buyer_rate: 12.75, spread_pct: 15.9, monthly_spread: 3500 },
];

const DEMO_BUYER_ENTRIES: LedgerEntry[] = [
  { id: "be1", date: "Feb 5, 2026", amount: 24375, description: "Monthly lease - Acme Logistics", deal_ref: "D-1042", status: "received" },
  { id: "be2", date: "Feb 5, 2026", amount: 61500, description: "Monthly lease - FreshCo Foods", deal_ref: "D-1038", status: "received" },
  { id: "be3", date: "Feb 4, 2026", amount: 34000, description: "Monthly lease - QuickShip Inc", deal_ref: "D-1035", status: "pending" },
  { id: "be4", date: "Feb 3, 2026", amount: 17250, description: "Monthly lease - TechParts Co", deal_ref: "D-1031", status: "received" },
  { id: "be5", date: "Feb 3, 2026", amount: 25500, description: "Monthly lease - MedSupply LLC", deal_ref: "D-1028", status: "received" },
  { id: "be6", date: "Jan 5, 2026", amount: 24375, description: "Monthly lease - Acme Logistics", deal_ref: "D-1042", status: "received" },
  { id: "be7", date: "Jan 5, 2026", amount: 61500, description: "Monthly lease - FreshCo Foods", deal_ref: "D-1038", status: "received" },
];

const DEMO_SUPPLIER_ENTRIES: LedgerEntry[] = [
  { id: "se1", date: "Feb 6, 2026", amount: 21250, description: "Payout - Downtown Distribution", deal_ref: "D-1042", status: "sent" },
  { id: "se2", date: "Feb 6, 2026", amount: 54000, description: "Payout - Airport Logistics Hub", deal_ref: "D-1038", status: "sent" },
  { id: "se3", date: "Feb 5, 2026", amount: 29000, description: "Payout - Northside Warehouse", deal_ref: "D-1035", status: "pending" },
  { id: "se4", date: "Feb 4, 2026", amount: 15000, description: "Payout - Commerce Park", deal_ref: "D-1031", status: "sent" },
  { id: "se5", date: "Feb 4, 2026", amount: 22000, description: "Payout - Southside Flex Space", deal_ref: "D-1028", status: "sent" },
  { id: "se6", date: "Jan 6, 2026", amount: 21250, description: "Payout - Downtown Distribution", deal_ref: "D-1042", status: "sent" },
  { id: "se7", date: "Jan 6, 2026", amount: 54000, description: "Payout - Airport Logistics Hub", deal_ref: "D-1038", status: "sent" },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function LedgerPage() {
  const [summary, setSummary] = useState<LedgerSummary>(DEMO_SUMMARY);
  const [spreads, setSpreads] = useState<SpreadEntry[]>(DEMO_SPREADS);
  const [buyerEntries, setBuyerEntries] = useState<LedgerEntry[]>(DEMO_BUYER_ENTRIES);
  const [supplierEntries, setSupplierEntries] = useState<LedgerEntry[]>(DEMO_SUPPLIER_ENTRIES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const result = await api.adminLedger();
      if (result.summary) setSummary(result.summary);
      if (result.spreads) setSpreads(result.spreads);
      if (result.buyer_entries) setBuyerEntries(result.buyer_entries);
      if (result.supplier_entries) setSupplierEntries(result.supplier_entries);
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

  function getEntryStatusBadge(status: string) {
    const styles: Record<string, string> = {
      received: "bg-green-100 text-green-700",
      sent: "bg-blue-100 text-blue-700",
      pending: "bg-amber-100 text-amber-700",
      failed: "bg-red-100 text-red-700",
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
                <span className="text-sm font-medium text-slate-600">Principal Ledger</span>
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
            <p className="text-slate-500">Loading ledger data...</p>
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
            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <div className="bg-green-100 p-2.5 rounded-lg">
                    <ArrowDownLeft className="w-5 h-5 text-green-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Buyer Payments In</span>
                </div>
                <p className="text-3xl font-bold text-green-600">{formatCurrency(summary.total_buyer_payments)}</p>
                <p className="text-xs text-slate-400 mt-2">Total received from buyers</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <div className="bg-blue-100 p-2.5 rounded-lg">
                    <ArrowUpRight className="w-5 h-5 text-blue-600" />
                  </div>
                  <span className="text-sm font-medium text-slate-500">Supplier Payments Out</span>
                </div>
                <p className="text-3xl font-bold text-blue-600">{formatCurrency(summary.total_supplier_payments)}</p>
                <p className="text-xs text-slate-400 mt-2">Total paid to suppliers</p>
              </div>

              <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-xl border border-emerald-200 p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <div className="bg-emerald-200 p-2.5 rounded-lg">
                    <TrendingUp className="w-5 h-5 text-emerald-700" />
                  </div>
                  <span className="text-sm font-medium text-emerald-700">WEx Net Revenue</span>
                </div>
                <p className="text-3xl font-bold text-emerald-700">{formatCurrency(summary.net_wex_revenue)}</p>
                <p className="text-xs text-emerald-600 mt-2">
                  {summary.total_buyer_payments > 0
                    ? `${((summary.net_wex_revenue / summary.total_buyer_payments) * 100).toFixed(1)}% margin on buyer payments`
                    : "The spread captured by WEx"}
                </p>
              </div>
            </div>

            {/* Revenue Breakdown / Spread Analysis */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-8">
              <div className="flex items-center gap-2 mb-4">
                <BookOpen className="w-5 h-5 text-emerald-600" />
                <h2 className="text-lg font-semibold text-slate-900">Revenue Breakdown</h2>
                <span className="text-xs text-slate-400 ml-auto">Spread analysis per deal</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Deal</th>
                      <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">City</th>
                      <th className="text-left py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Buyer</th>
                      <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Sqft</th>
                      <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Supplier Rate</th>
                      <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Buyer Rate</th>
                      <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Spread %</th>
                      <th className="text-right py-2.5 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Monthly WEx Rev</th>
                    </tr>
                  </thead>
                  <tbody>
                    {spreads.map((s) => (
                      <tr key={s.deal_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-2 text-slate-600 font-mono text-xs">{s.deal_id}</td>
                        <td className="py-3 px-2 text-slate-700">{s.warehouse_city}</td>
                        <td className="py-3 px-2 text-slate-700">{s.buyer_company}</td>
                        <td className="py-3 px-2 text-right text-slate-600">{formatNumber(s.sqft)}</td>
                        <td className="py-3 px-2 text-right text-slate-600">${s.supplier_rate.toFixed(2)}</td>
                        <td className="py-3 px-2 text-right text-slate-600">${s.buyer_rate.toFixed(2)}</td>
                        <td className="py-3 px-2 text-right font-medium text-emerald-600">{s.spread_pct.toFixed(1)}%</td>
                        <td className="py-3 px-2 text-right font-bold text-emerald-600">{formatCurrency(s.monthly_spread)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-gray-200">
                      <td colSpan={6} className="py-3 px-2 text-right text-sm font-semibold text-slate-700">Total Monthly WEx Revenue</td>
                      <td className="py-3 px-2 text-right text-sm font-medium text-emerald-600">
                        {summary.total_buyer_payments > 0
                          ? `${((summary.net_wex_revenue / summary.total_buyer_payments) * 100).toFixed(1)}%`
                          : "--"}
                      </td>
                      <td className="py-3 px-2 text-right text-lg font-bold text-emerald-600">
                        {formatCurrency(spreads.reduce((sum, s) => sum + s.monthly_spread, 0))}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            {/* Recent Transactions - Two Column */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Buyer Ledger Entries */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="bg-green-100 p-1.5 rounded-lg">
                    <ArrowDownLeft className="w-4 h-4 text-green-600" />
                  </div>
                  <h2 className="text-base font-semibold text-slate-900">Buyer Payments Received</h2>
                </div>
                <div className="space-y-0 max-h-[500px] overflow-y-auto">
                  {buyerEntries.map((entry) => (
                    <div key={entry.id} className="flex items-center justify-between py-3 border-b border-gray-50 last:border-0">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <p className="text-sm font-medium text-slate-700 truncate">{entry.description}</p>
                          {getEntryStatusBadge(entry.status)}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <span>{entry.date}</span>
                          <span className="text-slate-300">|</span>
                          <span className="font-mono">{entry.deal_ref}</span>
                        </div>
                      </div>
                      <div className="ml-4 text-right">
                        <p className="text-sm font-bold text-green-600">+{formatCurrency(entry.amount)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Supplier Ledger Entries */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="bg-blue-100 p-1.5 rounded-lg">
                    <ArrowUpRight className="w-4 h-4 text-blue-600" />
                  </div>
                  <h2 className="text-base font-semibold text-slate-900">Supplier Payments Made</h2>
                </div>
                <div className="space-y-0 max-h-[500px] overflow-y-auto">
                  {supplierEntries.map((entry) => (
                    <div key={entry.id} className="flex items-center justify-between py-3 border-b border-gray-50 last:border-0">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <p className="text-sm font-medium text-slate-700 truncate">{entry.description}</p>
                          {getEntryStatusBadge(entry.status)}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <span>{entry.date}</span>
                          <span className="text-slate-300">|</span>
                          <span className="font-mono">{entry.deal_ref}</span>
                        </div>
                      </div>
                      <div className="ml-4 text-right">
                        <p className="text-sm font-bold text-blue-600">-{formatCurrency(entry.amount)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* WEx Revenue Summary Bar */}
            <div className="mt-8 bg-gradient-to-r from-emerald-50 to-emerald-100 rounded-xl border border-emerald-200 p-6">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <DollarSign className="w-5 h-5 text-emerald-600" />
                  <h3 className="text-base font-semibold text-emerald-800">WEx Revenue Flow</h3>
                </div>
                <span className="text-sm font-bold text-emerald-700">{formatCurrency(summary.net_wex_revenue)} net</span>
              </div>
              <div className="h-4 bg-white rounded-full overflow-hidden border border-emerald-200 relative">
                {/* Supplier portion */}
                <div
                  className="absolute left-0 top-0 h-full bg-blue-300 rounded-l-full"
                  style={{
                    width: summary.total_buyer_payments > 0
                      ? `${(summary.total_supplier_payments / summary.total_buyer_payments) * 100}%`
                      : "0%",
                  }}
                />
                {/* WEx spread portion */}
                <div
                  className="absolute top-0 h-full bg-emerald-400 rounded-r-full"
                  style={{
                    left: summary.total_buyer_payments > 0
                      ? `${(summary.total_supplier_payments / summary.total_buyer_payments) * 100}%`
                      : "0%",
                    width: summary.total_buyer_payments > 0
                      ? `${(summary.net_wex_revenue / summary.total_buyer_payments) * 100}%`
                      : "0%",
                  }}
                />
              </div>
              <div className="flex items-center justify-between mt-2 text-xs">
                <span className="text-blue-600 font-medium">Supplier: {formatCurrency(summary.total_supplier_payments)}</span>
                <span className="text-emerald-700 font-bold">WEx Spread: {formatCurrency(summary.net_wex_revenue)}</span>
                <span className="text-slate-500">Total In: {formatCurrency(summary.total_buyer_payments)}</span>
              </div>
            </div>

            {/* Footer */}
            <div className="text-center py-6 border-t border-gray-100 mt-8">
              <p className="text-xs text-slate-400">
                Powered by W<span className="text-blue-500 font-semibold">Ex</span> Clearing House | Principal Ledger
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
