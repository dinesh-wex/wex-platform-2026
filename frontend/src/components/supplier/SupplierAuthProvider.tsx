"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { getToken, setToken, removeToken } from "@/lib/auth";
import { login as apiLogin, getMe } from "@/lib/api";
import { api } from "@/lib/api";
import type { SupplierProfile, Warehouse } from "@/types/supplier";

// ---------------------------------------------------------------------------
// Context value
// ---------------------------------------------------------------------------

interface SupplierAuthContextValue {
  supplier: SupplierProfile | null;
  warehouses: Warehouse[];
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  demoLogin: (email: string) => Promise<void>;
  logout: () => void;
  refreshWarehouses: () => Promise<void>;
}

const SupplierAuthContext = createContext<SupplierAuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function SupplierAuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [supplier, setSupplier] = useState<SupplierProfile | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [loading, setLoading] = useState(true);

  // ---- Fetch warehouses for a given supplier email (prefer company_id) ----
  const fetchWarehouses = useCallback(async (email: string, companyId?: string) => {
    try {
      const params: Record<string, string> = {};
      if (companyId) {
        params.company_id = companyId;
      } else {
        console.warn(
          "[WEx] Using deprecated owner_email fallback for warehouse fetching. " +
          "Caller should pass company_id. Remove this fallback next sprint."
        );
        params.owner_email = email;
      }
      const data = await api.getWarehouses(params);
      setWarehouses(Array.isArray(data) ? data : data.warehouses ?? []);
    } catch {
      setWarehouses([]);
    }
  }, []);

  // ---- Check for existing session on mount ----
  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const token = getToken();
      if (!token) {
        // No JWT — check for localStorage supplier (set during earncheck activation)
        try {
          const stored = localStorage.getItem("wex_supplier");
          if (stored) {
            const profile = JSON.parse(stored) as SupplierProfile;
            if (!cancelled) {
              setSupplier(profile);
              await fetchWarehouses(profile.email, profile.company_id);
            }
          }
        } catch {
          // Ignore parse errors
        }
        if (!cancelled) setLoading(false);
        return;
      }

      try {
        const profile: SupplierProfile = await getMe();
        if (cancelled) return;
        setSupplier(profile);
        await fetchWarehouses(profile.email, profile.company_id);
      } catch {
        // Token invalid / expired -- silently clear
        removeToken();
        setSupplier(null);
        setWarehouses([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [fetchWarehouses]);

  // ---- Regular email + password login ----
  const login = useCallback(
    async (email: string, password: string) => {
      const resp = await apiLogin(email, password);
      const jwt = resp.access_token ?? resp.token;
      setToken(jwt);

      const profile: SupplierProfile = await getMe();
      setSupplier(profile);
      await fetchWarehouses(profile.email, profile.company_id);
    },
    [fetchWarehouses],
  );

  // ---- Demo account login (no password) ----
  const demoLogin = useCallback(
    async (email: string) => {
      const { token, supplier: profile } = await api.supplierLogin(email);
      setToken(token);
      setSupplier(profile);
      await fetchWarehouses(profile.email, profile.company_id);
    },
    [fetchWarehouses],
  );

  // ---- Logout ----
  const logout = useCallback(() => {
    removeToken();
    localStorage.removeItem("wex_supplier");
    setSupplier(null);
    setWarehouses([]);
    router.push("/supplier");
  }, [router]);

  // ---- Refresh warehouses (callable from consumers) ----
  const refreshWarehouses = useCallback(async () => {
    if (!supplier) return;
    await fetchWarehouses(supplier.email, supplier.company_id);
  }, [supplier, fetchWarehouses]);

  // ---- Stable context value ----
  const value = useMemo<SupplierAuthContextValue>(
    () => ({
      supplier,
      warehouses,
      loading,
      login,
      demoLogin,
      logout,
      refreshWarehouses,
    }),
    [supplier, warehouses, loading, login, demoLogin, logout, refreshWarehouses],
  );

  return (
    <SupplierAuthContext.Provider value={value}>
      {children}
    </SupplierAuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSupplier(): SupplierAuthContextValue {
  const ctx = useContext(SupplierAuthContext);
  if (!ctx) {
    throw new Error(
      "useSupplier() must be used within a <SupplierAuthProvider>",
    );
  }
  return ctx;
}
