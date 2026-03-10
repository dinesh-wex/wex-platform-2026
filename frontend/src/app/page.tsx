"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Warehouse, Menu, X } from "lucide-react";
import { isAuthenticated } from "@/lib/auth";
import UserMenu from "@/components/auth/UserMenu";
import HeroSection from "@/components/homepage/HeroSection";
import HowItWorks from "@/components/homepage/HowItWorks";
import FeaturedListings from "@/components/homepage/FeaturedListings";
import ValueProps from "@/components/homepage/ValueProps";
import CTASection from "@/components/homepage/CTASection";
import Footer from "@/components/homepage/Footer";

function Navbar() {
  const [authed, setAuthed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 20);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-white/90 backdrop-blur-md border-b border-slate-200 shadow-lg shadow-slate-900/5"
          : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <Warehouse className="h-6 w-6 text-emerald-600" />
          <span className="text-lg font-bold text-slate-900">WEx</span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-8 md:flex">
          <Link
            href="/browse"
            className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
          >
            Browse Spaces
          </Link>
          <Link
            href="/supplier/earncheck?intent=onboard"
            className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
          >
            List Your Space
          </Link>

          {authed ? (
            <UserMenu />
          ) : (
            <Link
              href="/login"
              className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
            >
              Sign In
            </Link>
          )}

          <Link
            href="/buyer"
            className="inline-flex h-9 items-center justify-center rounded-lg bg-emerald-600 px-5 text-sm font-semibold text-white transition-all hover:bg-emerald-500 active:scale-[0.98]"
          >
            Find Space
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="text-slate-600 hover:text-slate-900 md:hidden"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-slate-200 bg-white/95 backdrop-blur-md px-6 py-6 md:hidden">
          <div className="flex flex-col gap-4">
            <Link
              href="/browse"
              onClick={() => setMobileOpen(false)}
              className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
            >
              Browse Spaces
            </Link>
            <Link
              href="/supplier/earncheck?intent=onboard"
              onClick={() => setMobileOpen(false)}
              className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
            >
              List Your Space
            </Link>

            {authed ? (
              <UserMenu />
            ) : (
              <Link
                href="/login"
                onClick={() => setMobileOpen(false)}
                className="text-sm text-slate-600 hover:text-slate-900 transition-colors"
              >
                Sign In
              </Link>
            )}

            <Link
              href="/buyer"
              onClick={() => setMobileOpen(false)}
              className="inline-flex h-10 items-center justify-center rounded-lg bg-emerald-600 px-5 text-sm font-semibold text-white transition-all hover:bg-emerald-500"
            >
              Find Space
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-50">
      <Navbar />
      <HeroSection />
      <HowItWorks />
      <FeaturedListings />
      <ValueProps />
      <CTASection />
      <Footer />
    </main>
  );
}
