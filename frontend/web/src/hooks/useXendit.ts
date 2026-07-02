// frontend/web/src/hooks/useXendit.ts
// Xendit invoice-based checkout for PH / SG / MY.
// Flow: backend creates a hosted invoice → we open the invoice_url in the
// same tab. After payment Xendit calls our webhook which activates the tenant.

import { useCallback } from 'react';
import axios from 'axios';

const api = axios.create({ baseURL: '/api' });
api.interceptors.request.use(c => {
  c.headers['Authorization'] = `Bearer ${localStorage.getItem('vantag_token') || ''}`;
  return c;
});

export function useXendit() {
  const openCheckout = useCallback(async (opts: {
    planId: string;
    onSuccess?: () => void;
    onError?: (err: string) => void;
  }) => {
    try {
      const { data } = await api.post('/billing/xendit-order', { plan_id: opts.planId });
      const invoiceUrl: string = data.invoice_url;
      if (!invoiceUrl) throw new Error('No invoice URL returned from server');

      // Xendit's hosted checkout page — open in same tab so the user returns
      // to the app after payment. Xendit redirects to success_redirect_url
      // which we set in xendit_service.py (the /dashboard route).
      window.location.href = invoiceUrl;

      // onSuccess is called optimistically; actual confirmation comes via webhook
      opts.onSuccess?.();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Could not initiate payment';
      opts.onError?.(msg);
    }
  }, []);

  return { openCheckout };
}
