"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PaymentRecord } from "@/types/supplier";

function formatCurrency(amount: number | undefined): string {
  if (amount === undefined || amount === null) return "—";
  return `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function statusColor(status: string): string {
  switch (status) {
    case "paid":
      return "bg-green-100 text-green-700";
    case "invoiced":
      return "bg-yellow-100 text-yellow-700";
    case "overdue":
      return "bg-red-100 text-red-700";
    case "upcoming":
      return "bg-gray-100 text-gray-600";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

// Demo data fallback
const demoPayments: PaymentRecord[] = [
  {
    id: "pay-001",
    engagementId: "eng-1234",
    periodStart: "2026-01-01",
    periodEnd: "2026-01-31",
    buyerAmount: 22260,
    buyerStatus: "paid",
    supplierStatus: "deposited",
    buyerInvoicedAt: "2025-12-28T00:00:00Z",
    buyerPaidAt: "2026-01-02T00:00:00Z",
  },
  {
    id: "pay-002",
    engagementId: "eng-1234",
    periodStart: "2026-02-01",
    periodEnd: "2026-02-28",
    buyerAmount: 22260,
    buyerStatus: "invoiced",
    supplierStatus: "scheduled",
    buyerInvoicedAt: "2026-01-28T00:00:00Z",
  },
  {
    id: "pay-003",
    engagementId: "eng-1234",
    periodStart: "2026-03-01",
    periodEnd: "2026-03-31",
    buyerAmount: 22260,
    buyerStatus: "upcoming",
    supplierStatus: "upcoming",
  },
];

export default function BuyerPaymentsPage() {
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const loadPayments = useCallback(async () => {
    try {
      const data = await api.getBuyerPayments();
      setPayments(data);
    } catch {
      setPayments(demoPayments);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPayments();
  }, [loadPayments]);

  const totalPaid = payments
    .filter((p) => p.buyerStatus === "paid")
    .reduce((sum, p) => sum + (p.buyerAmount || 0), 0);
  const totalUpcoming = payments
    .filter((p) => p.buyerStatus === "upcoming" || p.buyerStatus === "invoiced")
    .reduce((sum, p) => sum + (p.buyerAmount || 0), 0);
  const totalOverdue = payments
    .filter((p) => p.buyerStatus === "overdue")
    .reduce((sum, p) => sum + (p.buyerAmount || 0), 0);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading payments...</div>;
  }

  return (
    <div className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Payments</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="text-sm text-gray-500">Total Paid</div>
          <div className="text-xl font-bold text-green-700">
            {formatCurrency(totalPaid)}
          </div>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="text-sm text-gray-500">Upcoming</div>
          <div className="text-xl font-bold text-yellow-700">
            {formatCurrency(totalUpcoming)}
          </div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="text-sm text-gray-500">Overdue</div>
          <div className="text-xl font-bold text-red-700">
            {formatCurrency(totalOverdue)}
          </div>
        </div>
      </div>

      {/* Payment table */}
      {payments.length === 0 ? (
        <div className="text-center py-12 text-gray-400">No payments yet.</div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Period
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Amount
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Status
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Invoiced
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">
                  Paid
                </th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    {p.periodStart} — {p.periodEnd}
                  </td>
                  <td className="px-4 py-3 font-medium">
                    {formatCurrency(p.buyerAmount)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${statusColor(
                        p.buyerStatus
                      )}`}
                    >
                      {p.buyerStatus}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {p.buyerInvoicedAt
                      ? new Date(p.buyerInvoicedAt).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {p.buyerPaidAt
                      ? new Date(p.buyerPaidAt).toLocaleDateString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
