// --- WEx Revenue Tuner: Types & Utilities ---

export type Phase = 1 | 2 | 3 | 4 | 5 | 6;

export type ActivityTier = 'storage_only' | 'storage_light_assembly';
export type PricingPath = 'set_rate' | 'commission';

export interface TruthCore {
  address: string;
  sqft: number;
  minRentable: number; // Minimum rentable unit size
  activityTier: ActivityTier;
  hasOffice: boolean;
  weekendAccess: boolean;
  availabilityStart: string; // ISO date string
  minTermMonths: number;
  pricingPath: PricingPath;
  rateAsk: number; // $/sqft/mo
  activationStatus: 'off' | 'on';
  additionalNotes: string; // Free-text from "Tell us more"
}

export interface BuildingData {
  id?: string;
  address: string;
  city?: string;
  state?: string;
  zip?: string;
  building_size_sqft?: number;
  lot_size_acres?: number;
  year_built?: number;
  construction_type?: string;
  zoning?: string;
  primary_image_url?: string;
  image_urls?: string[];
  truth_core?: Record<string, unknown>;
  clear_height_ft?: number;
  dock_doors_receiving?: number;
  dock_doors_shipping?: number;
  drive_in_bays?: number;
  parking_spaces?: number;
  has_office_space?: boolean;
  has_sprinkler?: boolean;
  power_supply?: string;
  nnn_rates?: { nnn_low: number; nnn_high: number; rate_location: string } | null;
}

export interface RevenueEstimate {
  low_rate: number;
  high_rate: number;
  low_monthly: number;
  high_monthly: number;
  low_annual: number;
  high_annual: number;
  rate_location?: string;
}

export interface ContextualMemoryEntry {
  id: string;
  category: string;
  content: string;
  icon: string;
  source: 'activation_wizard' | 'ai_extraction' | 'user_input';
  timestamp: string;
}

// --- Revenue Calculator ---
// Base revenue only: sqft × rate × 12 months (no multipliers)
// Upsell potential (office, activity tier, weekend) shown as soft hints in the UI

export function calculateRevenue(truthCore: TruthCore): number {
  // Annual = sqft × rate × 12 months, rounded to nearest $100
  return Math.ceil((truthCore.sqft * truthCore.rateAsk * 12) / 100) * 100;
}

// --- Regional rate defaults (mirrors backend /api/supplier/estimate) ---
const REGION_RATES: Record<string, [number, number]> = {
  CA: [0.85, 1.10], TX: [0.65, 0.85], AZ: [0.60, 0.80],
  SC: [0.55, 0.75], MD: [0.70, 0.90], GA: [0.65, 0.85],
  MI: [0.60, 0.80], FL: [0.70, 0.90], IL: [0.65, 0.85],
  NY: [0.80, 1.05], NJ: [0.75, 1.00], PA: [0.65, 0.85],
  OH: [0.55, 0.75], WA: [0.75, 0.95], OR: [0.70, 0.90],
};
const DEFAULT_RATES: [number, number] = [0.65, 0.90];

export function getRegionalRates(state?: string): { low: number; high: number; mid: number } {
  const [baseRate] = state ? (REGION_RATES[state] || DEFAULT_RATES) : DEFAULT_RATES;
  // Conservative range derived from the low rate only
  const low = parseFloat((baseRate * 0.80).toFixed(2));
  const high = parseFloat((baseRate * 0.95).toFixed(2));
  const mid = parseFloat((baseRate * 0.85).toFixed(2));
  return { low, high, mid };
}

// --- Default Truth Core ---
export function createDefaultTruthCore(): TruthCore {
  return {
    address: '',
    sqft: 30000,
    minRentable: 2000,
    activityTier: 'storage_only',
    hasOffice: false,
    weekendAccess: false,
    availabilityStart: '',
    minTermMonths: 1,
    pricingPath: 'set_rate',
    rateAsk: 0.88,
    activationStatus: 'off',
    additionalNotes: '',
  };
}

// --- Demo building data fallback ---
export const DEMO_BUILDING: BuildingData = {
  id: 'demo-wh-001',
  address: '123 Industrial Blvd',
  city: 'Napa',
  state: 'CA',
  zip: '94559',
  building_size_sqft: 45000,
  year_built: 2004,
  construction_type: 'Tilt-up concrete',
  zoning: 'Industrial M-1',
  primary_image_url: '',
  image_urls: [],
  clear_height_ft: 28,
  dock_doors_receiving: 4,
  drive_in_bays: 2,
  parking_spaces: 30,
  has_office_space: true,
  has_sprinkler: true,
  power_supply: '3-phase 400A',
};
