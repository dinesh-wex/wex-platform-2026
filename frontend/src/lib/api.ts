import { getToken, removeToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchAPI(path: string, options?: RequestInit) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> || {}),
  };

  const token = getToken();
  if (token) {
    headers["Authorization"] = "Bearer " + token;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    removeToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Auth endpoints
// ---------------------------------------------------------------------------

export function login(email: string, password: string) {
  return fetchAPI("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function signup(
  email: string,
  password: string,
  name: string,
  role: string,
  company?: string,
  phone?: string,
) {
  return fetchAPI("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, name, role, company, phone }),
  });
}

export function getMe() {
  return fetchAPI("/api/auth/me");
}

export function updateProfile(data: { name?: string; company?: string; phone?: string }) {
  return fetchAPI("/api/auth/profile", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function logout() {
  removeToken();
}

// ---------------------------------------------------------------------------
// Existing API object
// ---------------------------------------------------------------------------

export const api = {
  // Supplier endpoints
  supplierLogin: (email: string) =>
    fetchAPI(`/api/supplier/login`, { method: 'POST', body: JSON.stringify({ email }) }),
  warehouseLookup: (address: string, sessionId?: string, isTest?: boolean) => {
    let url = `/api/supplier/warehouse/lookup?address=${encodeURIComponent(address)}`;
    if (sessionId) url += `&session_id=${encodeURIComponent(sessionId)}`;
    if (isTest) url += `&is_test=true`;
    return fetchAPI(url);
  },
  getWarehouses: (params?: { status?: string; owner_email?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.owner_email) searchParams.set('owner_email', params.owner_email);
    const qs = searchParams.toString();
    return fetchAPI(`/api/supplier/warehouses${qs ? `?${qs}` : ''}`);
  },
  getWarehouse: (id: string) =>
    fetchAPI(`/api/supplier/warehouse/${id}`),
  toggleWarehouse: (id: string, status: string, reason?: string) =>
    fetchAPI(`/api/supplier/warehouse/${id}/toggle`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason }),
    }),
  activateWarehouse: (id: string, data: any) =>
    fetchAPI(`/api/supplier/warehouse/${id}/activate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  startActivation: (warehouseId: string) =>
    fetchAPI('/api/supplier/activate/start', {
      method: 'POST',
      body: JSON.stringify({ warehouse_id: warehouseId }),
    }),
  sendActivationMessage: (data: any) =>
    fetchAPI('/api/supplier/activate/chat', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getRevenue: (id: string) =>
    fetchAPI(`/api/supplier/warehouse/${id}/revenue`),
  spaceEstimate: (data: { sqft: number; city?: string; state?: string; zip?: string }) =>
    fetchAPI('/api/supplier/estimate', { method: 'POST', body: JSON.stringify(data) }),
  trackEvent: (data: { event: string; properties: Record<string, unknown>; session_id: string }) =>
    fetchAPI('/api/supplier/track', { method: 'POST', body: JSON.stringify(data) }),
  streetViewUrl: (address: string) =>
    `${API_BASE}/api/supplier/street-view?address=${encodeURIComponent(address)}`,
  trackPageView: (data: { path: string; referrer?: string; utm_source?: string; utm_medium?: string; utm_campaign?: string; session_id?: string; is_test?: boolean }) =>
    fetchAPI('/api/supplier/pageview', { method: 'POST', body: JSON.stringify(data) }).catch(() => {}),

  // Onboarding
  onboardSupplier: (warehouseId: string, agreementAccepted: boolean) =>
    fetchAPI('/api/supplier/onboard', {
      method: 'POST',
      body: JSON.stringify({ warehouse_id: warehouseId, agreement_accepted: agreementAccepted }),
    }),

  // Buyer endpoints
  registerBuyer: (data: { name: string; company: string; email: string; phone: string }) =>
    fetchAPI('/api/buyer/register', { method: 'POST', body: JSON.stringify(data) }),
  getBuyer: (id: string) => fetchAPI(`/api/buyer/${id}`),
  createNeed: (data: any) =>
    fetchAPI('/api/buyer/need', { method: 'POST', body: JSON.stringify(data) }),
  getBuyerNeeds: (buyerId: string) => fetchAPI(`/api/buyer/${buyerId}/needs`),
  startBuyerChat: (needId: string) =>
    fetchAPI(`/api/buyer/need/${needId}/chat/start`, { method: 'POST' }),
  sendBuyerMessage: (needId: string, data: any) =>
    fetchAPI(`/api/buyer/need/${needId}/chat`, { method: 'POST', body: JSON.stringify(data) }),
  getClearedOptions: (needId: string) => fetchAPI(`/api/buyer/need/${needId}/options`),
  acceptMatch: (needId: string, data: { match_id: string; deal_type: string }) =>
    fetchAPI(`/api/buyer/need/${needId}/accept`, { method: 'POST', body: JSON.stringify(data) }),
  getBuyerDeals: (buyerId: string) => fetchAPI(`/api/buyer/${buyerId}/deals`),

  // Tour flow (anti-circumvention)
  signGuarantee: (dealId: string) =>
    fetchAPI(`/api/buyer/deal/${dealId}/guarantee`, {
      method: 'POST',
      body: JSON.stringify({ accepted: true }),
    }),
  scheduleTour: (dealId: string, data: { preferred_date: string; preferred_time: string; notes?: string }) =>
    fetchAPI(`/api/buyer/deal/${dealId}/tour`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  recordTourOutcome: (dealId: string, data: { outcome: string; reason?: string }) =>
    fetchAPI(`/api/buyer/deal/${dealId}/tour-outcome`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Supplier tour endpoints
  confirmTour: (dealId: string, data: { confirmed: boolean; proposed_date?: string; proposed_time?: string }) =>
    fetchAPI(`/api/supplier/deal/${dealId}/tour/confirm`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getUpcomingTours: (ownerEmail?: string) => {
    const qs = ownerEmail ? `?owner_email=${encodeURIComponent(ownerEmail)}` : '';
    return fetchAPI(`/api/supplier/tours${qs}`);
  },

  // Clearing
  triggerClearing: (buyerNeedId: string) =>
    fetchAPI('/api/clearing/match', { method: 'POST', body: JSON.stringify({ buyer_need_id: buyerNeedId }) }),

  // Admin endpoints
  adminOverview: () => fetchAPI('/api/admin/overview'),
  adminWarehouses: () => fetchAPI('/api/admin/warehouses'),
  adminDeals: (status?: string) => fetchAPI(`/api/admin/deals${status ? `?status=${status}` : ''}`),
  adminDealDetail: (id: string) => fetchAPI(`/api/admin/deals/${id}`),
  adminAgents: () => fetchAPI('/api/admin/agents'),
  adminLedger: () => fetchAPI('/api/admin/ledger'),
  adminClearingStats: () => fetchAPI('/api/admin/clearing/stats'),
  adminAcceptDeal: (matchId: string, dealType: string) =>
    fetchAPI('/api/admin/settlement/accept', { method: 'POST', body: JSON.stringify({ match_id: matchId, deal_type: dealType }) }),
  adminTourAction: (dealId: string, action: string, data?: any) =>
    fetchAPI('/api/admin/settlement/tour', { method: 'POST', body: JSON.stringify({ deal_id: dealId, action, ...data }) }),
  adminDealSummary: (dealId: string) => fetchAPI(`/api/admin/settlement/deal/${dealId}/summary`),

  // EarnCheck Analytics
  earncheckAnalytics: (days?: number) =>
    fetchAPI(`/api/admin/earncheck/analytics${days ? `?days=${days}` : ''}`),
  earncheckVisitors: (days?: number) =>
    fetchAPI(`/api/admin/earncheck/visitors${days ? `?days=${days}` : ''}`),
  earncheckChat: (question: string) =>
    fetchAPI('/api/admin/earncheck/chat', { method: 'POST', body: JSON.stringify({ question }) }),
  earncheckProperties: () =>
    fetchAPI('/api/admin/earncheck/properties'),
  earncheckPropertyDetail: (id: string) =>
    fetchAPI(`/api/admin/earncheck/properties/${id}`),
  adminLogin: (password: string) =>
    fetchAPI('/api/admin/earncheck/login', { method: 'POST', body: JSON.stringify({ password }) }),

  // Browse
  browseListings: (params?: {
    city?: string;
    state?: string;
    min_sqft?: number;
    max_sqft?: number;
    use_type?: string;
    features?: string;
    page?: number;
    per_page?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.city) searchParams.set('city', params.city);
    if (params?.state) searchParams.set('state', params.state);
    if (params?.min_sqft) searchParams.set('min_sqft', String(params.min_sqft));
    if (params?.max_sqft) searchParams.set('max_sqft', String(params.max_sqft));
    if (params?.use_type) searchParams.set('use_type', params.use_type);
    if (params?.features) searchParams.set('features', params.features);
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.per_page) searchParams.set('per_page', String(params.per_page));
    const qs = searchParams.toString();
    return fetchAPI(`/api/browse/listings${qs ? `?${qs}` : ''}`);
  },
  browseLocations: (q?: string) =>
    fetchAPI(`/api/browse/locations${q ? `?q=${encodeURIComponent(q)}` : ''}`),

  // DLA (Demand-Led Activation)
  resolveDLAToken: (token: string) =>
    fetchAPI(`/api/dla/token/${token}`),
  submitDLARate: (token: string, data: { accepted: boolean; proposed_rate?: number }) =>
    fetchAPI(`/api/dla/token/${token}/rate`, { method: 'POST', body: JSON.stringify(data) }),
  confirmDLA: (token: string, data?: { agreement_ref?: string; stripe_setup?: boolean; available_from?: string; available_to?: string; restrictions?: string }) =>
    fetchAPI(`/api/dla/token/${token}/confirm`, { method: 'POST', body: JSON.stringify(data || {}) }),
  storeDLAOutcome: (token: string, data: { outcome: string; reason?: string; rate_floor?: number }) =>
    fetchAPI(`/api/dla/token/${token}/outcome`, { method: 'POST', body: JSON.stringify(data) }),

  // Enrichment (progressive profile building)
  getNextEnrichmentQuestion: (warehouseId: string) =>
    fetchAPI(`/api/enrichment/warehouse/${warehouseId}/next`),
  submitEnrichmentResponse: (warehouseId: string, data: { question_id: string; response: string }) =>
    fetchAPI(`/api/enrichment/warehouse/${warehouseId}/respond`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getProfileCompleteness: (warehouseId: string) =>
    fetchAPI(`/api/enrichment/warehouse/${warehouseId}/completeness`),
  uploadPhotos: (warehouseId: string, photoUrls: string[]) =>
    fetchAPI(`/api/enrichment/warehouse/${warehouseId}/photos`, {
      method: 'POST',
      body: JSON.stringify({ photo_urls: photoUrls }),
    }),
  getEnrichmentHistory: (warehouseId: string) =>
    fetchAPI(`/api/enrichment/warehouse/${warehouseId}/history`),

  // Anonymous Search (no account required)
  anonymousSearch: (requirements: {
    location?: string;
    city?: string;
    state?: string;
    use_type?: string;
    goods_type?: string;
    size_sqft?: number;
    timing?: string;
    duration_months?: number;
    max_budget_per_sqft?: number;
    deal_breakers?: string[];
    requirements?: Record<string, unknown>;
  }) =>
    fetchAPI('/api/search', { method: 'POST', body: JSON.stringify(requirements) }),
  getSearchSession: (token: string) =>
    fetchAPI(`/api/search/session/${token}`),
  promoteSession: (sessionToken: string) =>
    fetchAPI('/api/search/promote', { method: 'POST', body: JSON.stringify({ session_token: sessionToken }) }),

  // Health
  health: () => fetchAPI('/health'),
};
