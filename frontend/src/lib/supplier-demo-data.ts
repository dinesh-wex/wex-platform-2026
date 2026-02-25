// =============================================================================
// Supplier Dashboard — Centralized Fallback Demo Data
// =============================================================================
// Every API call in the supplier dashboard has a try/catch that falls back to
// this demo data when the backend is unavailable. This keeps the UI fully
// functional for demos, development, and offline testing.
// =============================================================================

import type {
  SupplierProfile,
  Warehouse,
  PortfolioSummary,
  ActionItem,
  AISuggestion,
  Engagement,
  EngagementEvent,
  EngagementAgreement,
  OnboardingStatus,
  PaymentRecord,
  Payment,
  PaymentSummary,
  TeamMember,
  NotificationPrefs,
  PropertyActivity,
  ProfileCompleteness,
} from '@/types/supplier';

// =============================================================================
// 1. Supplier Profile
// =============================================================================

export const demoSupplier: SupplierProfile = {
  id: 'sup-001',
  name: 'Wilson Industrial',
  company: 'Wilson Properties LLC',
  email: 'wilson@demo.com',
  phone: '(410) 555-0173',
  company_id: 'comp-001',
  company_role: 'admin',
};

// =============================================================================
// 2. Warehouses
// =============================================================================

export const demoWarehouses: Warehouse[] = [
  {
    id: 'wh-001',
    name: 'Glen Burnie Distribution Center',
    address: '1221 Wilson Rd',
    city: 'Glen Burnie',
    state: 'MD',
    zip_code: '21061',
    total_sqft: 28000,
    available_sqft: 10080,
    min_sqft: 2000,
    status: 'in_network',
    supplier_rate: 0.71,
    image_url: '/images/warehouse-glen-burnie.jpg',
    rented_sqft: 17920,
    occupancy_pct: 64,
    truth_core: {
      building_sqft: 28000,
      clear_height_ft: 24,
      dock_doors: 6,
      drive_in_bays: 2,
      year_built: 1998,
      construction_type: 'Tilt-Up Concrete',
      building_class: 'B',
      zoning: 'Industrial',
      lot_size_acres: 2.1,
      sprinkler: true,
      power_supply: '3-Phase, 480V',
      parking_spaces: 35,
      available_sqft: 10080,
      min_rentable_sqft: 2000,
      activity_tier: 'active',
      has_office: true,
      weekend_access: false,
      access_24_7: false,
      min_term_months: 3,
      available_from: '2026-02-01',
      operating_hours: {
        monday: '7:00 AM - 6:00 PM',
        tuesday: '7:00 AM - 6:00 PM',
        wednesday: '7:00 AM - 6:00 PM',
        thursday: '7:00 AM - 6:00 PM',
        friday: '7:00 AM - 6:00 PM',
        saturday: 'Closed',
        sunday: 'Closed',
      },
      target_rate_sqft: 0.71,
      food_grade: false,
      fda_registered: false,
      hazmat_certified: false,
      c_tpat: false,
      temperature_controlled: false,
      foreign_trade_zone: false,
    },
  },
  {
    id: 'wh-002',
    name: 'Gardena Logistics Hub',
    address: '15001 S Figueroa St',
    city: 'Gardena',
    state: 'CA',
    zip_code: '90248',
    total_sqft: 46530,
    available_sqft: 46530,
    min_sqft: 5000,
    status: 'in_network',
    supplier_rate: 0.82,
    image_url: undefined,
    rented_sqft: 0,
    occupancy_pct: 0,
    truth_core: {
      building_sqft: 46530,
      clear_height_ft: 30,
      dock_doors: 10,
      drive_in_bays: 3,
      year_built: 2005,
      construction_type: 'Pre-Engineered Metal',
      building_class: 'A',
      zoning: 'Industrial',
      lot_size_acres: 3.8,
      sprinkler: true,
      power_supply: '3-Phase, 480V',
      parking_spaces: 60,
      available_sqft: 46530,
      min_rentable_sqft: 5000,
      activity_tier: 'matching',
      has_office: false,
      weekend_access: true,
      access_24_7: true,
      min_term_months: 3,
      available_from: '2026-01-15',
      operating_hours: {
        monday: '24 Hours',
        tuesday: '24 Hours',
        wednesday: '24 Hours',
        thursday: '24 Hours',
        friday: '24 Hours',
        saturday: '24 Hours',
        sunday: '24 Hours',
      },
      target_rate_sqft: 0.82,
      food_grade: false,
      fda_registered: false,
      hazmat_certified: false,
      c_tpat: false,
      temperature_controlled: false,
      foreign_trade_zone: false,
    },
  },
  {
    id: 'wh-003',
    name: 'Sugar Land Flex Space',
    address: '8900 Hwy 6 S',
    city: 'Sugar Land',
    state: 'TX',
    zip_code: '77478',
    total_sqft: 18500,
    available_sqft: 0,
    min_sqft: 2500,
    status: 'in_network',
    supplier_rate: 0.58,
    image_url: '/images/warehouse-sugar-land.jpg',
    rented_sqft: 18500,
    occupancy_pct: 100,
    truth_core: {
      building_sqft: 18500,
      clear_height_ft: 20,
      dock_doors: 4,
      drive_in_bays: 1,
      year_built: 2012,
      construction_type: 'Tilt-Up Concrete',
      building_class: 'B+',
      zoning: 'Light Industrial',
      lot_size_acres: 1.5,
      sprinkler: true,
      power_supply: 'Single Phase, 240V',
      parking_spaces: 22,
      available_sqft: 0,
      min_rentable_sqft: 2500,
      activity_tier: 'full',
      has_office: true,
      weekend_access: false,
      access_24_7: false,
      min_term_months: 6,
      available_from: '2027-01-01',
      operating_hours: {
        monday: '8:00 AM - 5:00 PM',
        tuesday: '8:00 AM - 5:00 PM',
        wednesday: '8:00 AM - 5:00 PM',
        thursday: '8:00 AM - 5:00 PM',
        friday: '8:00 AM - 5:00 PM',
        saturday: 'Closed',
        sunday: 'Closed',
      },
      target_rate_sqft: 0.58,
      food_grade: false,
      fda_registered: false,
      hazmat_certified: false,
      c_tpat: false,
      temperature_controlled: false,
      foreign_trade_zone: false,
    },
  },
];

// =============================================================================
// 3. Portfolio Summary (calculated from the 3 warehouses)
// =============================================================================

// Glen Burnie: 17,920 rented × $0.71 = $12,723.20/mo
// Gardena:     0 rented × $0.82 = $0/mo
// Sugar Land:  18,500 rented × $0.58 = $10,730.00/mo
// Total projected: $23,453.20/mo
// Total rented: 36,420 sqft
// Total available: 56,610 sqft (10,080 + 46,530 + 0)
// Total capacity: 93,030 sqft
// Weighted avg rate: (17920*0.71 + 18500*0.58) / 36420 ≈ $0.646
// Occupancy: 36420 / 93030 ≈ 39.1%

export const demoPortfolio: PortfolioSummary = {
  total_projected_income: 23453.2,
  avg_rate: 0.65,
  active_capacity_sqft: 93030,
  occupancy_pct: 39.1,
  total_rented_sqft: 36420,
  total_available_sqft: 56610,
  property_count: 3,
};

// =============================================================================
// 4. Action Items
// =============================================================================

export const demoActions: ActionItem[] = [
  {
    id: 'act-001',
    type: 'deal_ping',
    title: 'New Inquiry — 5,000 sqft Storage',
    description:
      'A buyer needs 5,000 sqft of storage space in the Glen Burnie area. Rate: $0.75/sqft, 6 month term. Respond within 24 hours.',
    action_label: 'Review Deal',
    action_url: '/supplier/engagements/eng-1250',
    engagement_id: 'eng-1250',
    property_id: 'wh-001',
    urgency: 'high',
    deadline: '2026-02-24T17:00:00Z',
    created_at: '2026-02-23T09:15:00Z',
  },
  {
    id: 'act-002',
    type: 'tour_confirm',
    title: 'Tour to Confirm — March 5',
    description:
      'A buyer has requested a tour of 1221 Wilson Rd, Glen Burnie on March 5 at 10:00 AM. Please confirm or suggest an alternate time.',
    action_label: 'Confirm Tour',
    action_url: '/supplier/engagements/eng-1198',
    engagement_id: 'eng-1198',
    property_id: 'wh-001',
    urgency: 'high',
    deadline: '2026-03-03T17:00:00Z',
    created_at: '2026-02-22T14:30:00Z',
  },
  {
    id: 'act-003',
    type: 'agreement_sign',
    title: 'Agreement Ready — Engagement #1280',
    description:
      'The lease agreement for Engagement #1280 is ready for your signature. 5,000 sqft storage at Gardena Logistics Hub.',
    action_label: 'Sign Agreement',
    action_url: '/supplier/engagements/eng-1280',
    engagement_id: 'eng-1280',
    property_id: 'wh-002',
    urgency: 'medium',
    deadline: '2026-02-28T23:59:00Z',
    created_at: '2026-02-20T10:00:00Z',
  },
];

// =============================================================================
// 5. AI Suggestions
// =============================================================================

// Suggestions follow tier priority (spec 3.3):
//   Tier 1 — photos, available_sqft, rate, clear_height, dock_doors,
//            activity_tier, available_from  (shown first)
//   Tier 2 — only surfaces once all Tier 1 fields would be complete
//   Certification suggestions are demand-triggered and reference actual
//   buyer activity rather than appearing proactively.

export const demoSuggestions: AISuggestion[] = [
  // ---- Tier 1 suggestions (highest priority — shown first) ----
  {
    id: 'sug-001',
    type: 'photos',
    title: 'Add photos to your Gardena property',
    description:
      'Your Gardena property has no photos. Properties with photos get 2x more tour requests.',
    action_label: 'Upload Photos',
    action_type: 'navigate',
    action_url: '/supplier/properties/wh-002',
    target_property_id: 'wh-002',
    target_tab: 'photos',
    target_field: undefined,
    priority: 1,
    dismissed: false,
  },
  {
    id: 'sug-002',
    type: 'feature',
    title: 'Set your available space',
    description:
      'Buyers search by square footage. Confirm how much space is available so we can match you with tenants.',
    action_label: 'Set Available Space',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'config',
    target_field: 'available_sqft',
    priority: 1,
    dismissed: false,
  },
  {
    id: 'sug-003',
    type: 'rate',
    title: 'Set your rate',
    description:
      'Your rate determines which buyers you match with. Area median is $0.55-$0.95/sqft.',
    action_label: 'Set Rate',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'pricing',
    target_field: 'target_rate_sqft',
    priority: 1,
    dismissed: false,
  },
  {
    id: 'sug-004',
    type: 'feature',
    title: 'Add clear height',
    description:
      'Buyers filter by clear height. Adding this detail helps your property match 30% more searches.',
    action_label: 'Add Clear Height',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'building',
    target_field: 'clear_height_ft',
    priority: 1,
    dismissed: false,
  },
  {
    id: 'sug-005',
    type: 'feature',
    title: 'Add dock door count',
    description:
      'Distribution buyers require dock doors. Confirm your count to match with logistics companies.',
    action_label: 'Add Dock Doors',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'building',
    target_field: 'dock_doors',
    priority: 1,
    dismissed: false,
  },
  {
    id: 'sug-006',
    type: 'availability',
    title: 'Set your activity tier',
    description:
      'Choose whether your property is actively seeking tenants, matching only, paused, or full.',
    action_label: 'Set Activity Tier',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'config',
    target_field: 'activity_tier',
    priority: 1,
    dismissed: false,
  },
  {
    id: 'sug-007',
    type: 'availability',
    title: 'Set available-from date',
    description:
      'Let buyers know when your space becomes available so they can plan their move-in.',
    action_label: 'Set Date',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'config',
    target_field: 'available_from',
    priority: 1,
    dismissed: false,
  },

  // ---- Tier 2 suggestions (shown only when all Tier 1 fields are complete) ----
  {
    id: 'sug-008',
    type: 'feature',
    title: 'Add parking space count',
    description:
      'Some tenants need guaranteed parking. Adding this helps your listing stand out.',
    action_label: 'Add Parking',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'building',
    target_field: 'parking_spaces',
    priority: 2,
    dismissed: false,
  },
  {
    id: 'sug-009',
    type: 'feature',
    title: 'Confirm power supply type',
    description:
      'Manufacturing tenants need to know your power specs. Confirm to unlock those matches.',
    action_label: 'Confirm Power',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'building',
    target_field: 'power_supply',
    priority: 2,
    dismissed: false,
  },
  {
    id: 'sug-010',
    type: 'feature',
    title: 'Set minimum term length',
    description:
      'Specify the shortest lease you accept so buyers see accurate availability.',
    action_label: 'Set Min Term',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'config',
    target_field: 'min_term_months',
    priority: 2,
    dismissed: false,
  },

  // ---- Certification suggestions (demand-triggered, referencing buyer activity) ----
  {
    id: 'sug-011',
    type: 'certification',
    title: 'Buyers are asking: Is this food grade?',
    description:
      'Demand-triggered: 3 active food-storage buyers in your area searched for food-grade facilities this week. Answering unlocks those matches.',
    action_label: 'Answer Now',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'config',
    target_field: 'food_grade',
    priority: 3,
    dismissed: false,
  },
  {
    id: 'sug-012',
    type: 'certification',
    title: 'Buyer question: Temperature controlled?',
    description:
      'Demand-triggered: A pharma logistics buyer shortlisted your property but needs temperature-controlled confirmation.',
    action_label: 'Answer Now',
    action_type: 'edit_field',
    action_url: undefined,
    target_property_id: undefined,
    target_tab: 'config',
    target_field: 'temperature_controlled',
    priority: 3,
    dismissed: false,
  },
];

// =============================================================================
// 6. Engagements (spec-compliant, 24-status lifecycle)
// =============================================================================

// Helper to build a backward-compat engagement object with all required fields
function makeEngagement(e: Partial<Engagement> & Pick<Engagement, 'id' | 'status' | 'sqft'>): Engagement {
  return {
    // New spec fields — defaults
    warehouseId: '',
    buyerNeedId: '',
    supplierId: 'sup-001',
    tier: 'tier_1',
    matchScore: 85,
    matchRank: 1,
    supplierRateSqft: 0,
    buyerRateSqft: 0,
    monthlySupplierPayout: 0,
    monthlyBuyerTotal: 0,
    tourRescheduleCount: 0,
    insuranceUploaded: false,
    companyDocsUploaded: false,
    paymentMethodAdded: false,
    adminNotes: '',
    adminFlagged: false,
    createdAt: '',
    updatedAt: '',
    // Backward-compat defaults
    property_id: '',
    property_address: '',
    buyer_need_id: '',
    use_type: 'storage',
    supplier_rate: 0,
    monthly_payout: 0,
    term_months: 6,
    total_value: 0,
    created_at: '',
    updated_at: '',
    buyer_use_type: 'storage',
    timeline: [],
    ...e,
  } as Engagement;
}

export const demoEngagements: Engagement[] = [
  // ===== 1. ACTION NEEDED: deal_ping_sent — awaiting supplier accept =====
  makeEngagement({
    id: 'eng-1250',
    warehouseId: 'wh-002',
    buyerNeedId: 'bn-512',
    supplierId: 'sup-001',
    status: 'deal_ping_sent',
    tier: 'tier_1',
    path: undefined,
    matchScore: 88,
    matchRank: 2,
    supplierRateSqft: 0.82,
    buyerRateSqft: 0.95,
    monthlySupplierPayout: 6560,
    monthlyBuyerTotal: 7600,
    sqft: 8000,
    dealPingSentAt: '2026-02-23T09:15:00Z',
    dealPingExpiresAt: '2026-02-24T17:00:00Z',
    createdAt: '2026-02-23T09:15:00Z',
    updatedAt: '2026-02-23T09:15:00Z',
    // Backward compat
    property_id: 'wh-002',
    property_address: '15001 S Figueroa St, Gardena, CA 90248',
    property_image_url: undefined,
    buyer_need_id: 'bn-512',
    use_type: 'storage',
    supplier_rate: 0.82,
    monthly_payout: 6560,
    term_months: 3,
    total_value: 19680,
    created_at: '2026-02-23T09:15:00Z',
    updated_at: '2026-02-23T09:15:00Z',
    next_step: 'Review and accept or decline this inquiry',
    buyer_use_type: 'storage',
    buyer_goods_type: 'E-commerce fulfillment',
    warehouse: { id: 'wh-002', name: 'Gardena Logistics Hub', address: '15001 S Figueroa St', city: 'Gardena', state: 'CA', zip_code: '90248' },
    timeline: [
      { id: 'tl-1250-01', type: 'deal_ping_sent', description: 'Inquiry received — 8,000 sqft storage, 3 month term', timestamp: '2026-02-23T09:15:00Z', completed: false },
    ],
  }),

  // ===== 2. ACTION NEEDED: tour_requested — awaiting supplier confirm =====
  makeEngagement({
    id: 'eng-1198',
    warehouseId: 'wh-001',
    buyerNeedId: 'bn-487',
    supplierId: 'sup-001',
    status: 'tour_requested',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 92,
    matchRank: 1,
    supplierRateSqft: 0.71,
    buyerRateSqft: 0.85,
    monthlySupplierPayout: 7100,
    monthlyBuyerTotal: 8500,
    sqft: 10000,
    dealPingSentAt: '2026-02-10T08:00:00Z',
    dealPingRespondedAt: '2026-02-11T10:00:00Z',
    supplierTermsAccepted: true,
    supplierTermsVersion: '2026-02',
    guaranteeSignedAt: '2026-02-15T14:00:00Z',
    guaranteeTermsVersion: '2026-02',
    tourRequestedAt: '2026-02-22T14:30:00Z',
    tourScheduledDate: '2026-03-05',
    tourRescheduleCount: 0,
    createdAt: '2026-02-10T08:00:00Z',
    updatedAt: '2026-02-22T14:30:00Z',
    // Backward compat
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    property_image_url: '/images/warehouse-glen-burnie.jpg',
    buyer_need_id: 'bn-487',
    use_type: 'distribution',
    supplier_rate: 0.71,
    monthly_payout: 7100,
    term_months: 12,
    total_value: 85200,
    created_at: '2026-02-10T08:00:00Z',
    updated_at: '2026-02-22T14:30:00Z',
    next_step: 'Confirm tour for March 5',
    buyer_use_type: 'distribution',
    buyer_goods_type: 'Auto parts',
    tour_date: '2026-03-05',
    tour_time: '10:00 AM',
    tour_confirmed: false,
    warehouse: { id: 'wh-001', name: 'Glen Burnie Distribution Center', address: '1221 Wilson Rd', city: 'Glen Burnie', state: 'MD', zip_code: '21061' },
    timeline: [
      { id: 'tl-1198-01', type: 'deal_ping_sent', description: 'Inquiry received — 10,000 sqft distribution request', timestamp: '2026-02-10T08:00:00Z', completed: true },
      { id: 'tl-1198-02', type: 'deal_ping_accepted', description: 'You accepted the inquiry', timestamp: '2026-02-11T10:00:00Z', completed: true },
      { id: 'tl-1198-03', type: 'guarantee_signed', description: 'Buyer signed anti-circumvention guarantee', timestamp: '2026-02-15T14:00:00Z', completed: true },
      { id: 'tl-1198-04', type: 'tour_requested', description: 'Tour requested for March 5 at 10:00 AM — awaiting confirmation', timestamp: '2026-02-22T14:30:00Z', completed: false },
    ],
  }),

  // ===== 3. ACTIVE: active lease running =====
  makeEngagement({
    id: 'eng-1234',
    warehouseId: 'wh-001',
    buyerNeedId: 'bn-501',
    buyerId: 'buyer-301',
    supplierId: 'sup-001',
    status: 'active',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 95,
    matchRank: 1,
    supplierRateSqft: 0.71,
    buyerRateSqft: 0.85,
    monthlySupplierPayout: 3550,
    monthlyBuyerTotal: 4250,
    sqft: 5000,
    dealPingSentAt: '2026-01-10T09:00:00Z',
    dealPingRespondedAt: '2026-01-10T15:30:00Z',
    supplierTermsAccepted: true,
    supplierTermsVersion: '2026-01',
    buyerEmail: 'ops@chesapeakegoods.com',
    buyerPhone: '(410) 555-9900',
    buyerCompanyName: 'Chesapeake Goods Co.',
    guaranteeSignedAt: '2026-01-12T09:00:00Z',
    guaranteeTermsVersion: '2026-01',
    tourRequestedAt: '2026-01-12T11:00:00Z',
    tourConfirmedAt: '2026-01-20T09:00:00Z',
    tourScheduledDate: '2026-01-22',
    tourCompletedAt: '2026-01-22T11:30:00Z',
    tourOutcome: 'confirmed',
    tourRescheduleCount: 0,
    agreementSentAt: '2026-01-28T10:00:00Z',
    agreementSignedAt: '2026-02-05T16:00:00Z',
    onboardingStartedAt: '2026-02-06T09:00:00Z',
    onboardingCompletedAt: '2026-02-12T16:00:00Z',
    insuranceUploaded: true,
    companyDocsUploaded: true,
    paymentMethodAdded: true,
    leaseStartDate: '2026-02-15',
    leaseEndDate: '2026-08-15',
    createdAt: '2026-01-10T09:00:00Z',
    updatedAt: '2026-02-15T14:00:00Z',
    // Backward compat
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    property_image_url: '/images/warehouse-glen-burnie.jpg',
    buyer_need_id: 'bn-501',
    use_type: 'storage',
    supplier_rate: 0.71,
    monthly_payout: 3550,
    term_months: 6,
    total_value: 21300,
    created_at: '2026-01-10T09:00:00Z',
    updated_at: '2026-02-15T14:00:00Z',
    buyer_company: 'Chesapeake Goods Co.',
    buyer_use_type: 'storage',
    buyer_goods_type: 'Consumer packaged goods',
    tour_date: '2026-01-22',
    tour_time: '10:00 AM',
    tour_confirmed: true,
    warehouse: { id: 'wh-001', name: 'Glen Burnie Distribution Center', address: '1221 Wilson Rd', city: 'Glen Burnie', state: 'MD', zip_code: '21061' },
    timeline: [
      { id: 'tl-1234-01', type: 'deal_ping_sent', description: 'Inquiry received — 5,000 sqft storage request', timestamp: '2026-01-10T09:00:00Z', completed: true },
      { id: 'tl-1234-02', type: 'deal_ping_accepted', description: 'You accepted the inquiry', timestamp: '2026-01-10T15:30:00Z', completed: true },
      { id: 'tl-1234-03', type: 'guarantee_signed', description: 'Buyer signed anti-circumvention guarantee', timestamp: '2026-01-12T09:00:00Z', completed: true },
      { id: 'tl-1234-04', type: 'tour_requested', description: 'Tour requested for Jan 22 at 10:00 AM', timestamp: '2026-01-12T11:00:00Z', completed: true },
      { id: 'tl-1234-05', type: 'tour_confirmed', description: 'Tour confirmed by both parties', timestamp: '2026-01-20T09:00:00Z', completed: true },
      { id: 'tl-1234-06', type: 'tour_completed', description: 'Tour completed — buyer interested', timestamp: '2026-01-22T11:30:00Z', completed: true },
      { id: 'tl-1234-07', type: 'agreement_sent', description: 'Lease agreement generated and sent for review', timestamp: '2026-01-28T10:00:00Z', completed: true },
      { id: 'tl-1234-08', type: 'agreement_signed', description: 'Agreement signed by both parties', timestamp: '2026-02-05T16:00:00Z', completed: true },
      { id: 'tl-1234-09', type: 'onboarding', description: 'Onboarding completed — insurance, docs, payment verified', timestamp: '2026-02-12T16:00:00Z', completed: true },
      { id: 'tl-1234-10', type: 'active', description: 'Lease started — move-in Feb 15', timestamp: '2026-02-15T14:00:00Z', completed: true },
    ],
  }),

  // ===== 4. IN PROGRESS: guarantee_signed (tour path, pre-tour) =====
  makeEngagement({
    id: 'eng-1275',
    warehouseId: 'wh-001',
    buyerNeedId: 'bn-520',
    supplierId: 'sup-001',
    status: 'guarantee_signed',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 90,
    matchRank: 1,
    supplierRateSqft: 0.71,
    buyerRateSqft: 0.88,
    monthlySupplierPayout: 3550,
    monthlyBuyerTotal: 4400,
    sqft: 5000,
    dealPingSentAt: '2026-02-18T10:00:00Z',
    dealPingRespondedAt: '2026-02-18T16:00:00Z',
    supplierTermsAccepted: true,
    supplierTermsVersion: '2026-02',
    guaranteeSignedAt: '2026-02-20T11:00:00Z',
    guaranteeTermsVersion: '2026-02',
    tourRescheduleCount: 0,
    createdAt: '2026-02-18T10:00:00Z',
    updatedAt: '2026-02-20T11:00:00Z',
    // Backward compat
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    property_image_url: '/images/warehouse-glen-burnie.jpg',
    buyer_need_id: 'bn-520',
    use_type: 'storage',
    supplier_rate: 0.71,
    monthly_payout: 3550,
    term_months: 6,
    total_value: 21300,
    created_at: '2026-02-18T10:00:00Z',
    updated_at: '2026-02-20T11:00:00Z',
    next_step: 'Buyer will request a tour or instant book',
    buyer_use_type: 'storage',
    buyer_goods_type: 'Seasonal retail inventory',
    warehouse: { id: 'wh-001', name: 'Glen Burnie Distribution Center', address: '1221 Wilson Rd', city: 'Glen Burnie', state: 'MD', zip_code: '21061' },
    timeline: [
      { id: 'tl-1275-01', type: 'deal_ping_sent', description: 'Inquiry received — 5,000 sqft storage', timestamp: '2026-02-18T10:00:00Z', completed: true },
      { id: 'tl-1275-02', type: 'deal_ping_accepted', description: 'You accepted the inquiry', timestamp: '2026-02-18T16:00:00Z', completed: true },
      { id: 'tl-1275-03', type: 'guarantee_signed', description: 'Buyer signed anti-circumvention guarantee', timestamp: '2026-02-20T11:00:00Z', completed: true },
      { id: 'tl-1275-04', type: 'pending_tour_or_book', description: 'Awaiting buyer to request tour or instant book', timestamp: '2026-02-20T11:00:00Z', completed: false },
    ],
  }),

  // ===== 5. IN PROGRESS: buyer_confirmed (instant book path, post-agreement) =====
  makeEngagement({
    id: 'eng-1280',
    warehouseId: 'wh-002',
    buyerNeedId: 'bn-525',
    buyerId: 'buyer-310',
    supplierId: 'sup-001',
    status: 'buyer_confirmed',
    tier: 'tier_2',
    path: 'instant_book',
    matchScore: 82,
    matchRank: 3,
    supplierRateSqft: 0.82,
    buyerRateSqft: 0.98,
    monthlySupplierPayout: 4100,
    monthlyBuyerTotal: 4900,
    sqft: 5000,
    dealPingSentAt: '2026-02-12T09:00:00Z',
    dealPingRespondedAt: '2026-02-12T14:00:00Z',
    supplierTermsAccepted: true,
    supplierTermsVersion: '2026-02',
    buyerEmail: 'logistics@westcoastgoods.com',
    buyerPhone: '(310) 555-1234',
    buyerCompanyName: 'West Coast Goods LLC',
    guaranteeSignedAt: '2026-02-14T10:00:00Z',
    guaranteeTermsVersion: '2026-02',
    instantBookRequestedAt: '2026-02-16T09:00:00Z',
    instantBookConfirmedAt: '2026-02-16T09:05:00Z',
    tourRescheduleCount: 0,
    createdAt: '2026-02-12T09:00:00Z',
    updatedAt: '2026-02-22T10:00:00Z',
    // Backward compat
    property_id: 'wh-002',
    property_address: '15001 S Figueroa St, Gardena, CA 90248',
    buyer_need_id: 'bn-525',
    use_type: 'storage',
    supplier_rate: 0.82,
    monthly_payout: 4100,
    term_months: 6,
    total_value: 24600,
    created_at: '2026-02-12T09:00:00Z',
    updated_at: '2026-02-22T10:00:00Z',
    next_step: 'Agreement will be sent shortly',
    buyer_company: 'West Coast Goods LLC',
    buyer_use_type: 'storage',
    buyer_goods_type: 'Health & beauty products',
    warehouse: { id: 'wh-002', name: 'Gardena Logistics Hub', address: '15001 S Figueroa St', city: 'Gardena', state: 'CA', zip_code: '90248' },
    timeline: [
      { id: 'tl-1280-01', type: 'deal_ping_sent', description: 'Inquiry received — 5,000 sqft storage', timestamp: '2026-02-12T09:00:00Z', completed: true },
      { id: 'tl-1280-02', type: 'deal_ping_accepted', description: 'You accepted the inquiry', timestamp: '2026-02-12T14:00:00Z', completed: true },
      { id: 'tl-1280-03', type: 'guarantee_signed', description: 'Buyer signed anti-circumvention guarantee', timestamp: '2026-02-14T10:00:00Z', completed: true },
      { id: 'tl-1280-04', type: 'instant_book_requested', description: 'Buyer chose Instant Book', timestamp: '2026-02-16T09:00:00Z', completed: true },
      { id: 'tl-1280-05', type: 'instant_book_confirmed', description: 'Instant Book confirmed', timestamp: '2026-02-16T09:05:00Z', completed: true },
      { id: 'tl-1280-06', type: 'buyer_confirmed', description: 'Buyer confirmed — agreement pending', timestamp: '2026-02-22T10:00:00Z', completed: false },
    ],
  }),

  // ===== 6a. PAST: completed =====
  makeEngagement({
    id: 'eng-1089',
    warehouseId: 'wh-003',
    buyerNeedId: 'bn-410',
    buyerId: 'buyer-220',
    supplierId: 'sup-001',
    status: 'completed',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 97,
    matchRank: 1,
    supplierRateSqft: 0.58,
    buyerRateSqft: 0.72,
    monthlySupplierPayout: 10730,
    monthlyBuyerTotal: 13320,
    sqft: 18500,
    dealPingSentAt: '2025-12-01T10:00:00Z',
    dealPingRespondedAt: '2025-12-02T08:30:00Z',
    supplierTermsAccepted: true,
    supplierTermsVersion: '2025-12',
    buyerEmail: 'ops@gulfcoastlogistics.com',
    buyerPhone: '(281) 555-4567',
    buyerCompanyName: 'Gulf Coast Logistics Inc.',
    guaranteeSignedAt: '2025-12-03T10:00:00Z',
    guaranteeTermsVersion: '2025-12',
    tourRequestedAt: '2025-12-04T14:00:00Z',
    tourConfirmedAt: '2025-12-08T09:00:00Z',
    tourScheduledDate: '2025-12-10',
    tourCompletedAt: '2025-12-10T15:00:00Z',
    tourOutcome: 'confirmed',
    tourRescheduleCount: 0,
    agreementSentAt: '2025-12-15T10:00:00Z',
    agreementSignedAt: '2025-12-20T16:00:00Z',
    onboardingStartedAt: '2025-12-21T09:00:00Z',
    onboardingCompletedAt: '2025-12-28T16:00:00Z',
    insuranceUploaded: true,
    companyDocsUploaded: true,
    paymentMethodAdded: true,
    leaseStartDate: '2026-01-01',
    leaseEndDate: '2026-12-31',
    createdAt: '2025-12-01T10:00:00Z',
    updatedAt: '2026-02-01T00:00:00Z',
    // Backward compat
    property_id: 'wh-003',
    property_address: '8900 Hwy 6 S, Sugar Land, TX 77478',
    property_image_url: '/images/warehouse-sugar-land.jpg',
    buyer_need_id: 'bn-410',
    use_type: 'distribution',
    supplier_rate: 0.58,
    monthly_payout: 10730,
    term_months: 12,
    total_value: 128760,
    created_at: '2025-12-01T10:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    buyer_company: 'Gulf Coast Logistics Inc.',
    buyer_use_type: 'distribution',
    buyer_goods_type: 'Industrial equipment',
    tour_date: '2025-12-10',
    tour_time: '2:00 PM',
    tour_confirmed: true,
    warehouse: { id: 'wh-003', name: 'Sugar Land Flex Space', address: '8900 Hwy 6 S', city: 'Sugar Land', state: 'TX', zip_code: '77478' },
    timeline: [
      { id: 'tl-1089-01', type: 'deal_ping_sent', description: 'Inquiry received — 18,500 sqft distribution', timestamp: '2025-12-01T10:00:00Z', completed: true },
      { id: 'tl-1089-02', type: 'deal_ping_accepted', description: 'You accepted the inquiry', timestamp: '2025-12-02T08:30:00Z', completed: true },
      { id: 'tl-1089-03', type: 'guarantee_signed', description: 'Buyer signed guarantee', timestamp: '2025-12-03T10:00:00Z', completed: true },
      { id: 'tl-1089-04', type: 'tour_requested', description: 'Tour requested for Dec 10 at 2:00 PM', timestamp: '2025-12-04T14:00:00Z', completed: true },
      { id: 'tl-1089-05', type: 'tour_confirmed', description: 'Tour confirmed by both parties', timestamp: '2025-12-08T09:00:00Z', completed: true },
      { id: 'tl-1089-06', type: 'tour_completed', description: 'Tour completed — buyer moving forward', timestamp: '2025-12-10T15:00:00Z', completed: true },
      { id: 'tl-1089-07', type: 'agreement_sent', description: 'Lease agreement generated', timestamp: '2025-12-15T10:00:00Z', completed: true },
      { id: 'tl-1089-08', type: 'agreement_signed', description: 'Agreement signed by both parties', timestamp: '2025-12-20T16:00:00Z', completed: true },
      { id: 'tl-1089-09', type: 'onboarding', description: 'Onboarding completed', timestamp: '2025-12-28T16:00:00Z', completed: true },
      { id: 'tl-1089-10', type: 'active', description: 'Lease started — tenant moved in Jan 1', timestamp: '2026-01-01T00:00:00Z', completed: true },
      { id: 'tl-1089-11', type: 'completed', description: 'Engagement completed — lease fully executed', timestamp: '2026-02-01T00:00:00Z', completed: true },
    ],
  }),

  // ===== 6b. PAST: declined_by_buyer =====
  makeEngagement({
    id: 'eng-1102',
    warehouseId: 'wh-001',
    buyerNeedId: 'bn-430',
    supplierId: 'sup-001',
    status: 'declined_by_buyer',
    tier: 'tier_2',
    matchScore: 68,
    matchRank: 4,
    supplierRateSqft: 0.71,
    buyerRateSqft: 0.50,
    monthlySupplierPayout: 0,
    monthlyBuyerTotal: 0,
    sqft: 8000,
    dealPingSentAt: '2026-01-05T11:00:00Z',
    dealPingRespondedAt: '2026-01-05T16:00:00Z',
    declinedBy: 'buyer',
    declineReason: 'Rate too high for our budget',
    declinedAt: '2026-01-06T09:45:00Z',
    tourRescheduleCount: 0,
    createdAt: '2026-01-05T11:00:00Z',
    updatedAt: '2026-01-06T09:45:00Z',
    // Backward compat
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    property_image_url: '/images/warehouse-glen-burnie.jpg',
    buyer_need_id: 'bn-430',
    use_type: 'storage',
    supplier_rate: 0.71,
    monthly_payout: 0,
    term_months: 6,
    total_value: 0,
    created_at: '2026-01-05T11:00:00Z',
    updated_at: '2026-01-06T09:45:00Z',
    buyer_use_type: 'storage',
    buyer_goods_type: 'Furniture',
    warehouse: { id: 'wh-001', name: 'Glen Burnie Distribution Center', address: '1221 Wilson Rd', city: 'Glen Burnie', state: 'MD', zip_code: '21061' },
    timeline: [
      { id: 'tl-1102-01', type: 'deal_ping_sent', description: 'Inquiry received — 8,000 sqft storage, $0.50/sqft offered', timestamp: '2026-01-05T11:00:00Z', completed: true },
      { id: 'tl-1102-02', type: 'deal_ping_accepted', description: 'You accepted the inquiry', timestamp: '2026-01-05T16:00:00Z', completed: true },
      { id: 'tl-1102-03', type: 'declined_by_buyer', description: 'Buyer declined — Rate too high for their budget', timestamp: '2026-01-06T09:45:00Z', completed: true, metadata: { reason: 'Rate too high for our budget' } },
    ],
  }),
];

// =============================================================================
// 6b. Demo Engagement Events (for timeline API)
// =============================================================================

export const demoEngagementEvents: EngagementEvent[] = [
  { id: 'ev-001', engagementId: 'eng-1250', eventType: 'deal_ping_sent', actor: 'system', fromStatus: undefined, toStatus: 'deal_ping_sent', createdAt: '2026-02-23T09:15:00Z' },
  { id: 'ev-002', engagementId: 'eng-1198', eventType: 'tour_requested', actor: 'buyer', fromStatus: 'guarantee_signed', toStatus: 'tour_requested', createdAt: '2026-02-22T14:30:00Z' },
  { id: 'ev-003', engagementId: 'eng-1234', eventType: 'active', actor: 'system', fromStatus: 'onboarding', toStatus: 'active', createdAt: '2026-02-15T14:00:00Z' },
];

// =============================================================================
// 7. Payments (last 3 months for 2 active engagements)
// =============================================================================

export const demoPayments: Payment[] = [
  // Engagement #1234 — Glen Burnie, $3,550/mo
  {
    id: 'pay-001',
    date: '2026-02-15T00:00:00Z',
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    engagement_id: 'eng-1234',
    type: 'monthly_deposit',
    amount: 3550,
    status: 'deposited',
  },
  {
    id: 'pay-002',
    date: '2026-01-15T00:00:00Z',
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    engagement_id: 'eng-1234',
    type: 'monthly_deposit',
    amount: 3550,
    status: 'deposited',
  },
  {
    id: 'pay-003',
    date: '2025-12-15T00:00:00Z',
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    engagement_id: 'eng-1234',
    type: 'monthly_deposit',
    amount: 3550,
    status: 'deposited',
  },

  // Engagement #1089 — Sugar Land, $10,730/mo
  {
    id: 'pay-004',
    date: '2026-02-15T00:00:00Z',
    property_id: 'wh-003',
    property_address: '8900 Hwy 6 S, Sugar Land, TX 77478',
    engagement_id: 'eng-1089',
    type: 'monthly_deposit',
    amount: 10730,
    status: 'deposited',
  },
  {
    id: 'pay-005',
    date: '2026-01-15T00:00:00Z',
    property_id: 'wh-003',
    property_address: '8900 Hwy 6 S, Sugar Land, TX 77478',
    engagement_id: 'eng-1089',
    type: 'monthly_deposit',
    amount: 10730,
    status: 'deposited',
  },
  {
    id: 'pay-006',
    date: '2025-12-15T00:00:00Z',
    property_id: 'wh-003',
    property_address: '8900 Hwy 6 S, Sugar Land, TX 77478',
    engagement_id: 'eng-1089',
    type: 'monthly_deposit',
    amount: 10730,
    status: 'deposited',
  },
];

// =============================================================================
// 8. Payment Summary
// =============================================================================

// Total earned (6 payments): 3*3550 + 3*10730 = 10650 + 32190 = $42,840
// This month (Feb): 3550 + 10730 = $14,280
// Next deposit: March 15
// Pending: $0 (all deposited)
// Active engagements paying out: 2

export const demoPaymentSummary: PaymentSummary = {
  total_earned: 42840,
  this_month: 14280,
  next_deposit: 14280,
  next_deposit_date: '2026-03-15',
  pending_amount: 0,
  active_engagements: 2,
};

// =============================================================================
// 9. Team Members
// =============================================================================

export const demoTeam: TeamMember[] = [
  {
    id: 'tm-001',
    name: 'John Smith',
    email: 'wilson@demo.com',
    role: 'admin',
    status: 'active',
    joined_at: '2026-01-15T10:00:00Z',
  },
  {
    id: 'tm-002',
    name: 'Sarah Johnson',
    email: 'sarah@company.com',
    role: 'member',
    status: 'invited',
    invited_at: '2026-02-18T14:00:00Z',
  },
];

// =============================================================================
// 10. Notification Preferences
// =============================================================================

export const demoNotificationPrefs: NotificationPrefs = {
  deal_pings_sms: true,
  deal_pings_email: true,
  tour_requests_sms: true,
  tour_requests_email: true,
  agreement_ready_email: true,
  payment_deposited_email: true,
  profile_suggestions_email: true,
  monthly_summary_email: true,
};

// =============================================================================
// 11. Property Activity (Glen Burnie — most recent first)
// =============================================================================

export const demoPropertyActivity: PropertyActivity[] = [
  {
    id: 'pa-001',
    type: 'shown_to_buyers',
    description: 'Your property was shown to 3 buyers searching in Glen Burnie',
    timestamp: '2026-02-23T08:00:00Z',
    metadata: { buyer_count: 3 },
  },
  {
    id: 'pa-002',
    type: 'deal_ping_response',
    description: 'You accepted an inquiry for 5,000 sqft storage',
    timestamp: '2026-02-22T10:15:00Z',
    metadata: { engagement_id: 'eng-1250-gb', sqft: 5000, use_type: 'storage' },
  },
  {
    id: 'pa-003',
    type: 'shown_to_buyers',
    description: 'Your property was shown to 5 buyers — 2 matched, 3 near-misses',
    timestamp: '2026-02-20T08:00:00Z',
    metadata: { buyer_count: 5, matched: 2, near_misses: 3 },
  },
  {
    id: 'pa-004',
    type: 'photo_uploaded',
    description: 'Photo uploaded via mobile — exterior loading dock',
    timestamp: '2026-02-18T13:45:00Z',
    metadata: { photo_type: 'exterior', source: 'mobile' },
  },
  {
    id: 'pa-005',
    type: 'profile_updated',
    description: 'Profile updated: confirmed 3-Phase power supply',
    timestamp: '2026-02-15T11:00:00Z',
    metadata: { field: 'power_supply', value: '3-Phase, 480V' },
  },
  {
    id: 'pa-006',
    type: 'joined_network',
    description: 'Property joined the WEx Network — now visible to buyers',
    timestamp: '2026-02-10T09:00:00Z',
  },
  {
    id: 'pa-007',
    type: 'earncheck_completed',
    description: 'EarnCheck completed — estimated income: $12,700/month at current rate',
    timestamp: '2026-02-08T16:30:00Z',
    metadata: { estimated_monthly_income: 12700 },
  },
];

// =============================================================================
// 12. Profile Completeness (Glen Burnie property)
// =============================================================================

export const demoProfileCompleteness: ProfileCompleteness = {
  total: 72,
  photos: 60,
  building_specs: 90,
  configuration: 80,
  pricing: 100,
  operating_hours: 50,
  certifications: 30,
};

// =============================================================================
// 13. Agreement Demo Data (Inc 2)
// =============================================================================

export const demoAgreement: EngagementAgreement = {
  id: 'agr-001',
  engagementId: 'eng-1234',
  version: 1,
  status: 'fully_signed',
  termsText: `WAREHOUSE SPACE LEASE AGREEMENT

This Warehouse Space Lease Agreement ("Agreement") is entered into through the WEx Platform.

1. PREMISES: 5,000 square feet of warehouse space located at 1221 Wilson Rd, Glen Burnie, MD 21061.

2. TERM: Six (6) months, commencing February 15, 2026 and ending August 15, 2026.

3. RENT: Buyer shall pay $4,250.00 per month ($0.85/sqft). Supplier shall receive $3,550.00 per month ($0.71/sqft). WEx platform fee: $700.00 per month.

4. USE: The premises shall be used for storage of consumer packaged goods only.

5. INSURANCE: Buyer shall maintain commercial general liability insurance with minimum coverage of $1,000,000 per occurrence.

6. ACCESS: Monday through Friday, 7:00 AM to 6:00 PM. No weekend access unless separately arranged.

7. SECURITY DEPOSIT: One month's rent ($4,250.00) due upon signing.

8. TERMINATION: Either party may terminate with 30 days written notice after the minimum term.

9. GOVERNING LAW: This agreement shall be governed by the laws of the State of Maryland.

10. ENTIRE AGREEMENT: This Agreement constitutes the entire agreement between the parties.`,
  buyerRateSqft: 0.85,
  supplierRateSqft: 0.71,
  monthlyBuyerTotal: 4250,
  monthlySupplierPayout: 3550,
  sentAt: '2026-01-28T10:00:00Z',
  buyerSignedAt: '2026-02-01T14:00:00Z',
  supplierSignedAt: '2026-02-05T16:00:00Z',
  expiresAt: '2026-02-28T23:59:59Z',
};

export const demoPendingAgreement: EngagementAgreement = {
  id: 'agr-002',
  engagementId: 'eng-1280',
  version: 1,
  status: 'pending',
  termsText: `WAREHOUSE SPACE LEASE AGREEMENT

This Warehouse Space Lease Agreement ("Agreement") is entered into through the WEx Platform.

1. PREMISES: 5,000 square feet of warehouse space located at 15001 S Figueroa St, Gardena, CA 90248.

2. TERM: Six (6) months, commencing upon completion of onboarding.

3. RENT: Buyer shall pay $4,900.00 per month ($0.98/sqft). Supplier shall receive $4,100.00 per month ($0.82/sqft). WEx platform fee: $800.00 per month.

4. USE: The premises shall be used for storage of health & beauty products only.

5. INSURANCE: Buyer shall maintain commercial general liability insurance with minimum coverage of $1,000,000 per occurrence.

6. ACCESS: 24/7 access included.

7. SECURITY DEPOSIT: One month's rent ($4,900.00) due upon signing.

8. TERMINATION: Either party may terminate with 30 days written notice after the minimum term.

9. GOVERNING LAW: This agreement shall be governed by the laws of the State of California.

10. ENTIRE AGREEMENT: This Agreement constitutes the entire agreement between the parties.`,
  buyerRateSqft: 0.98,
  supplierRateSqft: 0.82,
  monthlyBuyerTotal: 4900,
  monthlySupplierPayout: 4100,
  sentAt: '2026-02-22T10:00:00Z',
  expiresAt: '2026-03-08T23:59:59Z',
};

// =============================================================================
// 14. Onboarding Status Demo Data (Inc 2)
// =============================================================================

export const demoOnboardingComplete: OnboardingStatus = {
  insuranceUploaded: true,
  companyDocsUploaded: true,
  paymentMethodAdded: true,
  completedAt: '2026-02-12T16:00:00Z',
};

export const demoOnboardingPartial: OnboardingStatus = {
  insuranceUploaded: true,
  companyDocsUploaded: false,
  paymentMethodAdded: false,
};

// =============================================================================
// 15. Payment Records (Inc 2 — engagement-level, buyer + supplier view)
// =============================================================================

export const demoPaymentRecords: PaymentRecord[] = [
  // eng-1234 (active) — Feb, Jan, Dec payments
  {
    id: 'pr-001',
    engagementId: 'eng-1234',
    periodStart: '2026-02-15',
    periodEnd: '2026-03-14',
    buyerAmount: 4250,
    supplierAmount: 3550,
    wexAmount: 700,
    buyerStatus: 'paid',
    supplierStatus: 'deposited',
    buyerInvoicedAt: '2026-02-10T00:00:00Z',
    buyerPaidAt: '2026-02-14T00:00:00Z',
    supplierScheduledAt: '2026-02-14T00:00:00Z',
    supplierDepositedAt: '2026-02-15T00:00:00Z',
  },
  {
    id: 'pr-002',
    engagementId: 'eng-1234',
    periodStart: '2026-03-15',
    periodEnd: '2026-04-14',
    buyerAmount: 4250,
    supplierAmount: 3550,
    wexAmount: 700,
    buyerStatus: 'invoiced',
    supplierStatus: 'upcoming',
    buyerInvoicedAt: '2026-03-10T00:00:00Z',
  },
  {
    id: 'pr-003',
    engagementId: 'eng-1234',
    periodStart: '2026-04-15',
    periodEnd: '2026-05-14',
    buyerAmount: 4250,
    supplierAmount: 3550,
    wexAmount: 700,
    buyerStatus: 'upcoming',
    supplierStatus: 'upcoming',
  },
  // eng-1089 (completed) — Jan, Feb payments
  {
    id: 'pr-004',
    engagementId: 'eng-1089',
    periodStart: '2026-01-01',
    periodEnd: '2026-01-31',
    buyerAmount: 13320,
    supplierAmount: 10730,
    wexAmount: 2590,
    buyerStatus: 'paid',
    supplierStatus: 'deposited',
    buyerInvoicedAt: '2025-12-28T00:00:00Z',
    buyerPaidAt: '2025-12-31T00:00:00Z',
    supplierScheduledAt: '2025-12-31T00:00:00Z',
    supplierDepositedAt: '2026-01-01T00:00:00Z',
  },
  {
    id: 'pr-005',
    engagementId: 'eng-1089',
    periodStart: '2026-02-01',
    periodEnd: '2026-02-28',
    buyerAmount: 13320,
    supplierAmount: 10730,
    wexAmount: 2590,
    buyerStatus: 'paid',
    supplierStatus: 'deposited',
    buyerInvoicedAt: '2026-01-28T00:00:00Z',
    buyerPaidAt: '2026-01-31T00:00:00Z',
    supplierScheduledAt: '2026-01-31T00:00:00Z',
    supplierDepositedAt: '2026-02-01T00:00:00Z',
  },
];

// =============================================================================
// 16. Buyer-perspective Engagements (Inc 2)
// =============================================================================

export const demoBuyerEngagements: Engagement[] = [
  // Active search — tour path, tour completed, awaiting buyer decision
  makeEngagement({
    id: 'eng-b-001',
    warehouseId: 'wh-001',
    buyerNeedId: 'bn-601',
    buyerId: 'buyer-400',
    supplierId: 'sup-001',
    status: 'tour_completed',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 91,
    matchRank: 1,
    supplierRateSqft: 0.71,
    buyerRateSqft: 0.85,
    monthlySupplierPayout: 5325,
    monthlyBuyerTotal: 6375,
    sqft: 7500,
    tourCompletedAt: '2026-02-20T15:00:00Z',
    tourOutcome: undefined,
    tourRescheduleCount: 0,
    createdAt: '2026-02-05T10:00:00Z',
    updatedAt: '2026-02-20T15:00:00Z',
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    buyer_need_id: 'bn-601',
    use_type: 'distribution',
    supplier_rate: 0.71,
    monthly_payout: 5325,
    term_months: 12,
    total_value: 76500,
    created_at: '2026-02-05T10:00:00Z',
    updated_at: '2026-02-20T15:00:00Z',
    next_step: 'Confirm or pass after your tour',
    buyer_use_type: 'distribution',
    buyer_goods_type: 'Auto parts',
    warehouse: { id: 'wh-001', name: 'Glen Burnie Distribution Center', address: '1221 Wilson Rd', city: 'Glen Burnie', state: 'MD', zip_code: '21061' },
    timeline: [
      { id: 'tl-b001-01', type: 'deal_ping_sent', description: 'Match found for your search', timestamp: '2026-02-05T10:00:00Z', completed: true },
      { id: 'tl-b001-02', type: 'tour_completed', description: 'Tour completed at Glen Burnie Distribution Center', timestamp: '2026-02-20T15:00:00Z', completed: true },
      { id: 'tl-b001-03', type: 'awaiting_decision', description: 'Please confirm or pass on this property', timestamp: '2026-02-20T15:00:00Z', completed: false },
    ],
  }),
  // In progress — agreement sent, buyer needs to sign
  makeEngagement({
    id: 'eng-b-002',
    warehouseId: 'wh-002',
    buyerNeedId: 'bn-602',
    buyerId: 'buyer-400',
    supplierId: 'sup-001',
    status: 'agreement_sent',
    tier: 'tier_1',
    path: 'instant_book',
    matchScore: 87,
    matchRank: 2,
    supplierRateSqft: 0.82,
    buyerRateSqft: 0.98,
    monthlySupplierPayout: 4100,
    monthlyBuyerTotal: 4900,
    sqft: 5000,
    agreementSentAt: '2026-02-18T10:00:00Z',
    tourRescheduleCount: 0,
    createdAt: '2026-02-01T09:00:00Z',
    updatedAt: '2026-02-18T10:00:00Z',
    property_id: 'wh-002',
    property_address: '15001 S Figueroa St, Gardena, CA 90248',
    buyer_need_id: 'bn-602',
    use_type: 'storage',
    supplier_rate: 0.82,
    monthly_payout: 4100,
    term_months: 6,
    total_value: 24600,
    created_at: '2026-02-01T09:00:00Z',
    updated_at: '2026-02-18T10:00:00Z',
    next_step: 'Review and sign the lease agreement',
    buyer_use_type: 'storage',
    buyer_goods_type: 'Health & beauty products',
    warehouse: { id: 'wh-002', name: 'Gardena Logistics Hub', address: '15001 S Figueroa St', city: 'Gardena', state: 'CA', zip_code: '90248' },
    timeline: [
      { id: 'tl-b002-01', type: 'deal_ping_sent', description: 'Match found for your search', timestamp: '2026-02-01T09:00:00Z', completed: true },
      { id: 'tl-b002-02', type: 'agreement_sent', description: 'Lease agreement ready for your review', timestamp: '2026-02-18T10:00:00Z', completed: false },
    ],
  }),
  // Active lease
  makeEngagement({
    id: 'eng-1234',
    warehouseId: 'wh-001',
    buyerNeedId: 'bn-501',
    buyerId: 'buyer-400',
    supplierId: 'sup-001',
    status: 'active',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 95,
    matchRank: 1,
    supplierRateSqft: 0.71,
    buyerRateSqft: 0.85,
    monthlySupplierPayout: 3550,
    monthlyBuyerTotal: 4250,
    sqft: 5000,
    leaseStartDate: '2026-02-15',
    leaseEndDate: '2026-08-15',
    insuranceUploaded: true,
    companyDocsUploaded: true,
    paymentMethodAdded: true,
    tourRescheduleCount: 0,
    createdAt: '2026-01-10T09:00:00Z',
    updatedAt: '2026-02-15T14:00:00Z',
    property_id: 'wh-001',
    property_address: '1221 Wilson Rd, Glen Burnie, MD 21061',
    buyer_need_id: 'bn-501',
    use_type: 'storage',
    supplier_rate: 0.71,
    monthly_payout: 3550,
    term_months: 6,
    total_value: 25500,
    created_at: '2026-01-10T09:00:00Z',
    updated_at: '2026-02-15T14:00:00Z',
    buyer_company: 'Chesapeake Goods Co.',
    buyer_use_type: 'storage',
    buyer_goods_type: 'Consumer packaged goods',
    warehouse: { id: 'wh-001', name: 'Glen Burnie Distribution Center', address: '1221 Wilson Rd', city: 'Glen Burnie', state: 'MD', zip_code: '21061' },
    timeline: [
      { id: 'tl-1234-01', type: 'active', description: 'Lease active since Feb 15, 2026', timestamp: '2026-02-15T14:00:00Z', completed: true },
    ],
  }),
  // Past — completed
  makeEngagement({
    id: 'eng-b-past',
    warehouseId: 'wh-003',
    buyerNeedId: 'bn-410',
    buyerId: 'buyer-400',
    supplierId: 'sup-001',
    status: 'completed',
    tier: 'tier_1',
    path: 'tour',
    matchScore: 97,
    matchRank: 1,
    supplierRateSqft: 0.58,
    buyerRateSqft: 0.72,
    monthlySupplierPayout: 10730,
    monthlyBuyerTotal: 13320,
    sqft: 18500,
    leaseStartDate: '2025-06-01',
    leaseEndDate: '2025-12-01',
    tourRescheduleCount: 0,
    createdAt: '2025-05-01T10:00:00Z',
    updatedAt: '2025-12-01T00:00:00Z',
    property_id: 'wh-003',
    property_address: '8900 Hwy 6 S, Sugar Land, TX 77478',
    buyer_need_id: 'bn-410',
    use_type: 'distribution',
    supplier_rate: 0.58,
    monthly_payout: 10730,
    term_months: 6,
    total_value: 79920,
    created_at: '2025-05-01T10:00:00Z',
    updated_at: '2025-12-01T00:00:00Z',
    buyer_company: 'Gulf Coast Logistics Inc.',
    buyer_use_type: 'distribution',
    buyer_goods_type: 'Industrial equipment',
    warehouse: { id: 'wh-003', name: 'Sugar Land Flex Space', address: '8900 Hwy 6 S', city: 'Sugar Land', state: 'TX', zip_code: '77478' },
    timeline: [
      { id: 'tl-bpast-01', type: 'completed', description: 'Lease completed', timestamp: '2025-12-01T00:00:00Z', completed: true },
    ],
  }),
];
