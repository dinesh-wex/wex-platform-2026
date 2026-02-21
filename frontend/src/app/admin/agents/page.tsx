"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Activity,
  Loader2,
  AlertCircle,
  Clock,
  Zap,
  Filter,
  Cpu,
} from "lucide-react";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface AgentInfo {
  name: string;
  key: string;
  total_actions: number;
  avg_latency_ms: number;
  last_action: string;
  total_tokens: number;
}

interface AgentAction {
  id: string;
  agent: string;
  action_type: string;
  summary: string;
  timestamp: string;
  latency_ms: number;
}

/* ------------------------------------------------------------------ */
/*  Agent color map                                                    */
/* ------------------------------------------------------------------ */
const AGENT_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  activation: { bg: "bg-blue-100", text: "text-blue-700", border: "border-blue-300" },
  memory: { bg: "bg-purple-100", text: "text-purple-700", border: "border-purple-300" },
  clearing: { bg: "bg-green-100", text: "text-green-700", border: "border-green-300" },
  buyer: { bg: "bg-amber-100", text: "text-amber-700", border: "border-amber-300" },
  pricing: { bg: "bg-indigo-100", text: "text-indigo-700", border: "border-indigo-300" },
  settlement: { bg: "bg-rose-100", text: "text-rose-700", border: "border-rose-300" },
};

function getAgentColor(agent: string) {
  const key = agent.toLowerCase();
  for (const [k, v] of Object.entries(AGENT_COLORS)) {
    if (key.includes(k)) return v;
  }
  return { bg: "bg-gray-100", text: "text-gray-700", border: "border-gray-300" };
}

/* ------------------------------------------------------------------ */
/*  Demo data                                                          */
/* ------------------------------------------------------------------ */
const DEMO_AGENTS: AgentInfo[] = [
  { name: "Activation Agent", key: "activation", total_actions: 142, avg_latency_ms: 1850, last_action: "5 min ago", total_tokens: 248500 },
  { name: "Memory Agent", key: "memory", total_actions: 389, avg_latency_ms: 520, last_action: "10 min ago", total_tokens: 156200 },
  { name: "Clearing Agent", key: "clearing", total_actions: 215, avg_latency_ms: 1340, last_action: "2 min ago", total_tokens: 312800 },
  { name: "Buyer Agent", key: "buyer", total_actions: 178, avg_latency_ms: 1560, last_action: "8 min ago", total_tokens: 289400 },
  { name: "Pricing Agent", key: "pricing", total_actions: 256, avg_latency_ms: 890, last_action: "3 min ago", total_tokens: 178600 },
  { name: "Settlement Agent", key: "settlement", total_actions: 98, avg_latency_ms: 1120, last_action: "12 min ago", total_tokens: 145300 },
];

const DEMO_ACTIONS: AgentAction[] = [
  { id: "a1", agent: "Clearing Agent", action_type: "match", summary: "Matched Acme Logistics with Downtown Distribution Center - score 94", timestamp: "2 min ago", latency_ms: 1240 },
  { id: "a2", agent: "Pricing Agent", action_type: "rate_set", summary: "Set buyer rate $9.75/sqft for match M-1042 based on market analysis", timestamp: "3 min ago", latency_ms: 890 },
  { id: "a3", agent: "Activation Agent", action_type: "activation", summary: "Completed warehouse activation for Eastgate Cold Storage - all 5 steps passed", timestamp: "5 min ago", latency_ms: 2100 },
  { id: "a4", agent: "Buyer Agent", action_type: "intake", summary: "Intake complete for QuickShip Inc - 40,000 sqft distribution center needed in Plano", timestamp: "8 min ago", latency_ms: 1560 },
  { id: "a5", agent: "Memory Agent", action_type: "update", summary: "Updated truth core for Airport Logistics Hub - added dock configuration data", timestamp: "10 min ago", latency_ms: 450 },
  { id: "a6", agent: "Settlement Agent", action_type: "tour", summary: "Tour confirmed for TechParts Co at Irving facility - scheduled for tomorrow 2pm", timestamp: "12 min ago", latency_ms: 980 },
  { id: "a7", agent: "Clearing Agent", action_type: "rescore", summary: "Re-scored 3 pending matches after supplier rate update on Northside Warehouse", timestamp: "15 min ago", latency_ms: 1800 },
  { id: "a8", agent: "Pricing Agent", action_type: "analysis", summary: "Market rate analysis complete for DFW cold storage segment - rates trending up 3%", timestamp: "18 min ago", latency_ms: 720 },
  { id: "a9", agent: "Activation Agent", action_type: "start", summary: "Started activation for Southside Flex Space - collecting warehouse details", timestamp: "22 min ago", latency_ms: 340 },
  { id: "a10", agent: "Buyer Agent", action_type: "register", summary: "Registered new buyer MedSupply LLC - medical supply distribution company", timestamp: "25 min ago", latency_ms: 670 },
  { id: "a11", agent: "Memory Agent", action_type: "embed", summary: "Generated embeddings for 3 newly activated warehouses", timestamp: "28 min ago", latency_ms: 380 },
  { id: "a12", agent: "Settlement Agent", action_type: "terms", summary: "Generated deal terms for match M-1038 - 12 month standard lease", timestamp: "32 min ago", latency_ms: 1450 },
  { id: "a13", agent: "Clearing Agent", action_type: "match", summary: "Generated 4 potential matches for FreshCo Foods cold chain requirement", timestamp: "35 min ago", latency_ms: 2200 },
  { id: "a14", agent: "Pricing Agent", action_type: "spread", summary: "Calculated optimal spread for match M-1035: 14.7% margin", timestamp: "40 min ago", latency_ms: 560 },
  { id: "a15", agent: "Buyer Agent", action_type: "chat", summary: "Guided TechParts Co through space requirements - refined from 20k to 15k sqft", timestamp: "45 min ago", latency_ms: 1890 },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function AgentsPage() {
  const [agentInfos, setAgentInfos] = useState<AgentInfo[]>(DEMO_AGENTS);
  const [actions, setActions] = useState<AgentAction[]>(DEMO_ACTIONS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterAgent, setFilterAgent] = useState<string>("all");

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const result = await api.adminAgents();
      if (result.agents) setAgentInfos(result.agents);
      if (result.actions) setActions(result.actions);
    } catch {
      setError("Could not connect to backend");
    } finally {
      setLoading(false);
    }
  }

  const filteredActions =
    filterAgent === "all"
      ? actions
      : actions.filter((a) => a.agent.toLowerCase().includes(filterAgent));

  // Compute average latency per agent from actions
  const agentLatencyMap: Record<string, { total: number; count: number }> = {};
  for (const a of actions) {
    const key = a.agent;
    if (!agentLatencyMap[key]) agentLatencyMap[key] = { total: 0, count: 0 };
    agentLatencyMap[key].total += a.latency_ms;
    agentLatencyMap[key].count += 1;
  }

  const totalTokens = agentInfos.reduce((sum, a) => sum + a.total_tokens, 0);

  function formatNumber(num: number): string {
    return new Intl.NumberFormat("en-US").format(num);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/admin" className="text-slate-400 hover:text-slate-600 transition-colors">
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-900">
                  W<span className="text-blue-500">Ex</span>
                </h1>
                <span className="text-slate-300">|</span>
                <span className="text-sm font-medium text-slate-600">Agent Activity</span>
              </div>
            </div>
            {error && (
              <span className="flex items-center gap-1.5 text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full">
                <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
                Demo Mode
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mb-4" />
            <p className="text-slate-500">Loading agent data...</p>
          </div>
        )}

        {/* Error Banner */}
        {error && !loading && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-start gap-3 mb-6">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">Could not connect to backend</p>
              <p className="text-xs text-amber-600 mt-1">Showing demo data. Start the FastAPI backend for live data.</p>
            </div>
          </div>
        )}

        {!loading && (
          <>
            {/* Agent Status Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
              {agentInfos.map((agent) => {
                const color = getAgentColor(agent.key);
                return (
                  <div
                    key={agent.key}
                    className={`bg-white rounded-xl border-2 ${color.border} p-5 shadow-sm hover:shadow-md transition-shadow`}
                  >
                    <div className="flex items-center gap-3 mb-3">
                      <span className={`${color.bg} ${color.text} text-xs font-bold px-2.5 py-1 rounded-full`}>
                        {agent.name.replace(" Agent", "")}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-xs text-slate-400">Total Actions</p>
                        <p className="text-lg font-bold text-slate-900">{formatNumber(agent.total_actions)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-400">Avg Latency</p>
                        <p className="text-lg font-bold text-slate-900">{formatNumber(agent.avg_latency_ms)}ms</p>
                      </div>
                    </div>
                    <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs text-slate-400">
                        <Clock className="w-3 h-3" />
                        <span>Last: {agent.last_action}</span>
                      </div>
                      <span className="text-xs text-slate-400">{formatNumber(agent.total_tokens)} tokens</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Activity Timeline */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-8">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-purple-600" />
                  <h2 className="text-lg font-semibold text-slate-900">Activity Timeline</h2>
                </div>
                <div className="flex items-center gap-2">
                  <Filter className="w-4 h-4 text-slate-400" />
                  <select
                    value={filterAgent}
                    onChange={(e) => setFilterAgent(e.target.value)}
                    className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-slate-700 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="all">All Agents</option>
                    <option value="activation">Activation</option>
                    <option value="memory">Memory</option>
                    <option value="clearing">Clearing</option>
                    <option value="buyer">Buyer</option>
                    <option value="pricing">Pricing</option>
                    <option value="settlement">Settlement</option>
                  </select>
                </div>
              </div>

              <div className="space-y-0 max-h-[600px] overflow-y-auto">
                {filteredActions.map((action) => {
                  const color = getAgentColor(action.agent);
                  return (
                    <div key={action.id} className="flex items-start gap-4 py-3 border-b border-gray-50 last:border-0">
                      <span className="text-xs text-slate-400 whitespace-nowrap mt-0.5 w-20 text-right flex-shrink-0">
                        {action.timestamp}
                      </span>
                      <div className="flex-shrink-0 mt-0.5">
                        <span className={`${color.bg} ${color.text} text-xs font-medium px-2 py-0.5 rounded-full`}>
                          {action.agent.replace(" Agent", "")}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-xs font-medium text-slate-500 bg-gray-100 px-1.5 py-0.5 rounded">
                            {action.action_type}
                          </span>
                          <span className="text-xs text-slate-400">{action.latency_ms}ms</span>
                        </div>
                        <p className="text-sm text-slate-700">{action.summary}</p>
                      </div>
                    </div>
                  );
                })}

                {filteredActions.length === 0 && (
                  <div className="text-center py-10">
                    <p className="text-sm text-slate-400">No actions found for this filter.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Performance Stats */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
              <div className="flex items-center gap-2 mb-4">
                <Cpu className="w-5 h-5 text-indigo-600" />
                <h2 className="text-lg font-semibold text-slate-900">Performance Overview</h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Avg Latency per Agent */}
                <div>
                  <h3 className="text-sm font-medium text-slate-600 mb-3">Average Latency by Agent</h3>
                  <div className="space-y-3">
                    {agentInfos.map((agent) => {
                      const color = getAgentColor(agent.key);
                      const maxLatency = Math.max(...agentInfos.map((a) => a.avg_latency_ms));
                      const widthPct = maxLatency > 0 ? (agent.avg_latency_ms / maxLatency) * 100 : 0;
                      return (
                        <div key={agent.key}>
                          <div className="flex items-center justify-between mb-1">
                            <span className={`${color.bg} ${color.text} text-xs font-medium px-2 py-0.5 rounded-full`}>
                              {agent.name.replace(" Agent", "")}
                            </span>
                            <span className="text-xs font-medium text-slate-600">{formatNumber(agent.avg_latency_ms)}ms</span>
                          </div>
                          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${color.bg.replace("100", "400")}`}
                              style={{ width: `${widthPct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Token Usage */}
                <div>
                  <h3 className="text-sm font-medium text-slate-600 mb-3">Token Usage by Agent</h3>
                  <div className="space-y-3">
                    {agentInfos.map((agent) => {
                      const color = getAgentColor(agent.key);
                      const widthPct = totalTokens > 0 ? (agent.total_tokens / totalTokens) * 100 : 0;
                      return (
                        <div key={agent.key}>
                          <div className="flex items-center justify-between mb-1">
                            <span className={`${color.bg} ${color.text} text-xs font-medium px-2 py-0.5 rounded-full`}>
                              {agent.name.replace(" Agent", "")}
                            </span>
                            <span className="text-xs font-medium text-slate-600">{formatNumber(agent.total_tokens)}</span>
                          </div>
                          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${color.bg.replace("100", "400")}`}
                              style={{ width: `${widthPct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-4 pt-3 border-t border-gray-100">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-600">Total Tokens</span>
                      <div className="flex items-center gap-1.5">
                        <Zap className="w-3.5 h-3.5 text-amber-500" />
                        <span className="text-sm font-bold text-slate-900">{formatNumber(totalTokens)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="text-center py-6 border-t border-gray-100 mt-8">
              <p className="text-xs text-slate-400">
                Powered by W<span className="text-blue-500 font-semibold">Ex</span> Clearing House | Agent Monitor
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
