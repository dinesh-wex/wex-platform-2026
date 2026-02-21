"use client";

import Link from "next/link";
import SignupForm from "@/components/auth/SignupForm";

export default function SignupPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950 px-4 py-12">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="mb-8 text-center">
          <Link href="/" className="inline-block">
            <div className="flex items-center justify-center gap-2 mb-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600">
                <span className="text-lg font-bold text-white">W</span>
              </div>
              <span className="text-2xl font-bold text-white">WEx Platform</span>
            </div>
          </Link>
          <p className="text-sm text-gray-400">Create your account</p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6 shadow-xl backdrop-blur-sm">
          <SignupForm />
        </div>
      </div>
    </div>
  );
}
