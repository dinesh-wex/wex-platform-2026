"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, LogOut, User } from "lucide-react";
import { getMe, logout } from "@/lib/api";

interface UserData {
  id: string;
  name: string;
  email: string;
  role: string;
}

export default function UserMenu() {
  const router = useRouter();
  const [user, setUser] = useState<UserData | null>(null);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        /* token expired - redirect handled by fetchAPI */
      });
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  if (!user) return null;

  const roleLabel = user.role.charAt(0).toUpperCase() + user.role.slice(1);

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:border-slate-300 hover:bg-slate-50 transition-colors"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-xs font-semibold text-white">
          {user.name.charAt(0).toUpperCase()}
        </div>
        <div className="text-left hidden sm:block">
          <div className="font-medium text-slate-900 leading-tight">{user.name}</div>
          <div className="text-xs text-slate-500">{roleLabel}</div>
        </div>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-48 rounded-lg border border-slate-200 bg-white py-1 shadow-xl z-50">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              router.push("/profile");
            }}
            className="flex w-full items-center gap-2 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
          >
            <User className="h-4 w-4" />
            Profile
          </button>
          <hr className="border-slate-200 my-1" />
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-4 py-2 text-sm text-red-500 hover:bg-red-50 hover:text-red-600 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
