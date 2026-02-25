"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { EngagementAgreement } from "@/types/supplier";

export default function BuyerAgreementPage() {
  const params = useParams();
  const router = useRouter();
  const engagementId = params.id as string;

  const [agreement, setAgreement] = useState<EngagementAgreement | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [signing, setSigning] = useState(false);

  const loadAgreement = useCallback(async () => {
    try {
      const data = await api.getAgreement(engagementId);
      setAgreement(data);
    } catch {
      // Demo fallback
      setAgreement({
        id: "demo-agreement-1",
        engagementId,
        version: 1,
        status: "pending",
        termsText:
          "WAREHOUSE EXCHANGE LEASE AGREEMENT\n\nThis Lease Agreement is entered into between the Supplier and the Buyer for warehouse space facilitated through Warehouse Exchange (WEx).\n\nSPACE: 15,000 sq ft\n\nRATES:\n- Buyer Monthly Rate: $22,260.00\n\nTERMS AND CONDITIONS:\n1. Buyer shall pay monthly rent on or before the 1st of each month.\n2. Supplier shall maintain the property in good working condition.\n3. WEx facilitates payments between parties.\n4. Either party may terminate with 30 days written notice.\n5. This agreement is subject to WEx Platform Terms of Service.\n\nBy signing below, both parties agree to the terms of this lease.",
        buyerRateSqft: 1.484,
        monthlyBuyerTotal: 22260,
        sentAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 72 * 60 * 60 * 1000).toISOString(),
      });
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    loadAgreement();
  }, [loadAgreement]);

  const handleSign = async () => {
    if (!agreed) return;
    setSigning(true);
    try {
      await api.signAgreement(engagementId, "buyer");
      router.push(`/buyer/engagements/${engagementId}`);
    } catch {
      alert("Failed to sign agreement");
    } finally {
      setSigning(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading agreement...</div>;
  }

  if (!agreement) {
    return <div className="p-8 text-center text-gray-500">No agreement found.</div>;
  }

  const alreadySigned = !!agreement.buyerSignedAt;
  const supplierSigned = !!agreement.supplierSignedAt;

  return (
    <div className="max-w-3xl mx-auto p-6">
      <button
        onClick={() => router.push(`/buyer/engagements/${engagementId}`)}
        className="text-sm text-blue-600 hover:underline mb-4 inline-block"
      >
        ← Back to engagement
      </button>

      <h1 className="text-2xl font-bold mb-6">Lease Agreement</h1>

      {/* Sign status */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-6">
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span
              className={`w-3 h-3 rounded-full ${
                alreadySigned ? "bg-green-500" : "bg-gray-300"
              }`}
            />
            <span>Buyer: {alreadySigned ? "Signed" : "Pending"}</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`w-3 h-3 rounded-full ${
                supplierSigned ? "bg-green-500" : "bg-gray-300"
              }`}
            />
            <span>Supplier: {supplierSigned ? "Signed" : "Pending"}</span>
          </div>
          <div className="ml-auto text-gray-400">
            Expires:{" "}
            {agreement.expiresAt
              ? new Date(agreement.expiresAt).toLocaleDateString()
              : "—"}
          </div>
        </div>
      </div>

      {/* Agreement terms */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
        <pre className="whitespace-pre-wrap font-sans text-sm text-gray-700 leading-relaxed">
          {agreement.termsText}
        </pre>
      </div>

      {/* Pricing summary */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <h3 className="font-semibold mb-2">Your Rate</h3>
        <div className="flex gap-6 text-sm">
          <div>
            <span className="text-gray-500">Per Sq Ft</span>
            <div className="font-medium">
              ${agreement.buyerRateSqft?.toFixed(4) || "—"}
            </div>
          </div>
          <div>
            <span className="text-gray-500">Monthly Total</span>
            <div className="font-medium text-lg">
              ${agreement.monthlyBuyerTotal?.toLocaleString() || "—"}
            </div>
          </div>
        </div>
      </div>

      {/* Sign section */}
      {!alreadySigned ? (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <label className="flex items-start gap-3 mb-4 cursor-pointer">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-1 w-4 h-4"
            />
            <span className="text-sm text-gray-700">
              I have read and agree to all terms and conditions of this lease
              agreement.
            </span>
          </label>
          <button
            onClick={handleSign}
            disabled={!agreed || signing}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {signing ? "Signing..." : "Sign Agreement"}
          </button>
        </div>
      ) : (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
          <p className="text-green-700 font-medium">
            You have signed this agreement.
          </p>
          {!supplierSigned && (
            <p className="text-sm text-gray-500 mt-1">
              Waiting for supplier to sign.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
