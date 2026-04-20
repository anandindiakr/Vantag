export type Region = 'IN' | 'MY' | 'SG';

export interface PricingTier {
  name: string;
  key: 'starter' | 'growth' | 'pro';
  cameras: number;
  monthlyPrice: number;
  annualPrice: number;  // per month when billed annually
  currency: string;
  symbol: string;
  popular?: boolean;
}

export interface RegionConfig {
  region: Region;
  /** Brand name shown on the site */
  brand: string;
  /** Short brand name for sidebar / mobile header */
  brandShort: string;
  /** Full domain this config is for */
  domains: string[];
  /** ISO 639-1 codes for available languages */
  languages: { code: string; label: string }[];
  /** Default language code */
  defaultLang: string;
  /** ISO 4217 currency code */
  currency: string;
  /** Currency symbol */
  symbol: string;
  /** Country name shown in copy */
  country: string;
  /** Razorpay / payment gateway currency */
  paymentCurrency: string;
  /** Pricing tiers */
  plans: PricingTier[];
}

const REGIONS: Record<Region, RegionConfig> = {
  IN: {
    region: 'IN',
    brand: 'Vantag — Retail Nazar',
    brandShort: 'Retail Nazar',
    domains: ['retailnazar.com', 'retailnazar.in', 'retailnazar.info'],
    languages: [
      { code: 'en', label: 'English' },
      { code: 'hi', label: 'हिंदी' },
      { code: 'ta', label: 'தமிழ்' },
      { code: 'te', label: 'తెలుగు' },
      { code: 'kn', label: 'ಕನ್ನಡ' },
      { code: 'ml', label: 'മലയാളം' },
      { code: 'mr', label: 'मराठी' },
      { code: 'gu', label: 'ગુજરાતી' },
      { code: 'bn', label: 'বাংলা' },
      { code: 'pa', label: 'ਪੰਜਾਬੀ' },
    ],
    defaultLang: 'en',
    currency: 'INR',
    symbol: '₹',
    country: 'India',
    paymentCurrency: 'INR',
    plans: [
      {
        name: 'Starter',
        key: 'starter',
        cameras: 5,
        monthlyPrice: 1999,
        annualPrice: 1666,
        currency: 'INR',
        symbol: '₹',
      },
      {
        name: 'Growth',
        key: 'growth',
        cameras: 15,
        monthlyPrice: 4499,
        annualPrice: 3749,
        currency: 'INR',
        symbol: '₹',
        popular: true,
      },
      {
        name: 'Pro',
        key: 'pro',
        cameras: 30,
        monthlyPrice: 8999,
        annualPrice: 7499,
        currency: 'INR',
        symbol: '₹',
      },
    ],
  },

  MY: {
    region: 'MY',
    brand: 'Vantag — JagaJaga',
    brandShort: 'JagaJaga',
    domains: ['jagajaga.my', 'retailjagajaga.com'],
    languages: [
      { code: 'en', label: 'English' },
      { code: 'ms', label: 'Bahasa Malaysia' },
      { code: 'zh', label: '中文' },
    ],
    defaultLang: 'ms',
    currency: 'MYR',
    symbol: 'RM',
    country: 'Malaysia',
    paymentCurrency: 'MYR',
    plans: [
      {
        name: 'Starter',
        key: 'starter',
        cameras: 5,
        monthlyPrice: 59,
        annualPrice: 49,
        currency: 'MYR',
        symbol: 'RM',
      },
      {
        name: 'Growth',
        key: 'growth',
        cameras: 15,
        monthlyPrice: 149,
        annualPrice: 124,
        currency: 'MYR',
        symbol: 'RM',
        popular: true,
      },
      {
        name: 'Pro',
        key: 'pro',
        cameras: 30,
        monthlyPrice: 299,
        annualPrice: 249,
        currency: 'MYR',
        symbol: 'RM',
      },
    ],
  },

  SG: {
    region: 'SG',
    brand: 'Vantag — Retail Intelligence',
    brandShort: 'Vantag',
    domains: ['retail-vantag.com'],
    languages: [
      { code: 'en', label: 'English' },
      { code: 'zh', label: '中文' },
    ],
    defaultLang: 'en',
    currency: 'SGD',
    symbol: 'S$',
    country: 'Singapore',
    paymentCurrency: 'SGD',
    plans: [
      {
        name: 'Starter',
        key: 'starter',
        cameras: 5,
        monthlyPrice: 39,
        annualPrice: 32,
        currency: 'SGD',
        symbol: 'S$',
      },
      {
        name: 'Growth',
        key: 'growth',
        cameras: 15,
        monthlyPrice: 99,
        annualPrice: 82,
        currency: 'SGD',
        symbol: 'S$',
        popular: true,
      },
      {
        name: 'Pro',
        key: 'pro',
        cameras: 30,
        monthlyPrice: 189,
        annualPrice: 157,
        currency: 'SGD',
        symbol: 'S$',
      },
    ],
  },
};

/** Detect region from hostname. Falls back to SG for localhost / unknown hosts. */
export function detectRegion(): RegionConfig {
  const host = window.location.hostname.toLowerCase();

  if (
    host.includes('retailnazar') ||
    host === 'retailnazar.in' ||
    host === 'retailnazar.info'
  ) {
    return REGIONS.IN;
  }

  if (host.includes('jagajaga') || host.includes('retailjagajaga')) {
    return REGIONS.MY;
  }

  // retail-vantag.com → SG, or localhost (dev default)
  return REGIONS.SG;
}

export { REGIONS };
