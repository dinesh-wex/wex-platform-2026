// --- WEx Smoke Test Analytics ---
// Lightweight event tracker for measuring supplier funnel metrics.
// Logs to localStorage for dev visibility and POST to backend for persistence.

import { fetchAPI } from './api';

export type SmokeTestEvent =
  | 'address_entered'
  | 'estimate_viewed'
  | 'configurator_started'
  | 'configurator_completed'
  | 'selected_pricing_model'
  | 'email_submitted'
  | 'lead_verified'
  | 'supplier_joined';

interface EventProperties {
  [key: string]: string | number | boolean | null | undefined;
}

// Generate or retrieve a persistent session ID
function getSessionId(): string {
  const key = 'wex_smoke_session_id';
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem(key, id);
  }
  return id;
}

// Detect test mode from URL (?test=1) and persist in sessionStorage
export function isTestSession(): boolean {
  const key = 'wex_is_test';
  try {
    if (typeof window !== 'undefined' && window.location.search.includes('test=1')) {
      sessionStorage.setItem(key, '1');
      return true;
    }
    return sessionStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

export function trackEvent(event: SmokeTestEvent, properties: EventProperties = {}) {
  const sessionId = getSessionId();
  const isTest = isTestSession();
  const payload = {
    event,
    properties: { ...properties, timestamp: new Date().toISOString() },
    session_id: sessionId,
    is_test: isTest,
  };

  // 1. Log to localStorage for dev visibility
  const storageKey = 'wex_smoke_events';
  try {
    const existing = JSON.parse(localStorage.getItem(storageKey) || '[]');
    existing.push(payload);
    localStorage.setItem(storageKey, JSON.stringify(existing));
  } catch {
    // localStorage full or unavailable — skip
  }

  // 2. POST to backend (fire-and-forget)
  fetchAPI('/api/supplier/track', {
    method: 'POST',
    body: JSON.stringify(payload),
  }).catch(() => {
    // Backend unavailable — event is still in localStorage
  });
}
