"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { OnboardingStatus } from "@/types/supplier";

interface Step {
  key: "insurance" | "companyDocs" | "payment";
  label: string;
  description: string;
  done: boolean;
}

export default function BuyerOnboardingPage() {
  const params = useParams();
  const router = useRouter();
  const engagementId = params.id as string;

  const [status, setStatus] = useState<OnboardingStatus>({
    insuranceUploaded: false,
    companyDocsUploaded: false,
    paymentMethodAdded: false,
  });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const data = await api.getOnboardingStatus(engagementId);
      setStatus(data);
    } catch {
      // Demo fallback — all incomplete
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const steps: Step[] = [
    {
      key: "insurance",
      label: "Insurance Documentation",
      description:
        "Upload proof of general liability insurance covering the leased space.",
      done: status.insuranceUploaded,
    },
    {
      key: "companyDocs",
      label: "Company Documents",
      description:
        "Upload business license, certificate of incorporation, or equivalent.",
      done: status.companyDocsUploaded,
    },
    {
      key: "payment",
      label: "Payment Method",
      description:
        "Add a payment method (ACH or wire transfer) for monthly lease payments.",
      done: status.paymentMethodAdded,
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const allComplete = completedCount === steps.length;
  const progress = Math.round((completedCount / steps.length) * 100);

  const handleSubmit = async (stepKey: string) => {
    setSubmitting(stepKey);
    try {
      if (stepKey === "insurance") {
        await api.uploadInsurance(engagementId);
      } else if (stepKey === "companyDocs") {
        await api.uploadCompanyDocs(engagementId);
      } else if (stepKey === "payment") {
        await api.submitPaymentMethod(engagementId);
      }
      await loadStatus();
    } catch {
      alert(`Failed to submit ${stepKey}`);
    } finally {
      setSubmitting(null);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <button
        onClick={() => router.push(`/buyer/engagements/${engagementId}`)}
        className="text-sm text-blue-600 hover:underline mb-4 inline-block"
      >
        ← Back to engagement
      </button>

      <h1 className="text-2xl font-bold mb-2">Onboarding</h1>
      <p className="text-gray-500 mb-6">
        Complete these steps to activate your lease.
      </p>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-500">Progress</span>
          <span className="font-medium">{progress}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-purple-600 h-2 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-4">
        {steps.map((step, i) => (
          <div
            key={step.key}
            className={`border rounded-lg p-5 ${
              step.done
                ? "bg-green-50 border-green-200"
                : "bg-white border-gray-200"
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0 ${
                  step.done
                    ? "bg-green-500 text-white"
                    : "bg-gray-200 text-gray-600"
                }`}
              >
                {step.done ? "✓" : i + 1}
              </span>
              <div className="flex-1">
                <h3 className="font-semibold">{step.label}</h3>
                <p className="text-sm text-gray-500 mt-1">{step.description}</p>
                {!step.done && (
                  <button
                    onClick={() => handleSubmit(step.key)}
                    disabled={submitting === step.key}
                    className="mt-3 px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50"
                  >
                    {submitting === step.key
                      ? "Submitting..."
                      : step.key === "payment"
                        ? "Add Payment Method"
                        : "Upload"}
                  </button>
                )}
                {step.done && (
                  <span className="text-sm text-green-600 mt-2 inline-block">
                    Completed
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* All complete */}
      {allComplete && (
        <div className="mt-6 bg-green-50 border border-green-200 rounded-lg p-5 text-center">
          <h3 className="font-semibold text-green-700 text-lg">
            Onboarding Complete!
          </h3>
          <p className="text-sm text-gray-600 mt-1">
            Your lease is now being activated.
          </p>
          <button
            onClick={() => router.push(`/buyer/engagements/${engagementId}`)}
            className="mt-3 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            View Engagement
          </button>
        </div>
      )}
    </div>
  );
}
