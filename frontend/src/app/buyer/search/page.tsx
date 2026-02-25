"use client";

import { useEffect, useRef, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Send,
  CheckCircle2,
  Circle,
  Loader2,
  MapPin,
  Ruler,
  Box,
  Clock,
  DollarSign,
  Sparkles,
  Zap,
  ClipboardList,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface ChatMessage {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  timestamp: Date;
}

interface NeedSummaryField {
  key: string;
  label: string;
  icon: React.ReactNode;
  value: string | null;
  filled: boolean;
}

/* ------------------------------------------------------------------ */
/*  Inner Component                                                    */
/* ------------------------------------------------------------------ */
function BuyerSearchChatContent() {
  const router = useRouter();

  // State — no registration required, chat starts immediately
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [needComplete, setNeedComplete] = useState(false);
  const [findingMatches, setFindingMatches] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);

  const [needSummary, setNeedSummary] = useState<NeedSummaryField[]>([
    { key: "location", label: "Location", icon: <MapPin className="w-4 h-4" />, value: null, filled: false },
    { key: "size_sqft", label: "Size (sqft)", icon: <Ruler className="w-4 h-4" />, value: null, filled: false },
    { key: "use_type", label: "Use Type", icon: <Box className="w-4 h-4" />, value: null, filled: false },
    { key: "timing", label: "Timing", icon: <Clock className="w-4 h-4" />, value: null, filled: false },
    { key: "budget", label: "Budget", icon: <DollarSign className="w-4 h-4" />, value: null, filled: false },
    { key: "requirements", label: "Requirements", icon: <ClipboardList className="w-4 h-4" />, value: null, filled: false },
  ]);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const initRef = useRef(false);
  const demoBuyerSqftRef = useRef<number>(0);

  // Start chat immediately — no registration required
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    addWelcomeMessage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  function addWelcomeMessage() {
    addMessage(
      "agent",
      "Hi there! I'm your WEx Space Agent. I'll help you find the perfect warehouse space.\n\nLet's start with the basics -- what city or area are you looking for warehouse space in?"
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Helpers                                                          */
  /* ---------------------------------------------------------------- */
  function addMessage(role: "user" | "agent" | "system", content: string) {
    setMessages((prev) => [
      ...prev,
      {
        id: `msg-${Date.now()}-${Math.random()}`,
        role,
        content,
        timestamp: new Date(),
      },
    ]);
  }

  function updateSummaryField(key: string, value: string) {
    setNeedSummary((prev) =>
      prev.map((f) => (f.key === key ? { ...f, value, filled: true } : f))
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Send Message                                                     */
  /* ---------------------------------------------------------------- */
  async function handleSend() {
    const text = input.trim();
    if (!text) return;

    addMessage("user", text);
    setInput("");
    setIsTyping(true);
    inputRef.current?.focus();

    // Local-only chat — no backend call needed during intake
    setTimeout(() => {
      setIsTyping(false);
      simulateDemoResponse(text);
    }, 600);
  }

  /* ---------------------------------------------------------------- */
  /*  Demo Simulation                                                  */
  /* ---------------------------------------------------------------- */
  async function simulateDemoResponse(userText: string) {
    const lower = userText.toLowerCase();
    let agentMsg = "";

    // Use currentStep as the PRIMARY driver to prevent keyword collisions
    // (e.g. "$1200" matching a digit regex meant for the size step)
    if (currentStep === 1) {
      const location = userText.length > 3 ? userText : "Dallas, TX";
      updateSummaryField("location", location);

      // After step 1 location capture, try NLP extraction
      try {
        const extraction = await api.extractIntent({ text: userText });
        const fields = extraction?.fields || {};

        // Pre-fill whatever was extracted
        if (fields.size_sqft) {
          demoBuyerSqftRef.current = fields.size_sqft;
          updateSummaryField("size_sqft", `${Number(fields.size_sqft).toLocaleString()} sqft`);
        }
        if (fields.use_type) {
          updateSummaryField("use_type", fields.use_type.replace(/_/g, ' '));
        }
        if (fields.timing) {
          updateSummaryField("timing", fields.timing);
        }
        if (fields.budget_per_sqft) {
          updateSummaryField("budget", `$${fields.budget_per_sqft}/sqft`);
        } else if (fields.budget_monthly) {
          updateSummaryField("budget", `~$${Number(fields.budget_monthly).toLocaleString()}/mo`);
        }
        if (fields.requirements && fields.requirements.length > 0) {
          updateSummaryField("requirements", fields.requirements.join(", "));
        }

        // Count pre-filled fields to decide agent message
        const prefilledCount = Object.keys(fields).filter(k => !['location', 'lat', 'lng', 'city', 'state'].includes(k)).length;
        if (prefilledCount >= 2) {
          // Modify the agent response to acknowledge extraction
          // The agent message should mention the pre-filled fields
        }
      } catch (e) {
        // Extraction failed — continue step-by-step (no impact on flow)
        console.log("Intent extraction failed, continuing step-by-step", e);
      }

      setCurrentStep(2);
      agentMsg =
        "Great choice! How much warehouse space do you need? Give me an approximate square footage, or describe your operation and I'll help estimate.";
    } else if (currentStep === 2) {
      const sqftMatch = lower.match(/(\d[\d,]*)/);
      const sqft = sqftMatch ? sqftMatch[1] : "25,000";
      const sqftNum = parseInt(sqft.replace(/,/g, ""));
      demoBuyerSqftRef.current = sqftNum;
      updateSummaryField("size_sqft", `${sqftNum.toLocaleString()} sqft`);
      setCurrentStep(3);
      agentMsg =
        "What will you be using the space for? For example: e-commerce fulfillment, cold storage, distribution, manufacturing, etc.";
    } else if (currentStep === 3) {
      const useType = userText.length > 3 ? userText : "E-commerce fulfillment";
      updateSummaryField("use_type", useType);
      setCurrentStep(4);
      agentMsg =
        "When do you need the space? For example: immediately, within 30 days, Q2 2025, flexible, etc.";
    } else if (currentStep === 4) {
      const timing = userText.length > 3 ? userText : "Within 30 days";
      updateSummaryField("timing", timing);
      setCurrentStep(5);
      const bSqft = demoBuyerSqftRef.current || 5000;
      const estLow = Math.round(bSqft * 1.0);
      const estHigh = Math.round(bSqft * 1.2);
      agentMsg =
        `What's your monthly budget for the space? For ${bSqft.toLocaleString()} sqft, typical all-in rates run $1.00\u2013$1.20/sqft \u2014 so roughly **$${estLow.toLocaleString()}\u2013$${estHigh.toLocaleString()}/month**. What range works for you?`;
    } else if (currentStep === 5) {
      // Parse budget — could be total monthly ("$1200") or per-sqft ("$1.10/sqft")
      const bSqft = demoBuyerSqftRef.current || 5000;
      let budgetDisplay: string;
      const amountMatch = lower.match(/\$?([\d,]+(?:\.\d{1,2})?)/);
      const rawAmount = amountMatch ? parseFloat(amountMatch[1].replace(/,/g, "")) : 0;
      if (rawAmount > 10) {
        // Looks like a total monthly amount
        const perSqft = rawAmount / bSqft;
        budgetDisplay = `~$${rawAmount.toLocaleString()}/mo ($${perSqft.toFixed(2)}/sqft)`;
      } else if (rawAmount > 0) {
        // Looks like per-sqft rate
        const monthly = Math.round(rawAmount * bSqft);
        budgetDisplay = `$${rawAmount.toFixed(2)}/sqft (~$${monthly.toLocaleString()}/mo)`;
      } else {
        const estMonthly = Math.round(bSqft * 1.1);
        budgetDisplay = `~$${estMonthly.toLocaleString()}/mo ($1.10/sqft)`;
      }
      updateSummaryField("budget", budgetDisplay);
      setCurrentStep(6);
      agentMsg =
        "Almost done! Any specific requirements? For example: dock doors, clear height, climate control, 24/7 access, proximity to highways, etc.";
    } else if (currentStep === 6) {
      const reqs = userText.length > 3 ? userText : "Dock doors, 28ft+ clear height";
      updateSummaryField("requirements", reqs);
      setCurrentStep(7);
      setNeedComplete(true);
      agentMsg =
        "Your space requirements are complete! I've captured everything in the Need Summary on the right.\n\nClick **\"Find Matches\"** to run the WEx Clearing Engine and find your perfect warehouse match. Our AI will analyze available inventory across the network to find the best fit at the best rate.";
    } else {
      agentMsg =
        "Thanks for that! Could you tell me more about your space requirements? I want to make sure we find the perfect match.";
    }

    setTimeout(() => {
      addMessage("agent", agentMsg);
    }, 800);
  }

  /* ---------------------------------------------------------------- */
  /*  Find Matches (trigger clearing)                                  */
  /* ---------------------------------------------------------------- */
  async function handleFindMatches() {
    setFindingMatches(true);

    // Build requirements from the local need summary
    const buyerNeed: Record<string, string | null> = {};
    needSummary.forEach((f) => { buyerNeed[f.key] = f.value; });
    buyerNeed.sqft_raw = String(demoBuyerSqftRef.current || 0);
    localStorage.setItem("wex_buyer_need", JSON.stringify(buyerNeed));

    // Parse structured requirements for the anonymous search API
    const sqft = demoBuyerSqftRef.current || 5000;
    const budgetField = needSummary.find((f) => f.key === "budget")?.value || "";
    const budgetMatch = budgetField.match(/\$([\d.]+)\/sqft/);
    const maxBudget = budgetMatch ? parseFloat(budgetMatch[1]) : undefined;

    const requirements = {
      location: needSummary.find((f) => f.key === "location")?.value || undefined,
      use_type: needSummary.find((f) => f.key === "use_type")?.value || undefined,
      size_sqft: sqft,
      timing: needSummary.find((f) => f.key === "timing")?.value || undefined,
      max_budget_per_sqft: maxBudget,
      duration_months: 6,
      requirements: {
        details: needSummary.find((f) => f.key === "requirements")?.value || "",
      },
    };

    try {
      // Call the anonymous search endpoint — no account needed
      const result = await api.anonymousSearch(requirements);
      const sessionToken = result.session_token;

      // Cache results in localStorage as fallback
      localStorage.setItem("wex_search_session", JSON.stringify(result));

      router.push(`/buyer/options?session=${sessionToken}`);
    } catch {
      // Fallback: navigate with local data only
      router.push(`/buyer/options?session=local`);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Key handler                                                      */
  /* ---------------------------------------------------------------- */
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const filledCount = needSummary.filter((f) => f.filled).length;
  const totalFields = needSummary.length;
  const progressPct = (filledCount / totalFields) * 100;

  /* ================================================================ */
  /*  Render - Main Split-Screen Chat                                  */
  /* ================================================================ */
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 flex-shrink-0">
        <div className="px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-4">
              <Link
                href="/buyer"
                className="text-slate-400 hover:text-slate-600 transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-slate-900">
                  W<span className="text-blue-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">
                  Space Agent
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-400">
                {filledCount}/{totalFields} fields captured
              </span>
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-xs text-slate-500">Connected</span>
            </div>
          </div>
        </div>
      </header>

      {/* Split Panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT: Chat (60%) */}
        <div className="w-3/5 flex flex-col border-r border-gray-200 bg-white">
          {/* Progress Indicator */}
          <div className="px-6 py-2.5 border-b border-gray-100 bg-gray-50/50">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-slate-600">
                Need intake progress
              </span>
              <span className="text-xs text-slate-400">
                {Math.round(progressPct)}%
              </span>
            </div>
            <div className="w-full h-1.5 bg-gray-200 rounded-full">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-br-md"
                      : msg.role === "system"
                      ? "bg-amber-50 text-amber-800 border border-amber-200"
                      : "bg-gray-100 text-slate-800 rounded-bl-md"
                  }`}
                >
                  {msg.role === "agent" && (
                    <div className="flex items-center gap-1.5 mb-1">
                      <Sparkles className="w-3 h-3 text-blue-500" />
                      <span className="text-xs font-medium text-blue-500">
                        WEx Space Agent
                      </span>
                    </div>
                  )}
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">
                    {msg.content.split(/(\*\*.*?\*\*)/).map((part, i) => {
                      if (part.startsWith("**") && part.endsWith("**")) {
                        return <strong key={i}>{part.slice(2, -2)}</strong>;
                      }
                      return part;
                    })}
                  </p>
                  <span
                    className={`text-[10px] mt-1 block ${
                      msg.role === "user" ? "text-blue-200" : "text-slate-400"
                    }`}
                  >
                    {msg.timestamp.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {isTyping && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Sparkles className="w-3 h-3 text-blue-500" />
                    <span className="text-xs font-medium text-blue-500">
                      WEx Space Agent
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div
                      className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                      style={{ animationDelay: "0ms" }}
                    />
                    <div
                      className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                      style={{ animationDelay: "150ms" }}
                    />
                    <div
                      className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-gray-200 px-6 py-4 bg-white">
            <div className="flex items-center gap-3">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  needComplete
                    ? "Need complete! Click Find Matches -->"
                    : "Tell me about your space needs..."
                }
                disabled={needComplete}
                className="flex-1 bg-gray-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || needComplete}
                className="bg-blue-600 text-white p-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT: Need Summary (40%) */}
        <div className="w-2/5 overflow-y-auto bg-gray-50 px-6 py-6">
          {/* Need Summary Card */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6">
            <div className="bg-slate-900 px-5 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-white font-semibold text-sm">
                    Need Summary
                  </h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Your space requirements
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs text-slate-400">
                    {filledCount}/{totalFields} fields
                  </span>
                  <div className="w-20 h-1.5 bg-slate-700 rounded-full mt-1">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all duration-700 ease-out"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="divide-y divide-gray-100">
              {needSummary.map((field) => (
                <div
                  key={field.key}
                  className={`px-5 py-3 flex items-center gap-3 transition-all duration-500 ${
                    field.filled ? "bg-white" : "bg-gray-50/50"
                  }`}
                >
                  <div
                    className={`p-1.5 rounded-md transition-colors duration-500 ${
                      field.filled
                        ? "bg-blue-100 text-blue-600"
                        : "bg-gray-100 text-gray-400"
                    }`}
                  >
                    {field.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-slate-400">{field.label}</p>
                    {field.filled ? (
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {field.value}
                      </p>
                    ) : (
                      <p className="text-sm text-slate-300 italic">
                        Waiting...
                      </p>
                    )}
                  </div>
                  {field.filled && (
                    <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Find Matches Button */}
          {needComplete && (
            <div className="mb-6">
              <button
                onClick={handleFindMatches}
                disabled={findingMatches}
                className="w-full bg-gradient-to-r from-green-600 to-emerald-600 text-white py-4 rounded-xl font-semibold text-lg hover:from-green-700 hover:to-emerald-700 transition-all shadow-lg hover:shadow-xl flex items-center justify-center gap-2 disabled:opacity-70"
              >
                {findingMatches ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Running WEx Clearing Engine...
                  </>
                ) : (
                  <>
                    <Zap className="w-5 h-5" />
                    Find Matches
                  </>
                )}
              </button>
              <p className="text-xs text-slate-400 text-center mt-2">
                Our AI will analyze the entire WEx network to find your perfect
                match
              </p>
            </div>
          )}

          {/* Step Status */}
          {!needComplete && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
              <h4 className="text-sm font-medium text-slate-900 mb-3">
                Intake Progress
              </h4>
              <div className="space-y-2.5">
                {needSummary.map((field, idx) => (
                  <div key={field.key} className="flex items-center gap-2.5">
                    {field.filled ? (
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                    ) : idx === filledCount ? (
                      <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                    ) : (
                      <Circle className="w-4 h-4 text-gray-300" />
                    )}
                    <span
                      className={`text-sm ${
                        field.filled
                          ? "text-green-600 line-through"
                          : idx === filledCount
                          ? "text-blue-600 font-medium"
                          : "text-slate-400"
                      }`}
                    >
                      {field.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Footer */}
          <p className="text-xs text-slate-400 text-center mt-6">
            Powered by W
            <span className="text-blue-500 font-semibold">Ex</span> | All-in
            pricing, no hidden fees
          </p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page Component with Suspense boundary for useSearchParams          */
/* ------------------------------------------------------------------ */
export default function BuyerSearchPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      }
    >
      <BuyerSearchChatContent />
    </Suspense>
  );
}
