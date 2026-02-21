"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Plus,
  ShieldCheck,
  Loader2,
  AlertCircle,
  Mail,
  LogOut,
  Building2,
  Trash2,
} from "lucide-react";
import { motion } from "framer-motion";
import CountUp from "react-countup";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface Warehouse {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  total_sqft: number;
  available_sqft: number;
  min_sqft?: number;
  status: string;
  supplier_rate: number | null;
  image_url: string | null;
  activation_step: number | null;
  truth_core: Record<string, any> | null;
}

interface SupplierProfile {
  id: string;
  name: string;
  company: string;
  email: string;
}

/* ------------------------------------------------------------------ */
/*  Demo supplier accounts                                             */
/* ------------------------------------------------------------------ */
const DEMO_SUPPLIERS: { email: string; label: string }[] = [
  { email: "leasing@charlestonindustrial.com", label: "North Charleston, SC" },
  { email: "ops@gardenalogistics.com", label: "Gardena, CA" },
  { email: "info@commercetwp-warehouse.com", label: "Commerce Township, MI" },
  { email: "leasing@phoenix-industrial.com", label: "Phoenix, AZ - 11th Ave" },
  { email: "ops@glenburnielogistics.com", label: "Glen Burnie, MD" },
  { email: "info@sugarlandwarehouse.com", label: "Sugar Land, TX" },
  { email: "leasing@buckeyeindustrial.com", label: "Phoenix, AZ - Buckeye" },
  { email: "ops@lamiradawarehouse.com", label: "La Mirada, CA" },
  { email: "info@torrancelogistics.com", label: "Torrance, CA" },
  { email: "leasing@mariettawarehouse.com", label: "Marietta, GA" },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function SupplierDashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-50 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
        </div>
      }
    >
      <SupplierDashboard />
    </Suspense>
  );
}

function SupplierDashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const showLogin = searchParams.get("login") === "true";

  const [supplier, setSupplier] = useState<SupplierProfile | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [loading, setLoading] = useState(true); // true initially to check localStorage
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);

  // Login form state
  const [loginEmail, setLoginEmail] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Computed revenue
  const activeWarehouses = warehouses.filter((w) => w.status === "active");
  const warehousesWithRate = activeWarehouses.filter((w) => w.supplier_rate);
  const totalMonthly = warehousesWithRate.reduce(
    (sum, w) => sum + (w.supplier_rate || 0) * (w.available_sqft || 0),
    0
  );
  const avgRate =
    warehousesWithRate.length > 0
      ? warehousesWithRate.reduce((sum, w) => sum + (w.supplier_rate || 0), 0) /
        warehousesWithRate.length
      : 0;
  const totalActiveSqft = activeWarehouses.reduce(
    (sum, w) => sum + (w.available_sqft || 0),
    0
  );
  const totalProjected = totalMonthly * 12;

  // Check for saved supplier on mount
  useEffect(() => {
    const saved = localStorage.getItem("wex_supplier");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setSupplier(parsed);
        loadWarehouses(parsed.email);
      } catch {
        localStorage.removeItem("wex_supplier");
        // No saved supplier — redirect to activation unless ?login=true
        if (!showLogin) {
          router.replace("/supplier/earncheck");
        }
        setLoading(false);
      }
    } else {
      // No saved supplier — redirect to activation unless ?login=true
      if (!showLogin) {
        router.replace("/supplier/earncheck");
      }
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function getLocalWarehouses(): Warehouse[] {
    try {
      const stored = localStorage.getItem("wex_activated_warehouses");
      if (!stored) return [];
      return JSON.parse(stored).map((w: any) => ({
        id: w.id,
        name: w.name || "Activated Warehouse",
        address: w.address || "",
        city: w.city || "",
        state: w.state || "",
        zip_code: w.zip_code || "",
        total_sqft: w.total_sqft || 0,
        available_sqft: w.available_sqft || w.idle_sqft || 0,
        status: w.status || "active",
        supplier_rate: w.supplier_rate || null,
        min_sqft: w.min_sqft || 0,
        image_url: w.image_url || w.primary_image_url || null,
        activation_step: w.activation_step || 6,
        truth_core: w.truth_core || null,
      }));
    } catch {
      return [];
    }
  }

  async function loadWarehouses(ownerEmail: string) {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getWarehouses({ owner_email: ownerEmail });
      const raw = Array.isArray(data) ? data : data.warehouses || [];
      const apiWarehouses: Warehouse[] = raw.map((w: any) => ({
        ...w,
        image_url: w.image_url || w.primary_image_url || null,
        zip_code: w.zip_code || w.zip || "",
        total_sqft: w.total_sqft || w.building_size_sqft || 0,
        name: w.name || w.owner_name || `${w.city || ""} Warehouse`,
        status:
          w.activation_status === "on"
            ? "active"
            : w.activation_status === "off"
            ? "inactive"
            : w.status || "active",
        supplier_rate: w.supplier_rate ?? w.supplier_rate_per_sqft ?? null,
      }));

      const localWarehouses = getLocalWarehouses();
      const apiIds = new Set(apiWarehouses.map((w) => w.id));
      const merged = [
        ...apiWarehouses,
        ...localWarehouses.filter((w) => !apiIds.has(w.id)),
      ];
      setWarehouses(merged);
    } catch {
      setError("Could not connect to backend");
      const localWarehouses = getLocalWarehouses();
      setWarehouses(localWarehouses);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(email: string) {
    const target = email.trim().toLowerCase();
    if (!target) return;

    setLoggingIn(true);
    setLoginError(null);

    try {
      const result = await api.supplierLogin(target);
      const profile: SupplierProfile = {
        id: result.id || result.supplier_id || `supplier-${Date.now()}`,
        name: result.name || target.split("@")[0],
        company:
          result.company || target.split("@")[1]?.split(".")[0] || "Unknown",
        email: target,
      };
      setSupplier(profile);
      localStorage.setItem("wex_supplier", JSON.stringify(profile));
      loadWarehouses(target);
    } catch {
      const domain = target.split("@")[1]?.split(".")[0] || "unknown";
      const profile: SupplierProfile = {
        id: `supplier-${Date.now()}`,
        name: target
          .split("@")[0]
          .replace(/[._-]/g, " ")
          .replace(/\b\w/g, (l) => l.toUpperCase()),
        company: domain
          .replace(/-/g, " ")
          .replace(/\b\w/g, (l) => l.toUpperCase()),
        email: target,
      };
      setSupplier(profile);
      localStorage.setItem("wex_supplier", JSON.stringify(profile));
      loadWarehouses(target);
    } finally {
      setLoggingIn(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem("wex_supplier");
    setSupplier(null);
    setWarehouses([]);
    setError(null);
    setLoginEmail("");
    router.replace("/supplier/earncheck");
  }

  async function handleToggle(warehouse: Warehouse) {
    const newStatus = warehouse.status === "active" ? "inactive" : "active";
    setToggling(warehouse.id);
    try {
      await api.toggleWarehouse(warehouse.id, newStatus);
    } catch {
      // Optimistic update for prototype
    }
    setWarehouses((prev) =>
      prev.map((w) =>
        w.id === warehouse.id ? { ...w, status: newStatus } : w
      )
    );
    setToggling(null);
  }

  function handleRemoveWarehouse(warehouseId: string) {
    if (!confirm("Remove this warehouse from your portfolio?")) return;
    setWarehouses((prev) => prev.filter((w) => w.id !== warehouseId));
    try {
      const stored = JSON.parse(
        localStorage.getItem("wex_activated_warehouses") || "[]"
      );
      const updated = stored.filter((w: any) => w.id !== warehouseId);
      localStorage.setItem(
        "wex_activated_warehouses",
        JSON.stringify(updated)
      );
    } catch {
      // ignore
    }
  }

  /* ================================================================ */
  /*  Render - Login Screen (only if ?login=true and no supplier)      */
  /* ================================================================ */
  if (!supplier && showLogin) {
    return (
      <div className="min-h-screen bg-slate-50">
        <header className="bg-white border-b border-slate-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900">
                  W<span className="text-emerald-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">
                  Supplier Portal
                </span>
              </div>
              <Link
                href="/supplier/earncheck"
                className="text-sm text-emerald-600 hover:text-emerald-700 font-medium"
              >
                New here? Activate a warehouse →
              </Link>
            </div>
          </div>
        </header>

        <main className="max-w-lg mx-auto px-4 py-16">
          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 rounded-full mb-4">
              <Building2 className="w-8 h-8 text-emerald-600" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">
              Welcome Back
            </h2>
            <p className="text-slate-500 max-w-md mx-auto">
              Log in to view your portfolio and track yield
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleLogin(loginEmail);
            }}
            className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4"
          >
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email"
                  required
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="you@yourwarehouse.com"
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg pl-10 pr-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                />
              </div>
            </div>

            {loginError && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                <p className="text-sm text-red-700">{loginError}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loggingIn}
              className="w-full bg-emerald-600 text-white py-3 rounded-lg font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loggingIn ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Logging in...
                </>
              ) : (
                "Log In"
              )}
            </button>
          </form>

          {/* Demo quick-login chips */}
          <div className="mt-8">
            <p className="text-xs text-slate-400 text-center mb-3">
              Demo accounts &mdash; click to log in instantly
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {DEMO_SUPPLIERS.map((s) => (
                <button
                  key={s.email}
                  onClick={() => handleLogin(s.email)}
                  disabled={loggingIn}
                  className="inline-flex items-center gap-1.5 bg-white border border-slate-200 rounded-full px-3 py-1.5 text-xs text-slate-600 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700 transition-colors disabled:opacity-50"
                >
                  <Mail className="w-3 h-3" />
                  <span className="font-medium">
                    {s.email.split("@")[0]}
                  </span>
                  <span className="text-slate-400">({s.label})</span>
                </button>
              ))}
            </div>
          </div>
        </main>
      </div>
    );
  }

  /* ================================================================ */
  /*  Render - Loading / Redirecting                                   */
  /* ================================================================ */
  if (!supplier) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    );
  }

  /* ================================================================ */
  /*  Render - THE PORTFOLIO DASHBOARD                                 */
  /* ================================================================ */
  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900 pb-20">
      {/* ═══════════════════════════════════════════════
          1. THE FINANCIAL HERO HEADER
          One big number. Wealth management feel.
          ═══════════════════════════════════════════════ */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
            {/* The Big Money */}
            <div>
              <div className="flex items-center gap-3 mb-2">
                <p className="text-slate-400 text-xs font-bold uppercase tracking-widest">
                  Total Projected Income
                </p>
                <div className="bg-emerald-50 text-emerald-700 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1 border border-emerald-100">
                  <ShieldCheck size={10} />
                  <span>Protected by WEx Occupancy Guarantee</span>
                </div>
              </div>

              <div className="text-5xl md:text-6xl font-extrabold text-slate-900 tracking-tight flex items-baseline gap-1">
                {loading ? (
                  <span className="text-slate-300">$—</span>
                ) : (
                  <>
                    $
                    <CountUp
                      end={totalProjected}
                      duration={1.5}
                      separator=","
                    />
                  </>
                )}
                <span className="text-xl text-slate-400 font-medium">
                  / yr
                </span>
              </div>

              {/* The Breakdown Stats */}
              <div className="flex flex-wrap items-center gap-4 md:gap-6 mt-4 text-sm font-medium text-slate-500">
                {activeWarehouses.length > 0 && (
                  <>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                      <span className="text-emerald-700">
                        Matching Tenants...
                      </span>
                    </div>
                    <div className="w-px h-4 bg-slate-200 hidden md:block" />
                  </>
                )}
                {avgRate > 0 && (
                  <>
                    <div>
                      Avg Rate:{" "}
                      <span className="text-slate-900">
                        ${avgRate.toFixed(2)}/sqft
                      </span>
                    </div>
                    <div className="w-px h-4 bg-slate-200 hidden md:block" />
                  </>
                )}
                {totalActiveSqft > 0 && (
                  <div>
                    Active Capacity:{" "}
                    <span className="text-slate-900">
                      {totalActiveSqft.toLocaleString()} sqft
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Right side: Actions */}
            <div className="flex items-center gap-3">
              <Link
                href="/supplier/earncheck"
                className="bg-slate-900 hover:bg-black text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2 shadow-lg transition-transform hover:-translate-y-0.5"
              >
                <Plus size={18} />
                Add Asset
              </Link>
              <button
                onClick={handleLogout}
                className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-red-500 transition-colors p-2"
                title="Log out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════
          2. THE ASSET GRID — "Digital Deeds"
          ═══════════════════════════════════════════════ */}
      <main className="max-w-6xl mx-auto px-6 py-12">
        {/* Error Banner */}
        {error && !loading && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3 mb-8">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                Could not connect to backend
              </p>
              <p className="text-xs text-amber-600 mt-1">
                Showing locally activated warehouses.
              </p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-emerald-500 animate-spin mb-4" />
            <p className="text-slate-500">Loading your portfolio...</p>
          </div>
        )}

        {!loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {/* A. The "Growth" Card (Add New Asset) */}
            <Link href="/supplier/earncheck">
              <motion.div
                whileHover={{ scale: 1.02 }}
                className="group relative h-[420px] rounded-[24px] border-2 border-dashed border-slate-300 bg-gradient-to-b from-white to-emerald-50/50 hover:border-emerald-400 transition-all cursor-pointer flex flex-col items-center justify-center text-center p-6"
              >
                <div className="w-16 h-16 rounded-full bg-white border border-slate-200 flex items-center justify-center mb-4 shadow-sm group-hover:shadow-md group-hover:scale-110 transition-all">
                  <Plus
                    size={32}
                    className="text-slate-400 group-hover:text-emerald-500 transition-colors"
                  />
                </div>
                <h3 className="text-lg font-bold text-slate-900">
                  Add Asset to Portfolio
                </h3>
                <p className="text-sm text-slate-500 max-w-[200px] mt-1">
                  Increase your yield by activating more idle space.
                </p>
              </motion.div>
            </Link>

            {/* B. The Active Asset Cards */}
            {warehouses.map((warehouse) => (
              <AssetCard
                key={warehouse.id}
                warehouse={warehouse}
                toggling={toggling === warehouse.id}
                onToggle={() => handleToggle(warehouse)}
                onRemove={() => handleRemoveWarehouse(warehouse.id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

/* ================================================================== */
/*  COMPONENT: THE CINEMATIC ASSET CARD                                */
/*  Mirrors the Phase 3/6 "Split View" — Photo top, Data bottom.      */
/* ================================================================== */
function AssetCard({
  warehouse,
  toggling,
  onToggle,
  onRemove,
}: {
  warehouse: Warehouse;
  toggling: boolean;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const isOn = warehouse.status === "active";
  const revenue = (warehouse.supplier_rate || 0) * (warehouse.available_sqft || 0) * 12;
  const addressParts = warehouse.address.split(",");
  const streetLine = addressParts[0] || warehouse.name;
  const cityLine = addressParts.slice(1).join(",").trim() ||
    [warehouse.city, warehouse.state, warehouse.zip_code].filter(Boolean).join(", ");

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="group bg-white h-[420px] rounded-[24px] overflow-hidden shadow-sm border border-slate-200 hover:shadow-xl transition-shadow flex flex-col"
    >
      {/* TOP 45%: The Cinematic View */}
      <div className="relative h-[45%] bg-slate-800">
        {warehouse.image_url ? (
          <div
            className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-105"
            style={{ backgroundImage: `url(${warehouse.image_url})` }}
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-slate-600 via-slate-700 to-emerald-900 flex items-center justify-center">
            <Building2 className="w-12 h-12 text-slate-500" />
          </div>
        )}
        <div className="absolute inset-0 bg-black/10" />

        {/* Live / Paused Badge */}
        <div className="absolute top-4 right-4">
          <div
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest text-white backdrop-blur-md shadow-lg flex items-center gap-1.5 ${
              isOn ? "bg-emerald-500/90" : "bg-slate-500/90"
            }`}
          >
            <div
              className={`w-1.5 h-1.5 rounded-full bg-white ${
                isOn ? "animate-pulse" : ""
              }`}
            />
            {isOn ? "Live" : "Paused"}
          </div>
        </div>

        {/* Remove button (hover) */}
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRemove();
          }}
          className="absolute top-4 left-4 p-1.5 rounded-full bg-black/30 backdrop-blur-md hover:bg-red-500/80 text-white/70 hover:text-white transition-all opacity-0 group-hover:opacity-100"
          title="Remove from portfolio"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* BOTTOM 55%: The Deed Data */}
      <div className="flex-1 p-6 flex flex-col justify-between">
        <div>
          <h3 className="text-xl font-bold text-slate-900 leading-tight mb-1">
            {streetLine}
          </h3>
          <p className="text-sm text-slate-500 mb-5">{cityLine}</p>

          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Revenue
            </span>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
              Rate Locked
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold text-emerald-600">
              ${revenue > 0 ? revenue.toLocaleString() : "—"}
              {revenue > 0 && (
                <span className="text-sm text-slate-400 font-normal">
                  /yr
                </span>
              )}
            </span>
            {warehouse.supplier_rate != null && warehouse.supplier_rate > 0 && (
              <div className="flex items-center gap-1 text-slate-600 font-medium bg-slate-100 px-2.5 py-1 rounded-md text-sm">
                <ShieldCheck size={14} /> $
                {warehouse.supplier_rate.toFixed(2)}/ft
              </div>
            )}
          </div>
        </div>

        {/* Footer: Status + Master Toggle */}
        <div className="pt-5 border-t border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-medium">
            {isOn ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <span className="text-emerald-700">Matching Tenants...</span>
              </>
            ) : (
              <span className="text-slate-400">Not accepting matches</span>
            )}
          </div>

          {/* THE MASTER TOGGLE */}
          <button
            onClick={onToggle}
            disabled={toggling}
            className={`w-14 h-8 rounded-full p-1 transition-colors duration-300 ${
              isOn ? "bg-emerald-500" : "bg-slate-200"
            } ${toggling ? "opacity-50" : ""}`}
          >
            <div
              className={`w-6 h-6 bg-white rounded-full shadow-md transform transition-transform duration-300 ${
                isOn ? "translate-x-6" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>
    </motion.div>
  );
}
