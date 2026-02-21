"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, Check } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Agreement text content                                              */
/* ------------------------------------------------------------------ */

const AGREEMENT_TEXT: Record<string, { title: string; body: string }> = {
  occupancy_guarantee: {
    title: "WEx Occupancy Guarantee",
    body: `WEX OCCUPANCY GUARANTEE AGREEMENT

By accepting this agreement, you acknowledge and agree to the following terms:

1. ANTI-CIRCUMVENTION
You agree not to contact the property owner/operator directly to negotiate terms outside the Warehouse Exchange platform for a period of 12 months from the date of this agreement. All communications and negotiations shall be conducted through the WEx platform.

2. PRICING TRANSPARENCY
The rates presented through WEx are market-validated and include WEx's service fee. You agree to transact at the presented rate without attempting to negotiate directly with the supplier outside the platform.

3. GOOD FAITH TOURING
You agree to attend scheduled tours in good faith. Repeated no-shows or cancellations without 24-hour notice may result in reduced priority for future matches.

4. DISPUTE RESOLUTION
Any disputes arising from transactions facilitated through WEx shall first be submitted to WEx's internal resolution process before pursuing external remedies.

5. CONFIDENTIALITY
Property addresses and supplier information revealed through this agreement are confidential and shall not be shared with third parties.

This is a binding agreement. Property address will be revealed upon acceptance.`,
  },
  network_agreement: {
    title: "WEx Supplier Network Agreement",
    body: `WEX SUPPLIER NETWORK AGREEMENT

By accepting this agreement, you acknowledge and agree to the following terms:

1. PLATFORM EXCLUSIVITY FOR MATCHED DEALS
For any buyer introduced through the WEx platform, you agree to conduct the transaction exclusively through WEx for a period of 12 months from introduction.

2. ANTI-CIRCUMVENTION
You agree not to solicit or accept direct engagement from WEx-introduced buyers outside the platform.

3. PRICING COMMITMENT
Rates agreed upon through the WEx platform are binding for the stated term. Rate changes require 30 days notice through the platform.

4. PROPERTY ACCURACY
You certify that all property information provided is accurate to the best of your knowledge. Material misrepresentation may result in removal from the network.

5. PAYOUT TERMS
Monthly rental payments will be processed through WEx and deposited to your registered bank account within 5 business days of receipt.

6. AVAILABILITY UPDATES
You agree to keep your property availability status current on the platform. Failure to update availability within 48 hours of a change may affect your network standing.`,
  },
};

/* ------------------------------------------------------------------ */
/*  Props                                                               */
/* ------------------------------------------------------------------ */

export interface AgreementCheckboxProps {
  type: "occupancy_guarantee" | "network_agreement";
  onAccept: (accepted: boolean) => void;
  accepted: boolean;
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */

export default function AgreementCheckbox({
  type,
  onAccept,
  accepted,
}: AgreementCheckboxProps) {
  const [expanded, setExpanded] = useState(false);
  const agreement = AGREEMENT_TEXT[type];

  if (!agreement) return null;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/50 overflow-hidden">
      {/* Header row: title + expand toggle */}
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <FileText className="w-4 h-4 text-blue-400 shrink-0" />
          <span className="text-sm font-medium text-white">
            {agreement.title}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {expanded ? "Hide" : "View"} Terms
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          )}
        </div>
      </button>

      {/* Expandable terms section */}
      {expanded && (
        <div className="border-t border-slate-700">
          <div className="px-4 py-3 max-h-64 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-800">
            <pre className="text-xs text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">
              {agreement.body}
            </pre>
          </div>
        </div>
      )}

      {/* Checkbox row */}
      <div className="border-t border-slate-700 px-4 py-3">
        <label className="flex items-start gap-3 cursor-pointer group">
          <div className="relative mt-0.5 shrink-0">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => onAccept(e.target.checked)}
              className="sr-only peer"
            />
            <div
              className={`w-5 h-5 rounded border-2 transition-all flex items-center justify-center ${
                accepted
                  ? "bg-blue-600 border-blue-600"
                  : "border-slate-500 group-hover:border-slate-400"
              }`}
            >
              {accepted && <Check className="w-3.5 h-3.5 text-white" />}
            </div>
          </div>
          <span className="text-sm text-slate-300 leading-snug">
            I have read and agree to the{" "}
            <span className="text-white font-medium">{agreement.title}</span>
          </span>
        </label>
      </div>
    </div>
  );
}
