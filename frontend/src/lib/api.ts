import { getToken, removeToken, setToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchAPI(path: string, options?: RequestInit & { noAuth?: boolean }) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> || {}),
  };

  if (!options?.noAuth) {
    const token = getToken();
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    removeToken();
    throw new Error("Unauthorized");
  }

  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchAPIWithSignal(url: string, signal?: AbortSignal) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  const token = getToken();
  if (token) {
    headers["Authorization"] = "Bearer " + token;
  }

  const res = await fetch(`${API_BASE}${url}`, { headers, signal });

  if (res.status === 401) {
    removeToken();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `API error: ${res.status}`);
  }
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

export function storeAuthToken(token: string) {
  setToken(token);
}

// ---------------------------------------------------------------------------
// Existing API object
// ---------------------------------------------------------------------------

export const api = {
  // Auth (engagement flow)
  register: (body: { email: string; password: string; name: string; role: string; company?: string; phone?: string; engagement_id?: string }) =>
    fetchAPI('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  login: (body: { email: string; password: string }) =>
    fetchAPI('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Supplier endpoints
  supplierLogin: (email: string) =>
    fetchAPI(`/api/supplier/login`, { method: 'POST', body: JSON.stringify({ email }) }),
  warehouseLookup: (address: string, sessionId?: string, isTest?: boolean, signal?: AbortSignal) => {
    let url = `/api/supplier/warehouse/lookup?address=${encodeURIComponent(address)}`;
    if (sessionId) url += `&session_id=${encodeURIComponent(sessionId)}`;
    if (isTest) url += `&is_test=true`;
    return fetchAPIWithSignal(url, signal);
  },
  getWarehouses: (params?: { status?: string; owner_email?: string; company_id?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.company_id) searchParams.set('company_id', params.company_id);
    else if (params?.owner_email) searchParams.set('owner_email', params.owner_email);
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
  activateWarehouseAnon: (id: string, data: any) =>
    fetchAPI(`/api/supplier/warehouse/${id}/activate`, {
      method: 'POST',
      body: JSON.stringify(data),
      noAuth: true,
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
  signGuarantee: (engagementId: string) =>
    fetchAPI(`/api/engagements/${engagementId}/guarantee/sign`, {
      method: 'POST',
      body: JSON.stringify({ accepted: true }),
    }),
  scheduleTour: (engagementId: string, data: { preferred_date: string; preferred_time: string; notes?: string }) =>
    fetchAPI(`/api/engagements/${engagementId}/tour/request`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  recordTourOutcome: (engagementId: string, data: { outcome: string; reason?: string }) =>
    fetchAPI(`/api/engagements/${engagementId}/tour/outcome`, {
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
  extractIntent: (data: { text: string }) =>
    fetchAPI('/api/search/extract', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // ---------------------------------------------------------------------------
  // Engagement Lifecycle — Inc 2 (Agreement, Onboarding, Payments)
  // ---------------------------------------------------------------------------
  submitTourOutcome: (id: string, outcome: 'confirmed' | 'passed', reason?: string) =>
    fetchAPI(`/api/engagements/${id}/tour/outcome`, {
      method: 'POST',
      body: JSON.stringify({ outcome, reason }),
    }),
  getAgreement: (id: string) =>
    fetchAPI(`/api/engagements/${id}/agreement`),
  signAgreement: (id: string, role: 'buyer' | 'supplier') =>
    fetchAPI(`/api/engagements/${id}/agreement/sign`, {
      method: 'POST',
      body: JSON.stringify({ role }),
    }),
  getOnboardingStatus: (id: string) =>
    fetchAPI(`/api/engagements/${id}/onboarding`),
  uploadInsurance: (id: string) =>
    fetchAPI(`/api/engagements/${id}/onboarding/insurance`, { method: 'POST' }),
  uploadCompanyDocs: (id: string) =>
    fetchAPI(`/api/engagements/${id}/onboarding/company-docs`, { method: 'POST' }),
  submitPaymentMethod: (id: string) =>
    fetchAPI(`/api/engagements/${id}/onboarding/payment`, { method: 'POST' }),
  getEngagementPayments: (id: string) =>
    fetchAPI(`/api/engagements/${id}/payments`),
  getBuyerPayments: () =>
    fetchAPI('/api/buyer/payments'),

  // Health
  health: () => fetchAPI('/health'),

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Portfolio
  // ---------------------------------------------------------------------------
  getPortfolio: () => fetchAPI('/api/supplier/portfolio'),
  getActions: () => fetchAPI('/api/supplier/actions'),
  getSuggestions: () => fetchAPI('/api/supplier/suggestions'),

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Properties
  // ---------------------------------------------------------------------------
  getProperties: () => fetchAPI('/api/supplier/properties'),
  getProperty: (id: string) => fetchAPI(`/api/supplier/properties/${id}`),
  getPropertySuggestions: (id: string) => fetchAPI(`/api/supplier/properties/${id}/suggestions`),
  respondToSuggestion: (propertyId: string, data: { suggestion_id: string; response: string }) =>
    fetchAPI(`/api/supplier/properties/${propertyId}/suggestion-response`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateSpecs: (id: string, data: Record<string, unknown>) =>
    fetchAPI(`/api/supplier/properties/${id}/specs`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  updateConfig: (id: string, data: Record<string, unknown>) =>
    fetchAPI(`/api/supplier/properties/${id}/config`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  updatePricing: (id: string, data: { rate: number }) =>
    fetchAPI(`/api/supplier/properties/${id}/pricing`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getUploadToken: (id: string) =>
    fetchAPI(`/api/supplier/properties/${id}/upload-token`, { method: 'POST' }),
  getPropertyPhotos: (id: string) => fetchAPI(`/api/supplier/properties/${id}/photos`),
  deletePropertyPhoto: (propertyId: string, photoId: string) =>
    fetchAPI(`/api/supplier/properties/${propertyId}/photos/${photoId}`, { method: 'DELETE' }),
  reorderPropertyPhotos: (propertyId: string, order: string[]) =>
    fetchAPI(`/api/supplier/properties/${propertyId}/photos/reorder`, {
      method: 'PATCH',
      body: JSON.stringify({ order }),
    }),
  setPropertyPrimaryPhoto: (propertyId: string, photoId: string) =>
    fetchAPI(`/api/supplier/properties/${propertyId}/photos/${photoId}/primary`, {
      method: 'PATCH',
    }),
  getPropertyActivity: (id: string) => fetchAPI(`/api/supplier/properties/${id}/activity`),

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Photo Upload (tokenized, no auth)
  // ---------------------------------------------------------------------------
  verifyUploadToken: (propertyId: string, token: string) =>
    fetch(`${API_BASE}/api/upload/${propertyId}/${token}/verify`).then(r => r.json()),
  uploadPropertyPhotos: (propertyId: string, token: string, formData: FormData) =>
    fetch(`${API_BASE}/api/upload/${propertyId}/${token}/photos`, {
      method: 'POST',
      body: formData,
    }).then(r => r.json()),

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Engagements (legacy)
  // ---------------------------------------------------------------------------
  getEngagements: (status?: string) =>
    fetchAPI(`/api/supplier/engagements${status ? `?status=${status}` : ''}`),
  getEngagement: (id: string) => fetchAPI(`/api/supplier/engagements/${id}`),
  respondToEngagement: (id: string, data: { action: string; reason?: string }) =>
    fetchAPI(`/api/supplier/engagements/${id}/respond`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  confirmEngagementTour: (id: string, data: { confirmed: boolean; proposed_date?: string; proposed_time?: string }) =>
    fetchAPI(`/api/supplier/engagements/${id}/tour/confirm`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // ---------------------------------------------------------------------------
  // Engagement Lifecycle API (spec-compliant)
  // ---------------------------------------------------------------------------
  getEngagementTimeline: (id: string) =>
    fetchAPI(`/api/engagements/${id}/timeline`),
  acceptDealPing: (id: string, terms?: { supplierTermsAccepted: boolean; supplierTermsVersion: string }) =>
    fetchAPI(`/api/engagements/${id}/deal-ping/accept`, {
      method: 'POST',
      body: JSON.stringify(terms ?? {}),
    }),
  declineDealPing: (id: string, reason?: string) =>
    fetchAPI(`/api/engagements/${id}/deal-ping/decline`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  linkBuyer: (engagementId: string) =>
    fetchAPI(`/api/engagements/${engagementId}/link-buyer`, {
      method: 'POST',
    }),
  signEngagementGuarantee: (id: string) =>
    fetchAPI(`/api/engagements/${id}/guarantee/sign`, {
      method: 'POST',
      body: JSON.stringify({ accepted: true }),
    }),
  getEngagementProperty: (id: string) =>
    fetchAPI(`/api/engagements/${id}/property`),
  requestTour: (id: string, preferredDate?: string) =>
    fetchAPI(`/api/engagements/${id}/tour/request`, {
      method: 'POST',
      body: JSON.stringify({ preferred_date: preferredDate }),
    }),
  confirmEngagementTourV2: (id: string, scheduledDate: string) =>
    fetchAPI(`/api/engagements/${id}/tour/confirm`, {
      method: 'POST',
      body: JSON.stringify({ scheduled_date: scheduledDate }),
    }),
  rescheduleEngagementTour: (id: string, newDate: string, reason: string) =>
    fetchAPI(`/api/engagements/${id}/tour/reschedule`, {
      method: 'POST',
      body: JSON.stringify({ new_date: newDate, reason }),
    }),
  confirmInstantBook: (id: string) =>
    fetchAPI(`/api/engagements/${id}/instant-book/confirm`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  declineEngagement: (id: string, reason: string) =>
    fetchAPI(`/api/engagements/${id}/decline`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  // ---------------------------------------------------------------------------
  // Engagement Lifecycle — Inc 3 (Q&A, Admin)
  // ---------------------------------------------------------------------------
  getQuestions: (engagementId: string) =>
    fetchAPI(`/api/engagements/${engagementId}/qa`),
  submitQuestion: (engagementId: string, questionText: string) =>
    fetchAPI(`/api/engagements/${engagementId}/qa`, {
      method: 'POST',
      body: JSON.stringify({ question_text: questionText }),
    }),
  answerQuestion: (engagementId: string, questionId: string, answerText: string) =>
    fetchAPI(`/api/engagements/${engagementId}/qa/${questionId}/answer`, {
      method: 'POST',
      body: JSON.stringify({ answer_text: answerText }),
    }),
  getPropertyKnowledge: (warehouseId: string) =>
    fetchAPI(`/api/properties/${warehouseId}/knowledge`),

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Payments
  // ---------------------------------------------------------------------------
  getPayments: (params?: { from?: string; to?: string; property_id?: string; status?: string; page?: number }) => {
    const sp = new URLSearchParams();
    if (params?.from) sp.set('from', params.from);
    if (params?.to) sp.set('to', params.to);
    if (params?.property_id) sp.set('property_id', params.property_id);
    if (params?.status) sp.set('status', params.status);
    if (params?.page) sp.set('page', String(params.page));
    const qs = sp.toString();
    return fetchAPI(`/api/supplier/payments${qs ? `?${qs}` : ''}`);
  },
  getPaymentsSummary: () => fetchAPI('/api/supplier/payments/summary'),
  exportPayments: (format: 'csv' | 'pdf', from?: string, to?: string) => {
    const sp = new URLSearchParams({ format });
    if (from) sp.set('from', from);
    if (to) sp.set('to', to);
    return fetchAPI(`/api/supplier/payments/export?${sp.toString()}`);
  },

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Account
  // ---------------------------------------------------------------------------
  getAccount: () => fetchAPI('/api/supplier/account'),
  updateAccount: (data: { name?: string; company?: string; phone?: string; email?: string }) =>
    fetchAPI('/api/supplier/account', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  changePassword: (data: { current_password: string; new_password: string }) =>
    fetchAPI('/api/supplier/account/password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getNotificationPrefs: () => fetchAPI('/api/supplier/account/notifications'),
  updateNotificationPrefs: (data: Record<string, boolean>) =>
    fetchAPI('/api/supplier/account/notifications', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // ---------------------------------------------------------------------------
  // Supplier Dashboard — Team
  // ---------------------------------------------------------------------------
  getTeam: () => fetchAPI('/api/supplier/team'),
  inviteTeamMember: (data: { email: string; role: string }) =>
    fetchAPI('/api/supplier/team/invite', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  removeTeamMember: (userId: string) =>
    fetchAPI(`/api/supplier/team/${userId}`, { method: 'DELETE' }),
  updateTeamMember: (userId: string, data: { role: string }) =>
    fetchAPI(`/api/supplier/team/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};
