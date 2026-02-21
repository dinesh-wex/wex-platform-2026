"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  Building2,
  MapPin,
  DollarSign,
  Calendar,
  Shield,
  CheckCircle2,
  Clock,
  CalendarCheck,
  FileText,
  CreditCard,
  Eye,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface Deal {
  id: string;
  status: string;
  warehouse_id?: string;
  warehouse_name?: string;
  warehouse_address?: string;
  warehouse_city?: string;
  warehouse_state?: string;
  warehouse_zip?: string;
  primary_image_url?: string | null;
  buyer_rate?: number;
  monthly_cost?: number;
  term_months?: number;
  sqft?: number;
  start_date?: string;
  end_date?: string;
  deal_type?: string;
  tour_date?: string;
  tour_time?: string;
  payment_schedule?: PaymentEntry[];
  created_at?: string;
}

interface PaymentEntry {
  month: number;
  due_date: string;
  amount: number;
  status: string;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function BuyerDeals() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDeal, setExpandedDeal] = useState<string | null>(null);

  useEffect(() => {
    loadDeals();
  }, []);

  async function loadDeals() {
    setLoading(true);
    setError(null);

    const savedBuyer = localStorage.getItem("wex_buyer");
    if (!savedBuyer) {
      setError("No buyer profile found. Please register first.");
      setLoading(false);
      return;
    }

    let buyerId: string;
    try {
      buyerId = JSON.parse(savedBuyer).id;
    } catch {
      setError("Invalid buyer profile. Please register again.");
      setLoading(false);
      return;
    }

    try {
      const data = await api.getBuyerDeals(buyerId);
      const dealsList = Array.isArray(data) ? data : data.deals || [];
      setDeals(dealsList);
    } catch (err: any) {
      setError(err.message || "Failed to load deals");
      // Demo data
      setDeals([
        {
          id: "deal-demo-1",
          status: "active",
          warehouse_id: "wh-demo-1",
          warehouse_name: "Downtown Distribution Center",
          warehouse_address: "1200 Industrial Blvd",
          warehouse_city: "Dallas",
          warehouse_state: "TX",
          warehouse_zip: "75201",
          primary_image_url: null,
          buyer_rate: 9.75,
          monthly_cost: 24375,
          term_months: 12,
          sqft: 25000,
          start_date: "2025-02-01",
          end_date: "2026-01-31",
          deal_type: "instant_book",
          created_at: "2025-01-15T10:30:00Z",
          payment_schedule: [
            { month: 1, due_date: "2025-02-01", amount: 24375, status: "paid" },
            { month: 2, due_date: "2025-03-01", amount: 24375, status: "paid" },
            { month: 3, due_date: "2025-04-01", amount: 24375, status: "upcoming" },
            { month: 4, due_date: "2025-05-01", amount: 24375, status: "scheduled" },
            { month: 5, due_date: "2025-06-01", amount: 24375, status: "scheduled" },
            { month: 6, due_date: "2025-07-01", amount: 24375, status: "scheduled" },
          ],
        },
        {
          id: "deal-demo-2",
          status: "tour_scheduled",
          warehouse_id: "wh-demo-2",
          warehouse_name: "Airport Logistics Hub",
          warehouse_address: "8900 Cargo Way",
          warehouse_city: "Fort Worth",
          warehouse_state: "TX",
          warehouse_zip: "76177",
          primary_image_url: null,
          buyer_rate: 11.25,
          monthly_cost: 56250,
          term_months: 24,
          sqft: 50000,
          deal_type: "schedule_tour",
          tour_date: "2025-02-10",
          tour_time: "2:00 PM",
          created_at: "2025-01-28T14:00:00Z",
        },
        {
          id: "deal-demo-3",
          status: "terms_accepted",
          warehouse_id: "wh-demo-3",
          warehouse_name: "Northside Flex Space",
          warehouse_address: "4500 Commerce Dr",
          warehouse_city: "Plano",
          warehouse_state: "TX",
          warehouse_zip: "75024",
          primary_image_url: null,
          buyer_rate: 8.5,
          monthly_cost: 12750,
          term_months: 6,
          sqft: 15000,
          deal_type: "instant_book",
          created_at: "2025-02-01T09:15:00Z",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function formatCurrency(amount: number): string {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount);
  }

  function formatNumber(num: number): string {
    return new Intl.NumberFormat("en-US").format(num);
  }

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function getStatusConfig(status: string): {
    label: string;
    bgClass: string;
    icon: React.ReactNode;
  } {
    switch (status) {
      case "active":
        return {
          label: "Active",
          bgClass: "bg-green-100 text-green-700",
          icon: <CheckCircle2 className="w-3.5 h-3.5" />,
        };
      case "confirmed":
        return {
          label: "Confirmed",
          bgClass: "bg-green-100 text-green-700",
          icon: <CheckCircle2 className="w-3.5 h-3.5" />,
        };
      case "terms_accepted":
        return {
          label: "Terms Accepted",
          bgClass: "bg-emerald-100 text-emerald-700",
          icon: <FileText className="w-3.5 h-3.5" />,
        };
      case "tour_scheduled":
        return {
          label: "Tour Scheduled",
          bgClass: "bg-sky-100 text-sky-700",
          icon: <CalendarCheck className="w-3.5 h-3.5" />,
        };
      case "pending":
        return {
          label: "Pending",
          bgClass: "bg-yellow-100 text-yellow-700",
          icon: <Clock className="w-3.5 h-3.5" />,
        };
      default:
        return {
          label: status.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
          bgClass: "bg-gray-100 text-gray-700",
          icon: <FileText className="w-3.5 h-3.5" />,
        };
    }
  }

  function toggleExpand(dealId: string) {
    setExpandedDeal((prev) => (prev === dealId ? null : dealId));
  }

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link
                href="/buyer"
                className="text-slate-400 hover:text-slate-600 transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900">
                  W<span className="text-blue-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">
                  My Deals
                </span>
              </div>
            </div>
            <Link
              href="/buyer/search"
              className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
            >
              Find More Space
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Insurance Badge */}
        <div className="mb-6 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 flex items-center gap-3">
          <Shield className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          <p className="text-sm text-emerald-800">
            <span className="font-semibold">
              All deals include WEx Occupancy Guarantee Insurance.
            </span>{" "}
            Your occupancy terms and rates are locked and guaranteed.
          </p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-center gap-3 mb-2">
              <div className="bg-green-100 p-2 rounded-lg">
                <FileText className="w-4 h-4 text-green-600" />
              </div>
              <span className="text-sm font-medium text-slate-500">
                Total Deals
              </span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{deals.length}</p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-center gap-3 mb-2">
              <div className="bg-blue-100 p-2 rounded-lg">
                <DollarSign className="w-4 h-4 text-blue-600" />
              </div>
              <span className="text-sm font-medium text-slate-500">
                Monthly Spend
              </span>
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {formatCurrency(
                deals
                  .filter(
                    (d) => d.status === "active" || d.status === "confirmed"
                  )
                  .reduce((sum, d) => sum + (d.monthly_cost || 0), 0)
              )}
            </p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-center gap-3 mb-2">
              <div className="bg-purple-100 p-2 rounded-lg">
                <Building2 className="w-4 h-4 text-purple-600" />
              </div>
              <span className="text-sm font-medium text-slate-500">
                Total Space
              </span>
            </div>
            <p className="text-2xl font-bold text-slate-900">
              {formatNumber(
                deals
                  .filter(
                    (d) => d.status === "active" || d.status === "confirmed"
                  )
                  .reduce((sum, d) => sum + (d.sqft || 0), 0)
              )}{" "}
              sqft
            </p>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mb-4" />
            <p className="text-slate-500">Loading your deals...</p>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3 mb-6">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                Could not connect to backend
              </p>
              <p className="text-xs text-amber-600 mt-1">
                Showing demo deals. Start the FastAPI backend for live data.
              </p>
            </div>
          </div>
        )}

        {/* No Deals */}
        {!loading && deals.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4">
              <FileText className="w-8 h-8 text-blue-600" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">
              No deals yet
            </h3>
            <p className="text-slate-500 max-w-md mx-auto mb-6">
              Start searching for warehouse space and accept a match to create
              your first deal.
            </p>
            <div className="flex items-center gap-3">
              <Link
                href="/buyer/options"
                className="inline-flex items-center gap-2 border border-blue-200 text-blue-600 px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-50 transition-colors"
              >
                View Options
              </Link>
              <Link
                href="/buyer/search"
                className="inline-flex items-center gap-2 bg-blue-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                Find Space
              </Link>
            </div>
          </div>
        )}

        {/* Deals List */}
        {!loading && deals.length > 0 && (
          <div className="space-y-4">
            {deals.map((deal) => {
              const statusConfig = getStatusConfig(deal.status);
              const isExpanded = expandedDeal === deal.id;

              return (
                <div
                  key={deal.id}
                  className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"
                >
                  {/* Main Deal Row */}
                  <div className="flex flex-col md:flex-row">
                    {/* Image */}
                    <div className="md:w-48 h-40 md:h-auto bg-gradient-to-br from-slate-200 to-slate-300 relative flex-shrink-0">
                      {deal.primary_image_url ? (
                        <img
                          src={deal.primary_image_url}
                          alt={deal.warehouse_name || "Warehouse"}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center min-h-[120px]">
                          <Building2 className="w-12 h-12 text-slate-400" />
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 p-5">
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-lg font-semibold text-slate-900">
                              {deal.warehouse_name || "Warehouse Space"}
                            </h3>
                            <span
                              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${statusConfig.bgClass}`}
                            >
                              {statusConfig.icon}
                              {statusConfig.label}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 text-sm text-slate-500">
                            <MapPin className="w-3.5 h-3.5 text-slate-400" />
                            <span>
                              {deal.warehouse_address}, {deal.warehouse_city},{" "}
                              {deal.warehouse_state} {deal.warehouse_zip}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Key Metrics */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                        <div>
                          <p className="text-xs text-slate-400">Your Rate</p>
                          <p className="text-sm font-semibold text-slate-900">
                            {deal.buyer_rate
                              ? `$${deal.buyer_rate.toFixed(2)}/sqft/mo`
                              : "TBD"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Monthly Cost</p>
                          <p className="text-sm font-semibold text-green-600">
                            {deal.monthly_cost
                              ? formatCurrency(deal.monthly_cost)
                              : "TBD"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Space</p>
                          <p className="text-sm font-semibold text-slate-900">
                            {deal.sqft
                              ? `${formatNumber(deal.sqft)} sqft`
                              : "TBD"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Term</p>
                          <p className="text-sm font-semibold text-slate-900">
                            {deal.term_months
                              ? `${deal.term_months} months`
                              : "TBD"}
                          </p>
                        </div>
                      </div>

                      {/* Tour Info (if tour scheduled) */}
                      {deal.status === "tour_scheduled" &&
                        deal.tour_date && (
                          <div className="bg-sky-50 border border-sky-200 rounded-lg px-4 py-3 flex items-center gap-3 mb-3">
                            <CalendarCheck className="w-5 h-5 text-sky-600 flex-shrink-0" />
                            <div>
                              <p className="text-sm font-medium text-sky-800">
                                Tour scheduled for{" "}
                                {formatDate(deal.tour_date)}
                                {deal.tour_time && ` at ${deal.tour_time}`}
                              </p>
                              <p className="text-xs text-sky-600 mt-0.5">
                                You will receive a confirmation email with
                                details
                              </p>
                            </div>
                          </div>
                        )}

                      {/* Date Range */}
                      {deal.start_date && deal.end_date && (
                        <div className="flex items-center gap-1.5 text-xs text-slate-500">
                          <Calendar className="w-3 h-3" />
                          <span>
                            {formatDate(deal.start_date)} -{" "}
                            {formatDate(deal.end_date)}
                          </span>
                        </div>
                      )}

                      {/* Expand/Collapse Button */}
                      <button
                        onClick={() => toggleExpand(deal.id)}
                        className="mt-3 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium"
                      >
                        {isExpanded ? (
                          <>
                            <ChevronUp className="w-4 h-4" />
                            Hide details
                          </>
                        ) : (
                          <>
                            <ChevronDown className="w-4 h-4" />
                            Show details
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Section */}
                  {isExpanded && (
                    <div className="border-t border-gray-200">
                      {/* Payment Schedule */}
                      {deal.payment_schedule &&
                        deal.payment_schedule.length > 0 && (
                          <div className="px-6 py-5">
                            <div className="flex items-center gap-2 mb-4">
                              <CreditCard className="w-4 h-4 text-slate-500" />
                              <h4 className="text-sm font-semibold text-slate-900">
                                Payment Schedule
                              </h4>
                            </div>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b border-gray-200">
                                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wider">
                                      Month
                                    </th>
                                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wider">
                                      Due Date
                                    </th>
                                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wider">
                                      Amount
                                    </th>
                                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-500 uppercase tracking-wider">
                                      Status
                                    </th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                  {deal.payment_schedule.map((payment) => (
                                    <tr key={payment.month}>
                                      <td className="py-2.5 px-3 text-slate-900">
                                        Month {payment.month}
                                      </td>
                                      <td className="py-2.5 px-3 text-slate-600">
                                        {formatDate(payment.due_date)}
                                      </td>
                                      <td className="py-2.5 px-3 font-medium text-slate-900">
                                        {formatCurrency(payment.amount)}
                                      </td>
                                      <td className="py-2.5 px-3">
                                        <span
                                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                                            payment.status === "paid"
                                              ? "bg-green-100 text-green-700"
                                              : payment.status === "upcoming"
                                              ? "bg-amber-100 text-amber-700"
                                              : "bg-gray-100 text-gray-600"
                                          }`}
                                        >
                                          {payment.status === "paid" && (
                                            <CheckCircle2 className="w-3 h-3" />
                                          )}
                                          {payment.status === "upcoming" && (
                                            <Clock className="w-3 h-3" />
                                          )}
                                          {payment.status
                                            .charAt(0)
                                            .toUpperCase() +
                                            payment.status.slice(1)}
                                        </span>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                      {/* Status-Specific Actions */}
                      <div className="px-6 py-4 bg-gray-50 border-t border-gray-200">
                        <div className="flex items-center justify-between">
                          <div className="text-xs text-slate-400">
                            Deal ID: {deal.id}
                            {deal.created_at && (
                              <>
                                {" "}
                                | Created:{" "}
                                {formatDate(deal.created_at)}
                              </>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            {deal.status === "terms_accepted" && (
                              <button className="inline-flex items-center gap-1.5 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition-colors">
                                <CheckCircle2 className="w-4 h-4" />
                                Confirm &amp; Activate
                              </button>
                            )}
                            {deal.status === "tour_scheduled" && (
                              <button className="inline-flex items-center gap-1.5 bg-sky-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-sky-700 transition-colors">
                                <CalendarCheck className="w-4 h-4" />
                                Reschedule Tour
                              </button>
                            )}
                            {(deal.status === "active" ||
                              deal.status === "confirmed") && (
                              <button className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
                                <Eye className="w-4 h-4" />
                                View Agreement
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div className="text-center py-8 mt-4">
          <p className="text-xs text-slate-400">
            Powered by W
            <span className="text-blue-500 font-semibold">Ex</span> Clearing
            House | All-in pricing, no hidden fees
          </p>
        </div>
      </main>
    </div>
  );
}
