import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Shield, Loader2 } from 'lucide-react';
import { useVantagStore } from '../../store/useVantagStore';

// Hidden URL gate — only accessible via:
//   /sales-demo?key=vntg-sales-2026
// Not linked from anywhere on the public site. Share this URL only with the sales team.
const SALES_DEMO_KEY = 'vntg-sales-2026';
const DEMO_EMAIL = 'sales-demo@retail-vantag.com';
const DEMO_PASSWORD = 'VantagSales@2026';

export default function SalesDemo() {
  const nav = useNavigate();
  const setIsSuperAdmin = useVantagStore((s) => s.setIsSuperAdmin);
  const [status, setStatus] = useState<'checking' | 'logging-in' | 'denied' | 'error'>('checking');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const key = params.get('key');

    if (key !== SALES_DEMO_KEY) {
      setStatus('denied');
      return;
    }

    setStatus('logging-in');
    (async () => {
      try {
        const { data } = await axios.post('/api/auth/login', {
          email: DEMO_EMAIL,
          password: DEMO_PASSWORD,
        });
        localStorage.setItem('vantag_token', data.access_token);
        localStorage.setItem(
          'vantag_tenant',
          JSON.stringify({
            id: data.tenant_id,
            name: data.name,
            plan: data.plan_id,
            step: data.onboarding_step,
          })
        );
        if (data.is_super_admin) {
          localStorage.setItem('vantag_is_super_admin', 'true');
          setIsSuperAdmin(true);
        } else {
          localStorage.removeItem('vantag_is_super_admin');
          setIsSuperAdmin(false);
        }
        // Skip onboarding for the demo account — go straight to dashboard
        nav('/dashboard', { replace: true });
      } catch (err: any) {
        setStatus('error');
        setErrorMsg(err?.response?.data?.detail || 'Demo login failed');
      }
    })();
  }, [nav, setIsSuperAdmin]);

  // Generic 404 for invalid/missing key — no hint that a demo exists
  if (status === 'denied') {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4">
        <div className="text-center">
          <h1 className="text-6xl font-bold text-white/20 mb-4">404</h1>
          <p className="text-white/40">Page not found</p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4">
        <div className="bg-white/3 border border-white/8 rounded-2xl p-8 max-w-md text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <Shield className="w-6 h-6 text-red-400" />
          </div>
          <h1 className="text-xl font-bold mb-2">Demo unavailable</h1>
          <p className="text-white/50 text-sm mb-1">{errorMsg}</p>
          <p className="text-white/30 text-xs mt-4">
            Contact support@retail-vantag.com if this persists.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-4">
      <div className="text-center">
        <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
          <Shield className="w-6 h-6" />
        </div>
        <div className="flex items-center justify-center gap-2 text-white/60">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Preparing your demo…</span>
        </div>
      </div>
    </div>
  );
}
