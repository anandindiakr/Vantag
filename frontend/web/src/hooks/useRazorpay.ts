// frontend/web/src/hooks/useRazorpay.ts
// Loads Razorpay checkout.js once and exposes an openCheckout helper.

import { useCallback, useEffect, useRef } from 'react';

declare global {
  interface Window {
    Razorpay: new (opts: RazorpayOptions) => RazorpayInstance;
  }
}

interface RazorpayOptions {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  image?: string;
  prefill?: { name?: string; email?: string; contact?: string };
  theme?: { color?: string };
  handler: (response: RazorpayResponse) => void;
  modal?: { ondismiss?: () => void };
}

interface RazorpayInstance {
  open(): void;
}

export interface RazorpayResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

const RAZORPAY_SCRIPT = 'https://checkout.razorpay.com/v1/checkout.js';
const RAZORPAY_KEY    = import.meta.env.VITE_RAZORPAY_KEY_ID || 'rzp_test_placeholder';

function loadScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${RAZORPAY_SCRIPT}"]`)) {
      resolve();
      return;
    }
    const s = document.createElement('script');
    s.src = RAZORPAY_SCRIPT;
    s.onload  = () => resolve();
    s.onerror = () => reject(new Error('Failed to load Razorpay SDK'));
    document.head.appendChild(s);
  });
}

export function useRazorpay() {
  const loaded = useRef(false);

  useEffect(() => {
    loadScript()
      .then(() => { loaded.current = true; })
      .catch(console.warn);
  }, []);

  const openCheckout = useCallback(async (opts: {
    orderId: string;
    amount: number;          // in smallest currency unit (paise / cents)
    currency: string;
    description: string;
    prefill?: { name?: string; email?: string; phone?: string };
    onSuccess: (resp: RazorpayResponse) => void;
    onDismiss?: () => void;
  }) => {
    if (!loaded.current) await loadScript();

    const rzp = new window.Razorpay({
      key:         RAZORPAY_KEY,
      order_id:    opts.orderId,
      amount:      opts.amount,
      currency:    opts.currency,
      name:        'Vantag',
      description: opts.description,
      image:       '/vantag-icon.svg',
      prefill: {
        name:    opts.prefill?.name,
        email:   opts.prefill?.email,
        contact: opts.prefill?.phone,
      },
      theme:   { color: '#7c3aed' },
      handler: opts.onSuccess,
      modal:   { ondismiss: opts.onDismiss },
    });
    rzp.open();
  }, []);

  return { openCheckout };
}
