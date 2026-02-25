"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Handshake,
  DollarSign,
  Settings,
  LogOut,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { useSupplier } from "@/components/supplier/SupplierAuthProvider";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SupplierNavProps {
  collapsed?: boolean;
  onToggle?: () => void;
}

// ---------------------------------------------------------------------------
// Nav items
// ---------------------------------------------------------------------------

const NAV_ITEMS = [
  { label: "Portfolio", href: "/supplier", icon: LayoutDashboard },
  { label: "Engagements", href: "/supplier/engagements", icon: Handshake },
  { label: "Payments", href: "/supplier/payments", icon: DollarSign },
  { label: "Account", href: "/supplier/account", icon: Settings },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SupplierNav({ collapsed = false, onToggle }: SupplierNavProps) {
  const pathname = usePathname();
  const { supplier, logout } = useSupplier();

  function isActive(href: string) {
    if (href === "/supplier") return pathname === "/supplier" || pathname.startsWith("/supplier/properties");
    return pathname.startsWith(href);
  }

  return (
    <nav
      className={`h-full bg-white border-r border-slate-200 flex flex-col transition-all duration-200 ${
        collapsed ? "w-[72px]" : "w-64"
      }`}
    >
      {/* ─── Branding ─── */}
      <div className="flex items-center justify-between px-4 h-16 border-b border-slate-100 flex-shrink-0">
        <Link href="/supplier" className="flex items-center gap-2 min-w-0">
          <span className="text-xl font-bold text-slate-900 flex-shrink-0">
            W<span className="text-emerald-500">Ex</span>
          </span>
          {!collapsed && (
            <span className="text-xs font-medium text-slate-400 truncate">
              Supplier Portal
            </span>
          )}
        </Link>

        {onToggle && (
          <button
            onClick={onToggle}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors flex-shrink-0"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronsRight className="w-4 h-4" />
            ) : (
              <ChevronsLeft className="w-4 h-4" />
            )}
          </button>
        )}
      </div>

      {/* ─── Navigation Items ─── */}
      <div className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-emerald-50 text-emerald-700 border-l-2 border-emerald-500"
                  : "text-slate-600 hover:bg-slate-100"
              } ${collapsed ? "justify-center px-2" : ""}`}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={`w-5 h-5 flex-shrink-0 ${active ? "text-emerald-600" : "text-slate-400"}`} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </div>

      {/* ─── Footer: Supplier info + Logout ─── */}
      <div className="border-t border-slate-100 p-3 flex-shrink-0">
        {supplier && !collapsed && (
          <div className="px-3 py-2 mb-2">
            <p className="text-sm font-medium text-slate-900 truncate">
              {supplier.name}
            </p>
            <p className="text-xs text-slate-400 truncate">
              {supplier.company}
            </p>
          </div>
        )}

        {supplier && collapsed && (
          <div className="flex justify-center mb-2">
            <div
              className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold"
              title={`${supplier.name} — ${supplier.company}`}
            >
              {supplier.name.charAt(0).toUpperCase()}
            </div>
          </div>
        )}

        <button
          onClick={logout}
          className={`flex items-center gap-3 w-full rounded-lg px-3 py-2.5 text-sm font-medium text-slate-500 hover:bg-red-50 hover:text-red-600 transition-colors ${
            collapsed ? "justify-center px-2" : ""
          }`}
          title={collapsed ? "Log out" : undefined}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Log out</span>}
        </button>
      </div>
    </nav>
  );
}
