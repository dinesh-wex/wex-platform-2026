"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  Users,
  Mail,
  TrendingUp,
  DollarSign,
  MapPin,
  Send,
  Loader2,
  Sparkles,
  RefreshCw,
  Search,
  ChevronDown,
  ChevronUp,
  Building2,
  Lock,
  Download,
  Warehouse,
  CalendarDays,
  ToggleLeft,
  ToggleRight,
  Globe,
  Monitor,
  Clock,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface KPIs {
  total_page_views: number;
  total_sessions: number;
  emails_submitted: number;
  conversion_rate: number;
  total_property_value: number;
  total_sqft: number;
  total_available_sqft: number;
  total_monthly_value: number;
  total_annual_value: number;
  properties_searched: number;
}

interface PricingSplit {
  automated: number;
  manual: number;
}

interface ReferrerRow {
  referrer: string;
  count: number;
}

interface FunnelPhase {
  phase: string;
  sessions: number;
}

interface GeoRow {
  city?: string;
  state?: string;
  count: number;
}

interface AnalyticsData {
  kpis: KPIs;
  funnel: FunnelPhase[];
  pricing_split: PricingSplit;
  top_cities: GeoRow[];
  top_states: GeoRow[];
  all_cities: GeoRow[];
  all_states: GeoRow[];
  top_referrers: ReferrerRow[];
}

interface ChatMessage {
  role: "user" | "ai";
  text: string;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const PHASE_ICONS = ["1", "2", "3", "4", "5"];

const TIME_RANGES = [
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "All time", value: 0 },
];

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

/* ------------------------------------------------------------------ */
/*  Components                                                         */
/* ------------------------------------------------------------------ */

function KPICard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center">
          <Icon className="w-4 h-4 text-emerald-600" />
        </div>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function FunnelSquares({ phases }: { phases: FunnelPhase[] }) {
  return (
    <div className="grid grid-cols-5 gap-3">
      {phases.map((phase, i) => {
        const dropoff =
          i > 0 && phases[i - 1].sessions > 0
            ? Math.round(
                ((phases[i - 1].sessions - phase.sessions) /
                  phases[i - 1].sessions) *
                  100
              )
            : null;
        return (
          <div
            key={phase.phase}
            className="bg-slate-50 rounded-xl p-4 text-center border border-slate-100 relative"
          >
            <span className="w-6 h-6 rounded-full bg-emerald-600 text-white text-[10px] font-bold flex items-center justify-center mx-auto mb-2">
              {PHASE_ICONS[i]}
            </span>
            <p className="text-xs font-medium text-slate-500 mb-1">{phase.phase}</p>
            <p className="text-xl font-bold text-slate-900">{phase.sessions}</p>
            {dropoff !== null && dropoff > 0 && (
              <p className="text-[10px] text-red-400 font-medium mt-0.5">−{dropoff}%</p>
            )}
            {i < phases.length - 1 && (
              <span className="absolute right-[-10px] top-1/2 -translate-y-1/2 text-slate-300 text-xs hidden lg:block">→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function downloadCSV(rows: GeoRow[], labelKey: "city" | "state", filename: string) {
  const header = `${labelKey === "city" ? "City" : "State"},Count\n`;
  const body = rows.map((r) => `"${(r[labelKey] || "Unknown").replace(/"/g, '""')}",${r.count}`).join("\n");
  const blob = new Blob([header + body], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function GeoList({
  title,
  icon: Icon,
  topItems,
  allItems,
  labelKey,
}: {
  title: string;
  icon: React.ElementType;
  topItems: GeoRow[];
  allItems: GeoRow[];
  labelKey: "city" | "state";
}) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState("");

  const items = expanded ? allItems : topItems;
  const filtered = filter
    ? items.filter((r) =>
        (r[labelKey] || "").toLowerCase().includes(filter.toLowerCase())
      )
    : items;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          <Icon className="w-4 h-4 text-emerald-500" />
          {title}
        </h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {allItems.length} total
          </span>
          {allItems.length > 0 && (
            <button
              onClick={() => downloadCSV(allItems, labelKey, `${title.toLowerCase().replace(/\s+/g, "_")}.csv`)}
              className="text-slate-400 hover:text-emerald-600 transition-colors"
              title={`Download ${title} as CSV`}
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="relative mb-3">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`Filter ${labelKey === "city" ? "cities" : "states"}...`}
            className="w-full pl-8 pr-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/30 text-slate-700 placeholder:text-slate-400"
          />
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-slate-400 py-2">No data yet</p>
      ) : (
        <div className="space-y-0">
          {filtered.map((row, i) => {
            const label = row[labelKey] || "Unknown";
            const maxCount = Math.max(...(expanded ? allItems : topItems).map((r) => r.count), 1);
            const barPct = (row.count / maxCount) * 100;
            return (
              <div
                key={i}
                className="flex items-center gap-3 py-1.5"
              >
                <span className="text-sm text-slate-600 w-40 truncate shrink-0">
                  {label}
                </span>
                <div className="flex-1 h-4 bg-slate-50 rounded overflow-hidden">
                  <div
                    className="h-full bg-emerald-100 rounded"
                    style={{ width: `${Math.max(barPct, 4)}%` }}
                  />
                </div>
                <span className="text-sm font-semibold text-slate-900 w-8 text-right shrink-0">
                  {row.count}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {allItems.length > 10 && (
        <button
          onClick={() => { setExpanded(!expanded); setFilter(""); }}
          className="mt-3 w-full py-1.5 text-xs text-slate-500 hover:text-emerald-600 flex items-center justify-center gap-1 border-t border-slate-100 transition-colors"
        >
          {expanded ? (
            <>Show top 10 <ChevronUp className="w-3.5 h-3.5" /></>
          ) : (
            <>Show all {allItems.length} <ChevronDown className="w-3.5 h-3.5" /></>
          )}
        </button>
      )}
    </div>
  );
}

function AIChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "ai",
      text: "Hi! Ask me anything — visitors today, which cities, conversion rates, lead details, and more.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const send = async (text?: string) => {
    const q = (text || input).trim();
    if (!q || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.earncheckChat(q);
      setMessages((prev) => [...prev, { role: "ai", text: res.answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 flex flex-col h-[400px]">
      <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-emerald-500" />
        <span className="text-sm font-semibold text-slate-900">Ask AI</span>
        <span className="text-xs text-slate-400 ml-auto">Gemini</span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-emerald-600 text-white rounded-br-sm"
                  : "bg-slate-50 text-slate-700 rounded-bl-sm"
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.text}</div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-50 text-slate-500 px-3.5 py-2.5 rounded-xl rounded-bl-sm text-sm flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Thinking...
            </div>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-slate-100">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask about your analytics..."
            className="flex-1 px-3.5 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400 text-slate-700 placeholder:text-slate-400"
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            className="px-3 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {[
            "How many visitors today?",
            "Which cities?",
            "Conversion rate?",
            "Show recent leads",
          ].map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="text-xs px-2.5 py-1 rounded-full border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-700 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Visitors Panel                                                     */
/* ------------------------------------------------------------------ */

interface VisitorRow {
  id: string;
  path: string;
  referrer: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  user_agent: string | null;
  ip: string | null;
  city: string | null;
  session_id: string | null;
  created_at: string | null;
}

function parseUA(ua: string | null): { browser: string; os: string } {
  if (!ua) return { browser: "Unknown", os: "Unknown" };
  let browser = "Other";
  if (ua.includes("Chrome") && !ua.includes("Edg")) browser = "Chrome";
  else if (ua.includes("Safari") && !ua.includes("Chrome")) browser = "Safari";
  else if (ua.includes("Firefox")) browser = "Firefox";
  else if (ua.includes("Edg")) browser = "Edge";
  let os = "Other";
  if (ua.includes("Windows")) os = "Windows";
  else if (ua.includes("Mac OS")) os = "macOS";
  else if (ua.includes("iPhone") || ua.includes("iPad")) os = "iOS";
  else if (ua.includes("Android")) os = "Android";
  else if (ua.includes("Linux")) os = "Linux";
  return { browser, os };
}

/* ------------------------------------------------------------------ */
/*  Properties Panel                                                   */
/* ------------------------------------------------------------------ */

interface PropertyRow {
  id: string;
  address: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  email: string | null;
  session_id: string | null;
  warehouse_id: string | null;
  building_size_sqft: number | null;
  clear_height_ft: number | null;
  dock_doors: number | null;
  drive_in_bays: number | null;
  year_built: number | null;
  construction_type: string | null;
  property_type: string | null;
  building_class: string | null;
  sqft: number | null;
  min_rentable: number | null;
  activity_tier: string | null;
  pricing_path: string | null;
  rate_per_sqft: number | null;
  profile_version: number | null;
  lead: { email: string; sqft: number; revenue: number; rate: number; pricing_path: string } | null;
  created_at: string | null;
  updated_at: string | null;
}

interface PropertyDetail extends PropertyRow {
  parking_spaces: number | null;
  has_sprinkler: boolean | null;
  power_supply: string | null;
  zoning: string | null;
  trailer_parking: number | null;
  rail_served: boolean | null;
  fenced_yard: boolean | null;
  column_spacing_ft: string | null;
  number_of_stories: number | null;
  warehouse_heated: boolean | null;
  year_renovated: number | null;
  available_sqft: number | null;
  lot_size_acres: number | null;
  has_office: boolean | null;
  weekend_access: boolean | null;
  min_term_months: number | null;
  availability_start: string | null;
  additional_notes: string | null;
  ai_profile_summary: string | null;
  warehouse: {
    id: string;
    address: string;
    city: string;
    state: string;
    building_size_sqft: number | null;
    year_built: number | null;
    property_type: string | null;
    primary_image_url: string | null;
    image_urls: string[] | null;
    source_url: string | null;
  } | null;
  contextual_memories: {
    id: string;
    memory_type: string | null;
    content: string;
    source: string | null;
    confidence: number | null;
    created_at: string | null;
  }[];
}

function SpecRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex justify-between py-1.5 border-b border-slate-50">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xs font-medium text-slate-800 text-right max-w-[60%]">{value}</span>
    </div>
  );
}

function PropertyDetailPanel({
  detail,
  onClose,
}: {
  detail: PropertyDetail;
  onClose: () => void;
}) {
  // Collect all available images
  const images: string[] = [];
  if (detail.warehouse?.image_urls?.length) {
    images.push(...detail.warehouse.image_urls);
  } else if (detail.warehouse?.primary_image_url) {
    images.push(detail.warehouse.primary_image_url);
  }
  const hasImages = images.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className={`relative bg-white shadow-xl flex flex-col ${hasImages ? "w-full max-w-5xl" : "w-full max-w-lg"}`}>
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between z-10">
          <div>
            <h2 className="text-sm font-bold text-slate-900 truncate max-w-[500px]">
              {detail.address || "Unknown Address"}
            </h2>
            <p className="text-xs text-slate-500">
              {[detail.city, detail.state, detail.zip].filter(Boolean).join(", ")}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-lg font-bold px-2"
          >
            ✕
          </button>
        </div>

        {/* Two-column body */}
        <div className={`flex-1 overflow-hidden flex ${hasImages ? "" : "flex-col"}`}>
          {/* LEFT: Data column (scrollable) */}
          <div className={`overflow-y-auto ${hasImages ? "w-[420px] min-w-[420px] border-r border-slate-100" : "w-full"}`}>
            <div className="px-6 py-5 space-y-6">
              {/* Profile Version Badge */}
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  (detail.profile_version || 0) >= 3
                    ? "bg-emerald-100 text-emerald-700"
                    : (detail.profile_version || 0) >= 2
                    ? "bg-blue-100 text-blue-700"
                    : "bg-slate-100 text-slate-600"
                }`}>
                  v{detail.profile_version || 0}
                </span>
                {detail.email && (
                  <span className="text-xs text-slate-600">{detail.email}</span>
                )}
                {detail.lead && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700">
                    Lead
                  </span>
                )}
              </div>

              {/* Building Specs */}
              <div>
                <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                  Building Specs
                </h3>
                <div className="bg-slate-50 rounded-lg p-3">
                  <SpecRow label="Building Size" value={detail.building_size_sqft ? `${detail.building_size_sqft.toLocaleString()} sqft` : null} />
                  <SpecRow label="Clear Height" value={detail.clear_height_ft ? `${detail.clear_height_ft} ft` : null} />
                  <SpecRow label="Dock Doors" value={detail.dock_doors} />
                  <SpecRow label="Drive-In Bays" value={detail.drive_in_bays} />
                  <SpecRow label="Parking Spaces" value={detail.parking_spaces} />
                  <SpecRow label="Year Built" value={detail.year_built} />
                  <SpecRow label="Year Renovated" value={detail.year_renovated} />
                  <SpecRow label="Construction" value={detail.construction_type} />
                  <SpecRow label="Building Class" value={detail.building_class} />
                  <SpecRow label="Property Type" value={detail.property_type} />
                  <SpecRow label="Stories" value={detail.number_of_stories} />
                  <SpecRow label="Zoning" value={detail.zoning} />
                  <SpecRow label="Lot Size" value={detail.lot_size_acres ? `${detail.lot_size_acres} acres` : null} />
                  <SpecRow label="Column Spacing" value={detail.column_spacing_ft} />
                  <SpecRow label="Sprinkler" value={detail.has_sprinkler === true ? "Yes" : detail.has_sprinkler === false ? "No" : null} />
                  <SpecRow label="Heated" value={detail.warehouse_heated === true ? "Yes" : detail.warehouse_heated === false ? "No" : null} />
                  <SpecRow label="Power Supply" value={detail.power_supply} />
                  <SpecRow label="Rail Served" value={detail.rail_served === true ? "Yes" : detail.rail_served === false ? "No" : null} />
                  <SpecRow label="Fenced Yard" value={detail.fenced_yard === true ? "Yes" : detail.fenced_yard === false ? "No" : null} />
                  <SpecRow label="Trailer Parking" value={detail.trailer_parking} />
                </div>
              </div>

              {/* Configurator Choices */}
              {(detail.sqft || detail.activity_tier || detail.pricing_path) && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                    Configurator Choices
                  </h3>
                  <div className="bg-blue-50 rounded-lg p-3">
                    <SpecRow label="Available Space" value={detail.sqft ? `${detail.sqft.toLocaleString()} sqft` : null} />
                    <SpecRow label="Min Rentable" value={detail.min_rentable ? `${detail.min_rentable.toLocaleString()} sqft` : null} />
                    <SpecRow label="Activity Tier" value={detail.activity_tier} />
                    <SpecRow label="Has Office" value={detail.has_office === true ? "Yes" : detail.has_office === false ? "No" : null} />
                    <SpecRow label="Weekend Access" value={detail.weekend_access === true ? "Yes" : detail.weekend_access === false ? "No" : null} />
                    <SpecRow label="Min Term" value={detail.min_term_months ? `${detail.min_term_months} months` : null} />
                    <SpecRow label="Available From" value={detail.availability_start} />
                    <SpecRow label="Pricing Path" value={detail.pricing_path === "set_rate" ? "Automated" : detail.pricing_path === "commission" ? "Commission" : detail.pricing_path} />
                    <SpecRow label="Rate/sqft" value={detail.rate_per_sqft ? `$${detail.rate_per_sqft.toFixed(2)}/sqft/mo` : null} />
                  </div>
                </div>
              )}

              {/* Lead Info */}
              {detail.lead && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                    Lead Capture
                  </h3>
                  <div className="bg-emerald-50 rounded-lg p-3">
                    <SpecRow label="Email" value={detail.lead.email} />
                    <SpecRow label="Space" value={detail.lead.sqft ? `${detail.lead.sqft.toLocaleString()} sqft` : null} />
                    <SpecRow label="Revenue" value={detail.lead.revenue ? `$${detail.lead.revenue.toLocaleString()}/yr` : null} />
                    <SpecRow label="Rate" value={detail.lead.rate ? `$${detail.lead.rate.toFixed(2)}/sqft/mo` : null} />
                    <SpecRow label="Pricing" value={detail.lead.pricing_path === "set_rate" ? "Automated" : detail.lead.pricing_path === "commission" ? "Commission" : detail.lead.pricing_path} />
                  </div>
                </div>
              )}

              {/* AI Profile Summary */}
              {detail.ai_profile_summary && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                    AI Profile Summary
                  </h3>
                  <div className="bg-purple-50 rounded-lg p-3">
                    <p className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed">
                      {detail.ai_profile_summary}
                    </p>
                  </div>
                </div>
              )}

              {/* Additional Notes */}
              {detail.additional_notes && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                    User Notes
                  </h3>
                  <div className="bg-amber-50 rounded-lg p-3">
                    <p className="text-xs text-slate-700 whitespace-pre-wrap">
                      {detail.additional_notes}
                    </p>
                  </div>
                </div>
              )}

              {/* Contextual Memories */}
              {detail.contextual_memories && detail.contextual_memories.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                    Contextual Memories ({detail.contextual_memories.length})
                  </h3>
                  <div className="space-y-2">
                    {detail.contextual_memories.map((m) => (
                      <div key={m.id} className="bg-slate-50 rounded-lg p-3 border border-slate-100">
                        <div className="flex items-center gap-2 mb-1">
                          {m.memory_type && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-200 text-slate-600 uppercase">
                              {m.memory_type}
                            </span>
                          )}
                          {m.source && (
                            <span className="text-[10px] text-slate-400">{m.source}</span>
                          )}
                          {m.confidence !== null && (
                            <span className="text-[10px] text-slate-400">
                              conf: {(m.confidence * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed">
                          {m.content}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warehouse Source */}
              {detail.warehouse?.source_url && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-2">
                    Source
                  </h3>
                  <a
                    href={detail.warehouse.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-emerald-600 hover:underline break-all"
                  >
                    {detail.warehouse.source_url}
                  </a>
                </div>
              )}

              {/* Timestamps */}
              <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-100">
                <p>Created: {detail.created_at ? new Date(detail.created_at).toLocaleString() : "—"}</p>
                <p>Updated: {detail.updated_at ? new Date(detail.updated_at).toLocaleString() : "—"}</p>
                <p>Session: {detail.session_id || "—"}</p>
              </div>
            </div>
          </div>

          {/* RIGHT: Image gallery (wider side) */}
          {hasImages && (
            <div className="flex-1 overflow-y-auto bg-slate-50 p-4">
              <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wider mb-3">
                Property Images ({images.length})
              </h3>
              <div className="space-y-3">
                {images.map((url, i) => (
                  <a
                    key={i}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-lg overflow-hidden border border-slate-200 hover:border-emerald-300 transition-colors shadow-sm hover:shadow-md"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={url}
                      alt={`Property image ${i + 1}`}
                      className="w-full h-auto object-cover"
                      loading="lazy"
                    />
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PropertiesPanel() {
  const [properties, setProperties] = useState<PropertyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PropertyDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.earncheckProperties();
      setProperties(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (id: string) => {
    setSelectedId(id);
    setDetailLoading(true);
    try {
      const res = await api.earncheckPropertyDetail(id);
      setDetail(res);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedId(null);
    setDetail(null);
  };

  if (error) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
        <p className="text-red-500 mb-3">{error}</p>
        <button onClick={load} className="text-sm text-emerald-600 hover:underline">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 className="w-4 h-4 text-emerald-600" />
          <h2 className="text-sm font-semibold text-slate-900">
            Searched Properties ({properties.length})
          </h2>
        </div>
        <button
          onClick={load}
          className="text-slate-400 hover:text-emerald-600 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 text-left">
              <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Address</th>
              <th className="px-4 py-2.5 text-xs font-medium text-slate-500">City / State</th>
              <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Size</th>
              <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Email</th>
              <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Version</th>
              <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && properties.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto" />
                </td>
              </tr>
            ) : properties.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  No properties searched yet
                </td>
              </tr>
            ) : (
              properties.map((p) => {
                const time = p.created_at
                  ? new Date(p.created_at).toLocaleString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                      hour12: true,
                    })
                  : "—";
                return (
                  <tr
                    key={p.id}
                    className="hover:bg-emerald-50/30 cursor-pointer transition-colors"
                    onClick={() => openDetail(p.id)}
                  >
                    <td className="px-4 py-2.5 text-slate-800 font-medium max-w-[250px] truncate">
                      {p.address || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 whitespace-nowrap">
                      {[p.city, p.state].filter(Boolean).join(", ") || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600 whitespace-nowrap">
                      {p.building_size_sqft ? `${p.building_size_sqft.toLocaleString()} sqft` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500 max-w-[180px] truncate">
                      {p.email || "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                        (p.profile_version || 0) >= 3
                          ? "bg-emerald-100 text-emerald-700"
                          : (p.profile_version || 0) >= 2
                          ? "bg-blue-100 text-blue-700"
                          : "bg-slate-100 text-slate-600"
                      }`}>
                        v{p.profile_version || 0}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap text-xs">
                      {time}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Detail slide-out */}
      {selectedId && detailLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
        </div>
      )}
      {selectedId && detail && !detailLoading && (
        <PropertyDetailPanel detail={detail} onClose={closeDetail} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Visitors Panel                                                     */
/* ------------------------------------------------------------------ */

function VisitorsPanel({ days }: { days: number }) {
  const [visitors, setVisitors] = useState<VisitorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.earncheckVisitors(days);
      setVisitors(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load visitors");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-red-500 mb-4">{error}</p>
        <button onClick={load} className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm">
          Retry
        </button>
      </div>
    );
  }

  // Summary stats
  const uniqueIPs = new Set(visitors.map((v) => v.ip).filter(Boolean)).size;
  const uniqueSessions = new Set(visitors.map((v) => v.session_id).filter(Boolean)).size;
  const withReferrer = visitors.filter((v) => v.referrer).length;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
              <Globe className="w-4 h-4 text-blue-600" />
            </div>
            <p className="text-sm text-slate-500">Unique IPs</p>
          </div>
          <p className="text-2xl font-bold text-slate-900">{uniqueIPs}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center">
              <Users className="w-4 h-4 text-emerald-600" />
            </div>
            <p className="text-sm text-slate-500">Unique Sessions</p>
          </div>
          <p className="text-2xl font-bold text-slate-900">{uniqueSessions}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-amber-50 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-amber-600" />
            </div>
            <p className="text-sm text-slate-500">With Referrer</p>
          </div>
          <p className="text-2xl font-bold text-slate-900">{withReferrer}</p>
        </div>
      </div>

      {/* Visitors table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">
            Recent Visitors ({visitors.length})
          </h2>
          <button
            onClick={load}
            className="text-slate-400 hover:text-emerald-600 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-left">
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Time</th>
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">IP</th>
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">City</th>
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Page</th>
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Referrer</th>
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">Browser / OS</th>
                <th className="px-4 py-2.5 text-xs font-medium text-slate-500">UTM</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visitors.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No visitors recorded yet
                  </td>
                </tr>
              ) : (
                visitors.map((v) => {
                  const { browser, os } = parseUA(v.user_agent);
                  const time = v.created_at
                    ? new Date(v.created_at).toLocaleString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })
                    : "—";
                  let refDisplay = "—";
                  if (v.referrer) {
                    try {
                      refDisplay = new URL(v.referrer).hostname;
                    } catch {
                      refDisplay = v.referrer.slice(0, 30);
                    }
                  }
                  const utm = [v.utm_source, v.utm_medium, v.utm_campaign]
                    .filter(Boolean)
                    .join(" / ");

                  return (
                    <tr key={v.id} className="hover:bg-slate-50/50">
                      <td className="px-4 py-2.5 text-slate-600 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5 text-slate-400" />
                          {time}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-700">
                        {v.ip || "—"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600 text-xs whitespace-nowrap">
                        {v.city || "—"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600 max-w-[200px] truncate">
                        {v.path}
                      </td>
                      <td className="px-4 py-2.5 text-slate-500 max-w-[180px] truncate">
                        {refDisplay}
                      </td>
                      <td className="px-4 py-2.5 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <Monitor className="w-3.5 h-3.5 text-slate-400" />
                          <span className="text-slate-600">{browser}</span>
                          <span className="text-slate-300">/</span>
                          <span className="text-slate-500">{os}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-slate-500 text-xs max-w-[150px] truncate">
                        {utm || "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function EarnCheckDashboard() {
  const [authed, setAuthed] = useState(() => {
    if (typeof window !== "undefined") {
      return sessionStorage.getItem("wex_admin") === "1";
    }
    return false;
  });
  const [pw, setPw] = useState("");
  const [pwError, setPwError] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);

  const [tab, setTab] = useState<"analytics" | "visitors" | "properties">("analytics");
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(0);

  const handleLogin = async () => {
    setPwLoading(true);
    setPwError(false);
    try {
      await api.adminLogin(pw);
      sessionStorage.setItem("wex_admin", "1");
      setAuthed(true);
    } catch {
      setPwError(true);
    } finally {
      setPwLoading(false);
    }
  };

  const loadData = useCallback(async (d: number) => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.earncheckAnalytics(d);
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) loadData(days);
  }, [days, loadData, authed]);

  if (!authed) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="bg-white rounded-xl border border-slate-200 p-8 w-full max-w-sm shadow-sm">
          <div className="flex items-center justify-center mb-6">
            <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center">
              <Lock className="w-6 h-6 text-emerald-600" />
            </div>
          </div>
          <h2 className="text-lg font-bold text-slate-900 text-center mb-1">
            Admin Dashboard
          </h2>
          <p className="text-sm text-slate-500 text-center mb-6">
            Enter password to continue
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleLogin();
            }}
          >
            <input
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="Password"
              className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent mb-3"
              autoFocus
            />
            {pwError && (
              <p className="text-red-500 text-xs mb-3">Invalid password</p>
            )}
            <button
              type="submit"
              disabled={pwLoading || !pw}
              className="w-full py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 transition-colors"
            >
              {pwLoading ? "Checking..." : "Sign In"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={() => loadData(days)}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold text-slate-900">
              EarnCheck Analytics
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {/* Tab switcher */}
            <div className="flex bg-slate-100 rounded-lg p-0.5 mr-2">
              <button
                onClick={() => setTab("analytics")}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  tab === "analytics"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                Analytics
              </button>
              <button
                onClick={() => setTab("visitors")}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  tab === "visitors"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                Visitors
              </button>
              <button
                onClick={() => setTab("properties")}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  tab === "properties"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                Properties
              </button>
            </div>
            {/* Time range */}
            <div className="flex bg-slate-100 rounded-lg p-0.5">
              {TIME_RANGES.map((r) => (
                <button
                  key={r.value}
                  onClick={() => setDays(r.value)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    days === r.value
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <button
              onClick={() => loadData(days)}
              className="text-slate-400 hover:text-emerald-600 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </header>

      {/* Visitors tab */}
      {tab === "visitors" && (
        <main className="max-w-6xl mx-auto px-6 py-6">
          <VisitorsPanel days={days} />
        </main>
      )}

      {/* Properties tab */}
      {tab === "properties" && (
        <main className="max-w-6xl mx-auto px-6 py-6">
          <PropertiesPanel />
        </main>
      )}

      {/* Analytics tab */}
      {tab === "analytics" && !data ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
        </div>
      ) : tab === "analytics" && data && (
        <main className="max-w-6xl mx-auto px-6 py-6 space-y-6">
          {/* Hero KPIs — 4 cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
                  <Building2 className="w-5 h-5 text-emerald-600" />
                </div>
                <p className="text-sm text-slate-500">Properties Searched</p>
              </div>
              <p className="text-3xl font-bold text-slate-900">
                {data.kpis.properties_searched > 0 ? formatNumber(data.kpis.properties_searched) : "—"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
                  <Warehouse className="w-5 h-5 text-emerald-600" />
                </div>
                <p className="text-sm text-slate-500">Total Available Space</p>
              </div>
              <p className="text-3xl font-bold text-slate-900">
                {data.kpis.total_sqft > 0 ? `${formatNumber(data.kpis.total_sqft)} sqft` : "—"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
                  <CalendarDays className="w-5 h-5 text-emerald-600" />
                </div>
                <p className="text-sm text-slate-500">Monthly Property Value</p>
              </div>
              <p className="text-3xl font-bold text-slate-900">
                {data.kpis.total_monthly_value > 0 ? formatCurrency(data.kpis.total_monthly_value) : "—"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-emerald-50 flex items-center justify-center">
                  <DollarSign className="w-5 h-5 text-emerald-600" />
                </div>
                <p className="text-sm text-slate-500">Annual Property Value</p>
              </div>
              <p className="text-3xl font-bold text-slate-900">
                {data.kpis.total_annual_value > 0 ? formatCurrency(data.kpis.total_annual_value) : "—"}
              </p>
            </div>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              label="Page Views"
              value={formatNumber(data.kpis.total_page_views)}
              icon={Users}
            />
            <KPICard
              label="Engaged Visitors"
              value={formatNumber(data.kpis.total_sessions)}
              icon={Search}
            />
            <KPICard
              label="Emails Submitted"
              value={formatNumber(data.kpis.emails_submitted)}
              icon={Mail}
            />
            <KPICard
              label="Conversion"
              value={`${data.kpis.conversion_rate}%`}
              icon={TrendingUp}
            />
          </div>

          {/* User Journey — square cards */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h2 className="text-sm font-semibold text-slate-900 mb-4">
              User Journey
            </h2>
            <FunnelSquares phases={data.funnel} />
          </div>

          {/* Pricing Split */}
          {(data.pricing_split.automated > 0 || data.pricing_split.manual > 0) && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-900 mb-4">
                Pricing Model Choice
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-emerald-50 rounded-xl p-4 text-center border border-emerald-100">
                  <ToggleLeft className="w-5 h-5 text-emerald-600 mx-auto mb-2" />
                  <p className="text-xs font-medium text-emerald-700 mb-1">Automated</p>
                  <p className="text-2xl font-bold text-emerald-700">{data.pricing_split.automated}</p>
                </div>
                <div className="bg-slate-50 rounded-xl p-4 text-center border border-slate-100">
                  <ToggleRight className="w-5 h-5 text-slate-500 mx-auto mb-2" />
                  <p className="text-xs font-medium text-slate-500 mb-1">Manual</p>
                  <p className="text-2xl font-bold text-slate-700">{data.pricing_split.manual}</p>
                </div>
              </div>
            </div>
          )}

          {/* Two-column: Top Cities + Top States */}
          <div className="grid lg:grid-cols-2 gap-6">
            <GeoList
              title="Top Cities"
              icon={MapPin}
              topItems={data.top_cities}
              allItems={data.all_cities}
              labelKey="city"
            />
            <GeoList
              title="Top States"
              icon={Building2}
              topItems={data.top_states}
              allItems={data.all_states}
              labelKey="state"
            />
          </div>

          {/* Top Referrers */}
          {data.top_referrers && data.top_referrers.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-900 mb-4">
                Top Referrers
              </h2>
              <div className="space-y-2">
                {data.top_referrers.map((r) => {
                  let display = r.referrer;
                  try { display = new URL(r.referrer).hostname; } catch {}
                  return (
                    <div key={r.referrer} className="flex items-center justify-between text-sm">
                      <span className="text-slate-600 truncate max-w-[80%]">{display}</span>
                      <span className="text-slate-900 font-semibold">{r.count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI Chat */}
          <AIChatPanel />
        </main>
      )}
    </div>
  );
}
