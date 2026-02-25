"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import {
  SupplierAuthProvider,
  useSupplier,
} from "@/components/supplier/SupplierAuthProvider";
import SupplierNav from "@/components/supplier/SupplierNav";

// ---------------------------------------------------------------------------
// Root layout — wraps everything in auth provider
// ---------------------------------------------------------------------------

export default function SupplierLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SupplierAuthProvider>
      <SupplierShell>{children}</SupplierShell>
    </SupplierAuthProvider>
  );
}

// ---------------------------------------------------------------------------
// Inner shell — needs useSupplier(), so must be inside the provider
// ---------------------------------------------------------------------------

function SupplierShell({ children }: { children: React.ReactNode }) {
  const { supplier, loading } = useSupplier();
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  // Close mobile drawer on route change
  // (pathname changes trigger a re-render; if drawer is open, close it)
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (mobileOpen) setMobileOpen(false);
  }

  // ── Public routes that don't require authentication ──
  const isPublicRoute =
    pathname === "/supplier" ||
    pathname.startsWith("/supplier/earncheck") ||
    pathname.startsWith("/supplier/onboard");

  // ── Not authenticated: redirect sub-pages to /supplier?login=true ──
  // The main /supplier page.tsx handles showing the login UI itself.
  // EarnCheck and onboard flows are public (new supplier activation).
  useEffect(() => {
    if (!loading && !supplier && !isPublicRoute) {
      router.push("/supplier?login=true");
    }
  }, [loading, supplier, pathname, router, isPublicRoute]);

  // ── Public routes: always render without dashboard shell (even if authenticated) ──
  const isFullscreenRoute =
    pathname.startsWith("/supplier/earncheck") ||
    pathname.startsWith("/supplier/onboard");

  if (isFullscreenRoute) {
    return (
      <div className="min-h-screen bg-slate-50">
        {children}
      </div>
    );
  }

  if (!loading && !supplier) {
    // Render children for the main /supplier route (has its own login UI)
    if (isPublicRoute) {
      return (
        <div className="min-h-screen bg-slate-50">
          {children}
        </div>
      );
    }
    // For authenticated sub-pages, show nothing while redirecting
    return null;
  }

  // ── Authenticated (or still loading): full dashboard shell ──
  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* ════════════════════════════════════════════════
          Desktop sidebar — always visible at lg+
          ════════════════════════════════════════════════ */}
      <aside className="hidden lg:flex lg:fixed lg:inset-y-0 lg:left-0 lg:z-40 lg:w-64">
        <SupplierNav />
      </aside>

      {/* ════════════════════════════════════════════════
          Mobile top bar — visible below lg
          ════════════════════════════════════════════════ */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4">
        <span className="text-xl font-bold text-slate-900">
          W<span className="text-emerald-500">Ex</span>
        </span>

        <button
          onClick={() => setMobileOpen((prev) => !prev)}
          className="p-3 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* ════════════════════════════════════════════════
          Mobile drawer overlay + sidebar
          ════════════════════════════════════════════════ */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="lg:hidden fixed inset-0 z-50 bg-black/40"
              onClick={() => setMobileOpen(false)}
            />

            {/* Drawer */}
            <motion.aside
              key="drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="lg:hidden fixed inset-y-0 left-0 z-50 w-64 shadow-xl"
            >
              <SupplierNav
                collapsed={false}
                onToggle={() => setMobileOpen(false)}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ════════════════════════════════════════════════
          Main content area
          ════════════════════════════════════════════════ */}
      <main className="flex-1 lg:ml-64 pt-16 lg:pt-0 min-h-screen">
        {children}
      </main>
    </div>
  );
}
