"use client";

import Link from "next/link";
import { Warehouse } from "lucide-react";

const navLinks = [
  { label: "Home", href: "/" },
  { label: "Browse Spaces", href: "/browse" },
  { label: "List Your Space", href: "/supplier/earncheck?intent=onboard" },
  { label: "About", href: "/about" },
  { label: "Contact", href: "/contact" },
];

const legalLinks = [
  { label: "Terms of Service", href: "/terms" },
  { label: "Privacy Policy", href: "/privacy" },
];

export default function Footer() {
  return (
    <footer className="border-t border-gray-800 bg-gray-950 py-16">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-3">
          {/* Company */}
          <div>
            <Link href="/" className="inline-flex items-center gap-2">
              <Warehouse className="h-6 w-6 text-blue-400" />
              <span className="text-lg font-bold text-white">Warehouse Exchange</span>
            </Link>
            <p className="mt-4 max-w-xs text-sm text-gray-400">
              The marketplace connecting businesses with flexible warehouse space.
              Find or list space in hours, not months.
            </p>
          </div>

          {/* Navigation */}
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              Navigation
            </h4>
            <ul className="mt-4 space-y-3">
              {navLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-gray-400 hover:text-white transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wider text-gray-400">
              Legal
            </h4>
            <ul className="mt-4 space-y-3">
              {legalLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-gray-400 hover:text-white transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 border-t border-gray-800 pt-8 text-center text-sm text-gray-500">
          &copy; {new Date().getFullYear()} Warehouse Exchange. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
