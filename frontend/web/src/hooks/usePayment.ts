// frontend/web/src/hooks/usePayment.ts
// Unified payment hook — routes to Razorpay (India) or Xendit (PH/SG/MY)
// based on the current region's paymentGateway setting.

import { useCallback } from 'react';
import axios from 'axios';
import { detectRegion } from '../config/regions';
import { useRazorpay, type RazorpayResponse } from './useRazorpay';
import { useXendit } from './useXendit';

const api = axios.create({ baseURL: '/api' });
api.interceptors.request.use(c => {
  c.headers['Authorization'] = `Bearer ${localStorage.getItem('vantag_token') || ''}`;
  return c;
});

export function usePayment() {
  const region = detectRegion();
  const { openCheckout: openRazorpay } = useRazorpay();
  const { openCheckout: openXendit } = useXendit();

  const pay = useCallback(async (opts: {
    planId: string;
    description?: string;
    prefill?: { name?: string; email?: string; phone?: string };
    onSuccess: () => void;
    onDismiss?: () => void;
    onError?: (msg: string) => void;
  }) => {
    if (region.paymentGateway === 'razorpay') {
      try {
        const { data: order } = await api.post('/billing/order', { plan_id: opts.planId });
        await openRazorpay({
          orderId: order.id,
          amount: order.amount,
          currency: order.currency,
          description: opts.description ?? `Vantag ${opts.planId} Plan`,
          prefill: opts.prefill,
          onSuccess: async (resp: RazorpayResponse) => {
            try {
              await api.post('/billing/verify', {
                razorpay_order_id: resp.razorpay_order_id,
                razorpay_payment_id: resp.razorpay_payment_id,
                razorpay_signature: resp.razorpay_signature,
              });
              opts.onSuccess();
            } catch {
              opts.onError?.('Payment verification failed. Please contact support.');
            }
          },
          onDismiss: opts.onDismiss,
        });
      } catch (err: any) {
        opts.onError?.(err?.response?.data?.detail || 'Could not initiate payment');
      }
    } else {
      // Xendit — opens hosted invoice page; tab redirects away
      await openXendit({
        planId: opts.planId,
        onSuccess: opts.onSuccess,
        onError: opts.onError,
      });
    }
  }, [region.paymentGateway, openRazorpay, openXendit]);

  return { pay, gateway: region.paymentGateway };
}
