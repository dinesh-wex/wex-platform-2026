"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Filter,
  FileText,
  FileSpreadsheet,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useSupplier } from "@/components/supplier/SupplierAuthProvider";
import MetricCard from "@/components/supplier/MetricCard";
import StatusBadge from "@/components/supplier/StatusBadge";
import { demoPayments, demoPaymentSummary } from "@/lib/supplier-demo-data";
import type { Payment, PaymentSummary } from "@/types/supplier";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function fmt(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatType(type: string): string {
  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------------ */
/*  Filter State                                                       */
/* ------------------------------------------------------------------ */

interface Filters {
  from: string;
  to: string;
  property_id: string;
  status: string;
}

const emptyFilters: Filters = { from: "", to: "", property_id: "", status: "" };

/* ------------------------------------------------------------------ */
/*  Page Component                                                     */
/* ------------------------------------------------------------------ */

export default function PaymentsPage() {
  const { warehouses } = useSupplier();

  const [payments, setPayments] = useState<Payment[]>(demoPayments);
  const [summary, setSummary] = useState<PaymentSummary>(demoPaymentSummary);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(emptyFilters);

  // ---- Fetch data ----
  const fetchData = useCallback(async (f: Filters) => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {};
      if (f.from) params.from = f.from;
      if (f.to) params.to = f.to;
      if (f.property_id) params.property_id = f.property_id;
      if (f.status) params.status = f.status;
      const [paymentsRes, summaryRes] = await Promise.all([
        api.getPayments(params as any),
        api.getPaymentsSummary(),
      ]);
      setPayments(Array.isArray(paymentsRes) ? paymentsRes : paymentsRes.payments ?? demoPayments);
      setSummary(summaryRes ?? demoPaymentSummary);
    } catch {
      setPayments(demoPayments);
      setSummary(demoPaymentSummary);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(emptyFilters);
  }, [fetchData]);

  // ---- Apply filters ----
  const handleApplyFilters = () => {
    setAppliedFilters({ ...filters });
    fetchData(filters);
  };

  // ---- Client-side filtering (for demo fallback) ----
  const displayPayments = useMemo(() => {
    let list = [...payments];
    const f = appliedFilters;

    if (f.from) {
      const from = new Date(f.from);
      list = list.filter((p) => new Date(p.date) >= from);
    }
    if (f.to) {
      const to = new Date(f.to);
      list = list.filter((p) => new Date(p.date) <= to);
    }
    if (f.property_id) {
      list = list.filter((p) => p.property_id === f.property_id);
    }
    if (f.status) {
      list = list.filter((p) => p.status === f.status);
    }
    return list.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [payments, appliedFilters]);

  // ---- Export handlers ----
  const handleExport = async (format: "csv" | "pdf") => {
    try {
      await api.exportPayments(format, filters.from || undefined, filters.to || undefined);
    } catch {
      alert(`Export as ${format.toUpperCase()} is coming soon. This feature will be available once the backend is ready.`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ---- Header ---- */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-8"
        >
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">
            Payments
          </h1>
          <p className="text-slate-500 mt-1">
            Track your earnings and upcoming payouts.
          </p>
        </motion.div>

        {/* ---- Hero Metric Cards ---- */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricCard
            label="Total Earned"
            value={summary.total_earned}
            format="currency"
            sublabel="Lifetime"
          />
          <MetricCard
            label="This Month"
            value={summary.this_month}
            format="currency"
            sublabel={new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" })}
          />
          <MetricCard
            label="Upcoming Payout"
            value={summary.next_deposit}
            format="currency"
            sublabel={summary.next_deposit_date ? fmtDate(summary.next_deposit_date) : "Scheduled"}
          />
          <MetricCard
            label="Active Leases"
            value={summary.active_engagements}
            format="number"
            sublabel="Generating revenue"
          />
        </div>

        {/* ---- Filters ---- */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="bg-white rounded-xl shadow-sm p-4 sm:p-6 mb-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <Filter className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-700">Filters</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs text-slate-500 mb-1">From</label>
              <input
                type="date"
                value={filters.from}
                onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">To</label>
              <input
                type="date"
                value={filters.to}
                onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Property</label>
              <select
                value={filters.property_id}
                onChange={(e) => setFilters((f) => ({ ...f, property_id: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              >
                <option value="">All Properties</option>
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name || w.address}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Status</label>
              <select
                value={filters.status}
                onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              >
                <option value="">All Statuses</option>
                <option value="deposited">Deposited</option>
                <option value="scheduled">Scheduled</option>
                <option value="upcoming">Upcoming</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleApplyFilters}
                className="w-full rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-700 transition-colors"
              >
                Apply Filters
              </button>
            </div>
          </div>
        </motion.div>

        {/* ---- Export Buttons ---- */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => handleExport("csv")}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
          >
            <FileSpreadsheet className="w-4 h-4" />
            Download CSV
          </button>
          <button
            onClick={() => handleExport("pdf")}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
          >
            <FileText className="w-4 h-4" />
            Download PDF
          </button>
        </div>

        {/* ---- Transaction Table (Desktop) ---- */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="hidden md:block bg-white rounded-xl shadow-sm overflow-hidden"
        >
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Date
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Property
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Engagement
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Type
                </th>
                <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Amount
                </th>
                <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wide px-6 py-4">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    Loading...
                  </td>
                </tr>
              ) : displayPayments.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    No payments found matching your filters.
                  </td>
                </tr>
              ) : (
                displayPayments.map((payment, i) => (
                  <motion.tr
                    key={payment.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.04 }}
                    className="hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-6 py-4 text-sm text-slate-700">
                      {fmtDate(payment.date)}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-700 max-w-[200px] truncate">
                      {payment.property_address}
                    </td>
                    <td className="px-6 py-4 text-sm font-mono">
                      <Link
                        href={`/supplier/engagements/${payment.engagement_id}`}
                        className="text-emerald-600 hover:text-emerald-700"
                        onClick={(e) => e.stopPropagation()}
                      >
                        #{payment.engagement_id.replace("eng-", "")}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-600">
                      {formatType(payment.type)}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-900 font-semibold text-right">
                      {fmt(payment.amount)}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={payment.status} size="sm" />
                    </td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </motion.div>

        {/* ---- Transaction Cards (Mobile) ---- */}
        <div className="md:hidden space-y-3">
          {loading ? (
            <div className="text-center py-12 text-slate-400">Loading...</div>
          ) : displayPayments.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              No payments found matching your filters.
            </div>
          ) : (
            displayPayments.map((payment, i) => (
              <motion.div
                key={payment.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: i * 0.05 }}
                className="bg-white rounded-xl shadow-sm p-4"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {fmt(payment.amount)}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {fmtDate(payment.date)}
                    </p>
                  </div>
                  <StatusBadge status={payment.status} size="sm" />
                </div>

                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Property</span>
                    <span className="text-slate-700 text-right max-w-[60%] truncate">
                      {payment.property_address}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Engagement</span>
                    <Link
                      href={`/supplier/engagements/${payment.engagement_id}`}
                      className="text-emerald-600 hover:text-emerald-700 font-mono"
                    >
                      #{payment.engagement_id.replace("eng-", "")}
                    </Link>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Type</span>
                    <span className="text-slate-700">
                      {formatType(payment.type)}
                    </span>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
