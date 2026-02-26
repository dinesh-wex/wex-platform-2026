// =============================================================================
// Supplier Dashboard Types — WEx Platform
// =============================================================================

// -----------------------------------------------------------------------------
// TruthCore — verified building data
// -----------------------------------------------------------------------------

export interface TruthCore {
  building_sqft?: number;
  clear_height_ft?: number;
  dock_doors?: number;
  drive_in_bays?: number;
  year_built?: number;
  construction_type?: string;
  building_class?: string;
  zoning?: string;
  lot_size_acres?: number;
  sprinkler?: boolean;
  power_supply?: string;
  parking_spaces?: number;
  available_sqft?: number;
  min_rentable_sqft?: number;
  activity_tier?: string;
  has_office?: boolean;
  weekend_access?: boolean;
  access_24_7?: boolean;
  min_term_months?: number;
  available_from?: string;
  operating_hours?: Record<string, string>;
  target_rate_sqft?: number;
  // Certifications
  food_grade?: boolean | null;
  fda_registered?: boolean | null;
  hazmat_certified?: boolean | null;
  c_tpat?: boolean | null;
  temperature_controlled?: boolean | null;
  foreign_trade_zone?: boolean | null;
}

// -----------------------------------------------------------------------------
// Warehouse
// -----------------------------------------------------------------------------

export interface Warehouse {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  total_sqft: number;
  available_sqft: number;
  min_sqft: number;
  status: string; // in_network, in_network_paused, onboarding
  activation_status?: string; // on, off (from truth_core)
  supplier_rate: number;
  image_url?: string;
  activation_step?: string;
  truth_core?: TruthCore;
  rented_sqft: number;
  occupancy_pct: number;
}

// -----------------------------------------------------------------------------
// Supplier Profile
// -----------------------------------------------------------------------------

export interface SupplierProfile {
  id: string;
  name: string;
  company: string;
  email: string;
  phone?: string;
  company_id?: string;
  company_role?: 'admin' | 'member';
}

// -----------------------------------------------------------------------------
// Engagements
// -----------------------------------------------------------------------------

export type EngagementStatus =
  | 'deal_ping_sent' | 'deal_ping_accepted' | 'deal_ping_expired' | 'deal_ping_declined'
  | 'matched' | 'buyer_reviewing' | 'buyer_accepted' | 'account_created' | 'guarantee_signed'
  | 'address_revealed' | 'tour_requested' | 'tour_confirmed' | 'tour_rescheduled'
  | 'instant_book_requested' | 'tour_completed' | 'buyer_confirmed' | 'agreement_sent'
  | 'agreement_signed' | 'onboarding' | 'active' | 'completed' | 'declined_by_buyer'
  | 'declined_by_supplier' | 'cancelled' | 'expired';

export type EngagementTier = 'tier_1' | 'tier_2';
export type EngagementPath = 'tour' | 'instant_book';
export type TourOutcome = 'confirmed' | 'passed' | 'adjustment_needed';

export interface Engagement {
  id: string;
  // Core
  warehouseId: string;
  buyerNeedId: string;
  buyerId?: string;
  supplierId: string;
  status: EngagementStatus;
  tier: EngagementTier;
  path?: EngagementPath;
  matchScore: number;
  matchRank: number;
  // Pricing
  supplierRateSqft: number;
  buyerRateSqft: number;
  monthlySupplierPayout: number;
  monthlyBuyerTotal: number;
  sqft: number;
  // Deal ping
  dealPingSentAt?: string;
  dealPingExpiresAt?: string;
  dealPingRespondedAt?: string;
  // Supplier terms
  supplierTermsAccepted?: boolean;
  supplierTermsVersion?: string;
  // Buyer info
  buyerCompanyName?: string;
  // Account creation
  accountCreatedAt?: string;
  // Guarantee
  guaranteeSignedAt?: string;
  guaranteeIpAddress?: string;
  guaranteeTermsVersion?: string;
  // Tour
  tourRequestedAt?: string;
  tourRequestedDate?: string;
  tourRequestedTime?: string;
  tourConfirmedAt?: string;
  tourScheduledDate?: string;
  tourCompletedAt?: string;
  tourRescheduleCount: number;
  tourRescheduledDate?: string;
  tourRescheduledTime?: string;
  tourRescheduledBy?: string;
  tourOutcome?: TourOutcome;
  // Instant book
  instantBookRequestedAt?: string;
  instantBookConfirmedAt?: string;
  // Agreement
  agreementSentAt?: string;
  agreementSignedAt?: string;
  // Onboarding
  onboardingStartedAt?: string;
  onboardingCompletedAt?: string;
  insuranceUploaded: boolean;
  companyDocsUploaded: boolean;
  paymentMethodAdded: boolean;
  // Lease
  termMonths?: number;
  leaseStartDate?: string;
  leaseEndDate?: string;
  // Decline
  declinedBy?: 'buyer' | 'supplier' | 'admin' | 'system';
  declineReason?: string;
  declinedAt?: string;
  // Cancellation
  cancelledBy?: 'buyer' | 'supplier' | 'admin' | 'system';
  cancelReason?: string;
  cancelledAt?: string;
  // Admin
  adminNotes: string;
  adminFlagged: boolean;
  adminFlagReason?: string;
  // Timestamps
  createdAt: string;
  updatedAt: string;

  // --- Backward-compat fields (used by existing pages) ---
  property_id: string;
  property_address: string;
  property_image_url?: string;
  buyer_need_id: string;
  use_type: string;
  supplier_rate: number;
  monthly_payout: number;
  term_months: number;
  total_value: number;
  created_at: string;
  updated_at: string;
  next_step?: string;
  buyer_company?: string;
  buyer_use_type: string;
  buyer_goods_type?: string;
  tour_date?: string;
  tour_time?: string;
  tour_confirmed?: boolean;
  timeline: EngagementTimelineEvent[];
  // Nested warehouse object for display
  warehouse?: {
    id: string;
    name: string;
    address: string;
    city: string;
    state: string;
    zip_code: string;
  };
}

export interface EngagementTimelineEvent {
  id: string;
  type: string;
  description: string;
  timestamp: string;
  completed: boolean;
  metadata?: Record<string, unknown>;
}

export type EngagementEventType = string; // Will be refined later

export interface EngagementEvent {
  id: string;
  engagementId: string;
  eventType: EngagementEventType;
  actor: 'buyer' | 'supplier' | 'admin' | 'system';
  actorId?: string;
  fromStatus?: EngagementStatus;
  toStatus?: EngagementStatus;
  data?: Record<string, unknown>;
  createdAt: string;
}

// -----------------------------------------------------------------------------
// Action Items
// -----------------------------------------------------------------------------

export type ActionType =
  | 'deal_ping'
  | 'dla_outreach'
  | 'tour_confirm'
  | 'agreement_sign'
  | 'post_tour';

export interface ActionItem {
  id: string;
  type: ActionType;
  title: string;
  description: string;
  action_label: string;
  action_url: string;
  engagement_id?: string;
  property_id?: string;
  urgency: 'high' | 'medium' | 'low';
  deadline?: string;
  created_at: string;
}

// -----------------------------------------------------------------------------
// AI Suggestions
// -----------------------------------------------------------------------------

export type SuggestionType =
  | 'rate'
  | 'feature'
  | 'photos'
  | 'certification'
  | 'response_time'
  | 'availability'
  | 'profile';

export interface AISuggestion {
  id: string;
  type: SuggestionType;
  title: string;
  description: string;
  action_label: string;
  action_type: string; // navigate, toggle, confirm
  action_url?: string;
  target_property_id?: string;
  target_field?: string; // maps to InlineEdit field name (e.g., "clear_height_ft", "dock_doors")
  target_tab?: string;   // maps to tab key (e.g., "building", "photos", "config", "pricing")
  priority: number;
  dismissed?: boolean;
}

// -----------------------------------------------------------------------------
// Payments
// -----------------------------------------------------------------------------

export type PaymentStatus = 'deposited' | 'pending' | 'scheduled' | 'failed';
export type PaymentType = 'monthly_deposit' | 'setup_fee' | 'adjustment' | 'refund';

export interface Payment {
  id: string;
  date: string;
  property_id: string;
  property_address: string;
  engagement_id: string;
  type: PaymentType;
  amount: number;
  status: PaymentStatus;
}

export interface PaymentSummary {
  total_earned: number;
  this_month: number;
  next_deposit: number;
  next_deposit_date: string;
  pending_amount: number;
  active_engagements: number;
}

// -----------------------------------------------------------------------------
// Portfolio Summary
// -----------------------------------------------------------------------------

export interface PortfolioSummary {
  total_projected_income: number;
  avg_rate: number;
  active_capacity_sqft: number;
  occupancy_pct: number;
  total_rented_sqft: number;
  total_available_sqft: number;
  property_count: number;
}

// -----------------------------------------------------------------------------
// Team Management
// -----------------------------------------------------------------------------

export type TeamRole = 'admin' | 'member';
export type TeamMemberStatus = 'active' | 'invited' | 'disabled';

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: TeamRole;
  status: TeamMemberStatus;
  joined_at?: string;
  invited_at?: string;
}

// -----------------------------------------------------------------------------
// Notification Preferences
// -----------------------------------------------------------------------------

export interface NotificationPrefs {
  deal_pings_sms: boolean;
  deal_pings_email: boolean;
  tour_requests_sms: boolean;
  tour_requests_email: boolean;
  agreement_ready_email: boolean;
  payment_deposited_email: boolean;
  profile_suggestions_email: boolean;
  monthly_summary_email: boolean;
}

// -----------------------------------------------------------------------------
// Property Activity Timeline
// -----------------------------------------------------------------------------

export type ActivityEventType =
  | 'shown_to_buyers'
  | 'deal_ping_sent'
  | 'deal_ping_response'
  | 'tour_scheduled'
  | 'tour_completed'
  | 'agreement_signed'
  | 'photo_uploaded'
  | 'profile_updated'
  | 'joined_network'
  | 'earncheck_completed'
  | 'near_miss_summary';

export interface PropertyActivity {
  id: string;
  type: ActivityEventType;
  description: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

// -----------------------------------------------------------------------------
// Profile Completeness
// -----------------------------------------------------------------------------

export interface ProfileCompleteness {
  total: number;           // 0-100
  photos: number;          // weight: 25%
  building_specs: number;  // weight: 20%
  configuration: number;   // weight: 20%
  pricing: number;         // weight: 15%
  operating_hours: number; // weight: 10%
  certifications: number;  // weight: 10%
}

// -----------------------------------------------------------------------------
// Decline Reasons
// -----------------------------------------------------------------------------

export const DECLINE_REASONS = [
  'Rate too low',
  'Space not available at that time',
  'Wrong use type for my facility',
  'Term too short',
  'Term too long',
  'Sqft too small to be worth it',
  'Already in discussions with another tenant',
  'Other',
] as const;

export type DeclineReason = typeof DECLINE_REASONS[number];

// -----------------------------------------------------------------------------
// Engagement Agreement (Inc 2)
// -----------------------------------------------------------------------------

export type AgreementStatus = 'pending' | 'buyer_signed' | 'supplier_signed' | 'fully_signed' | 'expired' | 'cancelled';

export interface EngagementAgreement {
  id: string;
  engagementId: string;
  version: number;
  status: AgreementStatus;
  termsText: string;
  buyerRateSqft: number;
  supplierRateSqft?: number;
  monthlyBuyerTotal: number;
  monthlySupplierPayout?: number;
  sentAt: string;
  buyerSignedAt?: string;
  supplierSignedAt?: string;
  expiresAt: string;
}

// -----------------------------------------------------------------------------
// Onboarding Status (Inc 2)
// -----------------------------------------------------------------------------

export interface OnboardingStatus {
  insuranceUploaded: boolean;
  companyDocsUploaded: boolean;
  paymentMethodAdded: boolean;
  completedAt?: string;
}

// -----------------------------------------------------------------------------
// Payment Record (Inc 2 — engagement-level)
// -----------------------------------------------------------------------------

export type BuyerPaymentStatus = 'upcoming' | 'invoiced' | 'paid' | 'overdue';
export type SupplierPaymentStatus = 'upcoming' | 'scheduled' | 'deposited';

export interface PaymentRecord {
  id: string;
  engagementId: string;
  periodStart: string;
  periodEnd: string;
  buyerAmount: number;
  supplierAmount?: number;
  wexAmount?: number;
  buyerStatus: BuyerPaymentStatus;
  supplierStatus: SupplierPaymentStatus;
  buyerInvoicedAt?: string;
  buyerPaidAt?: string;
  supplierScheduledAt?: string;
  supplierDepositedAt?: string;
}
