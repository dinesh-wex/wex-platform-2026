// --- WEx Flow Copy Configuration ---
// Toggle between smoke test and production copy via NEXT_PUBLIC_FLOW_MODE env var.
// Default: 'smoke_test' (for market validation phase)
// Set to 'production' to restore original activation flow.

export type FlowMode = 'smoke_test' | 'production';

export const FLOW_MODE: FlowMode =
  (process.env.NEXT_PUBLIC_FLOW_MODE as FlowMode) || 'smoke_test';

export const isSmokeTest = FLOW_MODE === 'smoke_test';

// --- Copy Definitions ---

interface Phase1Copy {
  eyebrow: string;
  headline: string;
  headlineBreak: string; // second line of headline
  placeholder: string;
  subtext: string;
  loginLink: string;
}

interface Phase3Copy {
  eyebrow: string;
  revenueLabel: string;
  capacitySubtext: (sqft: string) => string;
  primaryCta: string;
  secondaryCta: string;
}

interface Phase4Copy {
  headline: string;
  subtext: string;
  capacityCardTitle: string;
  capacityCardSubtext: string;
  sentencePrefix: string;
  sentenceSuffix: string;
  nextButton: string;
}

interface Phase5Copy {
  title: string;
  subtext: string;
  optionA: {
    badge: string;
    title: string;
    desc: string;
    checklist: string[];
  };
  optionB: {
    title: string;
    desc: string;
  };
  rateTitle: string;
  rateSubtext: string;
  cta: (path: 'set_rate' | 'commission') => string;
}

interface Phase6Copy {
  statusBadge: string;
  revenueLabel: string;
  rateLockText: ((rate: string) => string) | null;
  emailPrompt: string | null;
  emailPlaceholder: string;
  button: string;
  buttonLoading: string;
  buttonDisabled: string;
  legal: string;
  successTitle: string;
  successSubtitle: string;
  successLink: string | null;
  successLinkText: string | null;
}

interface HeaderCopy {
  showNav: boolean;
  showLogin: boolean;
  logoPath: string;
}

interface FooterCopy {
  copyright: string;
  privacyUrl: string;
  termsUrl: string;
  privacyLabel: string;
  termsLabel: string;
}

export interface FlowCopyConfig {
  phase1: Phase1Copy;
  phase3: Phase3Copy;
  phase4: Phase4Copy;
  phase5: Phase5Copy;
  phase6: Phase6Copy;
  header: HeaderCopy;
  footer: FooterCopy;
}

// ─── PRODUCTION COPY (Original flow) ─────────────────────────────────────────

const productionCopy: FlowCopyConfig = {
  phase1: {
    eyebrow: '',
    headline: 'What is your empty',
    headlineBreak: 'space worth?',
    placeholder: 'Enter warehouse address...',
    subtext: 'Get an instant revenue estimate — no sign-up required',
    loginLink: 'Returning Supplier? Log in',
  },
  phase3: {
    eyebrow: '',
    revenueLabel: 'Estimated New Revenue',
    capacitySubtext: (sqft) => `From renting out ${sqft} sqft of idle capacity.`,
    primaryCta: 'Customize & Increase Value',
    secondaryCta: 'Not my building? Search again',
  },
  phase4: {
    headline: 'Let\u2019s define your offer.',
    subtext: 'WEx breaks your space into flexible units to maximize revenue. What are your boundaries?',
    capacityCardTitle: 'How flexible is your space?',
    capacityCardSubtext: 'Drag the knobs to set your total available space and minimum divisible unit.',
    sentencePrefix: 'I have',
    sentenceSuffix: 'sqft available, divisible down to',
    nextButton: 'Next: Finalize Pricing',
  },
  phase5: {
    title: 'Choose your pricing model',
    subtext: 'How do you want to earn from your space?',
    optionA: {
      badge: 'RECOMMENDED',
      title: 'Automated Income',
      desc: 'We find the tenant. We handle the billing. You get paid automatically.',
      checklist: [
        'Your locked-in rate per sqft',
        'WEx finds and places tenants',
        'Hands-off — we handle everything',
      ],
    },
    optionB: {
      title: 'Manual Mode',
      desc: 'Negotiate every deal. 15% service fee applies.',
    },
    rateTitle: 'Set your rate',
    rateSubtext: '',
    cta: (path) => (path === 'set_rate' ? 'Lock In Rate' : 'Confirm Pricing'),
  },
  phase6: {
    statusBadge: 'Pending Activation',
    revenueLabel: 'Projected Annual Income',
    rateLockText: (rate) => `$${rate}/sqft Rate Locked via Warehouse Exchange`,
    emailPrompt: null,
    emailPlaceholder: 'Enter email to claim asset...',
    button: 'Sign & Activate',
    buttonLoading: 'Activating...',
    buttonDisabled: 'Enter email to unlock',
    legal:
      'By clicking, you accept the WEx Capacity Agreement and grant programmatic matching rights.',
    successTitle: 'System Active',
    successSubtitle: 'Matching tenants to your criteria...',
    successLink: '/supplier',
    successLinkText: 'Go to Dashboard \u2192',
  },
  header: {
    showNav: true,
    showLogin: true,
    logoPath: '/wex-logo-black.png',
  },
  footer: {
    copyright: '\u00A9 2026 Warehouse Exchange Inc.',
    privacyUrl: 'https://warehouseexchange.com/resources/privacy-policy',
    termsUrl: 'https://warehouseexchange.com/resources/terms-of-services',
    privacyLabel: 'Privacy Policy',
    termsLabel: 'Terms of Service',
  },
};

// ─── SMOKE TEST COPY (Market validation flow) ────────────────────────────────

const smokeTestCopy: FlowCopyConfig = {
  phase1: {
    eyebrow: 'EARNCHECK\u2122',
    headline: 'See what your empty',
    headlineBreak: 'space is worth.',
    placeholder: 'Enter warehouse address...',
    subtext:
      'Warehouse Exchange is analyzing capacity in your area. Check your building\'s potential.',
    loginLink: '',
  },
  phase3: {
    eyebrow: 'EARNCHECK ESTIMATE',
    revenueLabel: 'POTENTIAL EXTRA REVENUE',
    capacitySubtext: () =>
      'We found high demand for warehouse space in your area. See what your under-utilized space could earn.',
    primaryCta: 'Calculate Earnings from Unused Space',
    secondaryCta: 'Not my building? Search again',
  },
  phase4: {
    headline: 'How much space is under-utilized in your building?',
    subtext: 'Drag the slider to see how your potential income grows.',
    capacityCardTitle: 'How much space is under-utilized in your building?',
    capacityCardSubtext: 'Drag the slider to see how your potential income grows.',
    sentencePrefix: 'I could potentially monetize',
    sentenceSuffix: 'sqft...',
    nextButton: 'Get My Additional Income',
  },
  phase5: {
    title: 'Start earning additional income from your unused space.',
    subtext: 'How do you want to get paid?',
    optionA: {
      badge: 'RECOMMENDED',
      title: 'Automated Payout',
      desc: 'Set your desired rate.\nWe fill the space.\nYou get the check without the hassle.',
      checklist: [],
    },
    optionB: {
      title: 'Manual Control',
      desc: 'You negotiate every deal. You handle the tours. Income varies.',
    },
    rateTitle: 'Set Your Target Rate',
    rateSubtext: 'How much do you want to earn per sqft?',
    cta: () => 'Continue',
  },
  phase6: {
    statusBadge: 'PENDING REPORT',
    revenueLabel: 'SEE YOUR INCOME PROJECTION',
    rateLockText: null,
    emailPrompt:
      'Enter your email to save your official EarnCheck report.\nSee what tenants would pay for your idle space.',
    emailPlaceholder: 'name@company.com',
    button: 'Email Me My EarnCheck Report',
    buttonLoading: 'Sending...',
    buttonDisabled: 'Email Me My EarnCheck Report',
    legal:
      'By clicking, you agree to receive your EarnCheck report and market updates from Warehouse Exchange.',
    successTitle: 'EarnCheck Report Sent',
    successSubtitle: '', // dynamic — built in component with revenue figure
    successLink: null,
    successLinkText: null,
  },
  header: {
    showNav: false,
    showLogin: false,
    logoPath: '/wex-logo-black.png',
  },
  footer: {
    copyright: '\u00A9 2026 Warehouse Exchange Inc.',
    privacyUrl: 'https://warehouseexchange.com/resources/privacy-policy',
    termsUrl: 'https://warehouseexchange.com/resources/terms-of-services',
    privacyLabel: 'Privacy Policy',
    termsLabel: 'Terms of Service',
  },
};

// ─── EXPORT ACTIVE COPY ──────────────────────────────────────────────────────

const COPY_MAP: Record<FlowMode, FlowCopyConfig> = {
  production: productionCopy,
  smoke_test: smokeTestCopy,
};

export const copy: FlowCopyConfig = COPY_MAP[FLOW_MODE];
