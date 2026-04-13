import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Store, CreditCard, Camera, Smartphone, CheckCircle, ChevronRight, ChevronLeft, Loader2, Wifi, AlertCircle, Zap } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useRazorpay } from '../../hooks/useRazorpay';

// ── helpers ───────────────────────────────────────────────────────────────
const token = () => localStorage.getItem('vantag_token') || '';
const api = axios.create({ baseURL: '/api' });
api.interceptors.request.use(c => { c.headers['Authorization'] = `Bearer ${token()}`; return c; });

// ── types ─────────────────────────────────────────────────────────────────
interface CameraEntry {
  ip: string;
  name: string;
  location: string;
  rtsp_url: string;
  brand: string;
  probeStatus: 'idle' | 'probing' | 'found' | 'error';
  thumbnail?: string;
  diagnostics?: string;
}

// ── Step indicator ────────────────────────────────────────────────────────
const STEPS = [
  { icon: Store, label: 'Shop Details' },
  { icon: CreditCard, label: 'Plan' },
  { icon: CreditCard, label: 'Payment' },
  { icon: Camera, label: 'Cameras' },
  { icon: Smartphone, label: 'Install Agent' },
];

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-10 w-full max-w-lg mx-auto">
      {STEPS.map((s, i) => (
        <React.Fragment key={i}>
          <div className={`flex flex-col items-center gap-1.5 ${i < current ? 'text-violet-400' : i === current ? 'text-white' : 'text-white/20'}`}>
            <div className={`w-9 h-9 rounded-full flex items-center justify-center border-2 transition-all
              ${i < current ? 'bg-violet-600 border-violet-600' : i === current ? 'bg-white/5 border-violet-500' : 'bg-transparent border-white/10'}`}>
              {i < current ? <CheckCircle className="w-4 h-4" /> : <s.icon className="w-4 h-4" />}
            </div>
            <span className="text-xs whitespace-nowrap hidden sm:block">{s.label}</span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={`h-px flex-1 mx-1 transition-all ${i < current ? 'bg-violet-600' : 'bg-white/10'}`} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ── PLAN DATA ─────────────────────────────────────────────────────────────
const PLANS = [
  { id: 'starter', name: 'Starter', cameras: '2–5', price: { IN: '₹2,999', SG: 'S$49', MY: 'RM 149' }, features: ['AI Detection Suite', 'Real-time Dashboard', 'One-Tap Door Lock', 'Email Alerts', '7-day history'] },
  { id: 'growth', name: 'Growth', cameras: '6–15', price: { IN: '₹5,999', SG: 'S$99', MY: 'RM 299' }, highlight: true, features: ['Everything in Starter', 'Face Recognition', 'Heatmap Analytics', 'Queue Detection', 'Priority Support'] },
  { id: 'enterprise', name: 'Enterprise', cameras: '16–30', price: { IN: '₹11,999', SG: 'S$199', MY: 'RM 599' }, features: ['Everything in Growth', 'POS Integration', 'Multi-location', 'API Access', 'Unlimited history'] },
];

// ── Main Onboarding Component ─────────────────────────────────────────────
export default function Onboarding() {
  const nav = useNavigate();
  const { openCheckout } = useRazorpay();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [payLoading, setPayLoading] = useState(false);
  const [country, setCountry] = useState('IN');
  const [selectedPlan, setSelectedPlan] = useState('starter');
  const [agentData, setAgentData] = useState<any>(null);
  const [cameras, setCameras] = useState<CameraEntry[]>([{ ip: '', name: '', location: '', rtsp_url: '', brand: '', probeStatus: 'idle' }]);
  const [shopForm, setShopForm] = useState({ shop_name: '', address: '', city: '', language: 'en', phone: '' });

  useEffect(() => {
    // Load saved step from server
    api.get('/onboarding/status').then(({ data }) => {
      setStep(Math.min(data.onboarding_step || 1, 5));
      setCountry(data.country || 'IN');
    }).catch(() => {});
  }, []);

  // ── Step handlers ─────────────────────────────────────────────────────
  const submitStep1 = async () => {
    setLoading(true);
    try {
      await api.post('/onboarding/step/1', { ...shopForm, country });
      setStep(2);
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Error'); }
    finally { setLoading(false); }
  };

  const submitStep2 = async () => {
    setLoading(true);
    try {
      await api.post('/onboarding/step/2', { plan_id: selectedPlan });
      setStep(3);
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Error'); }
    finally { setLoading(false); }
  };

  const submitStep3 = async () => {
    setLoading(true);
    try {
      // Start 14-day free trial, no payment required now
      await api.post('/onboarding/step/3', {});
      setStep(4);
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Error'); }
    finally { setLoading(false); }
  };

  const submitStep3PayNow = async () => {
    setPayLoading(true);
    try {
      // 1. Create Razorpay order
      const { data: order } = await api.post('/billing/order', { plan_id: selectedPlan });
      const userData = JSON.parse(atob((localStorage.getItem('vantag_token') || '').split('.')[1] || 'e30='));

      // 2. Open Razorpay checkout
      await openCheckout({
        orderId: order.id,
        amount: order.amount,
        currency: order.currency,
        description: `Vantag ${selectedPlan.charAt(0).toUpperCase() + selectedPlan.slice(1)} Plan`,
        prefill: { email: userData.email },
        onSuccess: async (resp) => {
          try {
            // 3. Verify payment signature on backend
            await api.post('/billing/verify', {
              razorpay_order_id: resp.razorpay_order_id,
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
            });
            // 4. Advance onboarding
            await api.post('/onboarding/step/3', { paid: true });
            toast.success('Payment successful! Welcome to Vantag.');
            setStep(4);
          } catch {
            toast.error('Payment verification failed. Please contact support.');
          } finally {
            setPayLoading(false);
          }
        },
        onDismiss: () => {
          setPayLoading(false);
          toast('Payment cancelled. You can pay later from your dashboard.', { icon: 'ℹ️' });
        },
      });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Could not initiate payment');
      setPayLoading(false);
    }
  };

  const submitStep4 = async () => {
    const filled = cameras.filter(c => c.ip.trim());
    if (!filled.length) { toast.error('Add at least one camera'); return; }
    setLoading(true);
    try {
      await api.post('/onboarding/step/4', { cameras: filled.map(c => ({ ip: c.ip, name: c.name || undefined, location: c.location || undefined, rtsp_url: c.rtsp_url || undefined, brand: c.brand || undefined })) });
      setStep(5);
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Error'); }
    finally { setLoading(false); }
  };

  const submitStep5 = async () => {
    setLoading(true);
    try {
      const { data } = await api.post('/onboarding/step/5', { device_type: 'android' });
      setAgentData(data);
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Error'); }
    finally { setLoading(false); }
  };

  // ── Camera AI probe ────────────────────────────────────────────────────
  const probeCamera = async (idx: number) => {
    const cam = cameras[idx];
    if (!cam.ip.trim()) { toast.error('Enter an IP address first'); return; }
    setCameras(cs => cs.map((c, i) => i === idx ? { ...c, probeStatus: 'probing' } : c));
    try {
      const { data } = await api.post('/camera/probe', { ip: cam.ip });
      if (data.success) {
        setCameras(cs => cs.map((c, i) => i === idx ? {
          ...c, rtsp_url: data.rtsp_url, brand: data.brand, probeStatus: 'found', thumbnail: data.thumbnail_b64,
        } : c));
        toast.success(`Camera found! Brand: ${data.brand}`);
      } else {
        setCameras(cs => cs.map((c, i) => i === idx ? { ...c, probeStatus: 'error', diagnostics: data.diagnostics } : c));
      }
    } catch {
      setCameras(cs => cs.map((c, i) => i === idx ? { ...c, probeStatus: 'error', diagnostics: 'Connection failed. Please check the IP address.' } : c));
    }
  };

  const updateCamera = (idx: number, field: keyof CameraEntry, value: string) => {
    setCameras(cs => cs.map((c, i) => i === idx ? { ...c, [field]: value, probeStatus: field === 'ip' ? 'idle' : c.probeStatus } : c));
  };
  const addCamera = () => setCameras(cs => [...cs, { ip: '', name: '', location: '', rtsp_url: '', brand: '', probeStatus: 'idle' }]);
  const removeCamera = (idx: number) => setCameras(cs => cs.filter((_, i) => i !== idx));

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex flex-col items-center justify-start pt-16 px-4">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(99,102,241,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(99,102,241,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />

      {/* Logo */}
      <div className="flex items-center gap-2 mb-10">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
          <Shield className="w-4 h-4" />
        </div>
        <span className="text-lg font-bold">Vantag Setup</span>
      </div>

      <StepBar current={step - 1} />

      <div className="relative w-full max-w-2xl">
        <AnimatePresence mode="wait">
          {/* ── STEP 1: Shop Details ── */}
          {step === 1 && (
            <motion.div key="s1" initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} className="bg-white/3 border border-white/8 rounded-2xl p-8">
              <h2 className="text-2xl font-bold mb-1">Tell us about your shop</h2>
              <p className="text-white/40 text-sm mb-8">This helps us personalise Vantag for your business.</p>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">Shop Name *</label>
                  <input required value={shopForm.shop_name} onChange={e => setShopForm(f => ({...f, shop_name: e.target.value}))}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                    placeholder="My Grocery Store" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-white/60 block mb-1.5">Country *</label>
                    <select value={country} onChange={e => setCountry(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors">
                      <option value="IN" className="bg-gray-900">🇮🇳 India</option>
                      <option value="SG" className="bg-gray-900">🇸🇬 Singapore</option>
                      <option value="MY" className="bg-gray-900">🇲🇾 Malaysia</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-sm text-white/60 block mb-1.5">City</label>
                    <input value={shopForm.city} onChange={e => setShopForm(f => ({...f, city: e.target.value}))}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                      placeholder="Mumbai" />
                  </div>
                </div>
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">Full Address</label>
                  <input value={shopForm.address} onChange={e => setShopForm(f => ({...f, address: e.target.value}))}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                    placeholder="123 Market Street" />
                </div>
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">Phone Number</label>
                  <input type="tel" value={shopForm.phone} onChange={e => setShopForm(f => ({...f, phone: e.target.value}))}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors"
                    placeholder="+91 98765 43210" />
                </div>
                <div>
                  <label className="text-sm text-white/60 block mb-1.5">Dashboard Language</label>
                  <select value={shopForm.language} onChange={e => setShopForm(f => ({...f, language: e.target.value}))}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-violet-500/50 transition-colors">
                    <option value="en" className="bg-gray-900">English</option>
                    <option value="hi" className="bg-gray-900">हिंदी (Hindi)</option>
                    <option value="ms" className="bg-gray-900">Bahasa Malaysia</option>
                    <option value="zh" className="bg-gray-900">中文 (Chinese)</option>
                  </select>
                </div>
              </div>
              <button onClick={submitStep1} disabled={loading || !shopForm.shop_name}
                className="w-full mt-8 py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><span>Continue</span><ChevronRight className="w-4 h-4" /></>}
              </button>
            </motion.div>
          )}

          {/* ── STEP 2: Plan Selection ── */}
          {step === 2 && (
            <motion.div key="s2" initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} className="bg-white/3 border border-white/8 rounded-2xl p-8">
              <h2 className="text-2xl font-bold mb-1">Choose your plan</h2>
              <p className="text-white/40 text-sm mb-8">Start with a 14-day free trial. Cancel anytime.</p>
              <div className="space-y-3 mb-8">
                {PLANS.map(plan => {
                  const price = plan.price[country as keyof typeof plan.price] || plan.price.IN;
                  return (
                    <div key={plan.id} onClick={() => setSelectedPlan(plan.id)}
                      className={`p-5 rounded-xl border cursor-pointer transition-all ${selectedPlan === plan.id ? 'border-violet-500 bg-violet-500/10' : 'border-white/10 hover:border-white/20'}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${selectedPlan === plan.id ? 'border-violet-500' : 'border-white/30'}`}>
                            {selectedPlan === plan.id && <div className="w-2 h-2 rounded-full bg-violet-500" />}
                          </div>
                          <span className="font-semibold">{plan.name}</span>
                          {(plan as any).highlight && <span className="px-2 py-0.5 bg-violet-600 rounded-full text-xs font-medium">Popular</span>}
                        </div>
                        <div className="text-right">
                          <div className="font-bold">{price}<span className="text-white/40 font-normal text-sm">/mo</span></div>
                          <div className="text-xs text-white/40">{plan.cameras} cameras</div>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-0.5 ml-7">
                        {plan.features.slice(0, 3).map(f => <span key={f} className="text-xs text-white/40">{f}</span>)}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex gap-3">
                <button onClick={() => setStep(1)} className="flex-1 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl font-medium flex items-center justify-center gap-2 transition-all">
                  <ChevronLeft className="w-4 h-4" /> Back
                </button>
                <button onClick={submitStep2} disabled={loading}
                  className="flex-[2] py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><span>Continue</span><ChevronRight className="w-4 h-4" /></>}
                </button>
              </div>
            </motion.div>
          )}

          {/* ── STEP 3: Payment ── */}
          {step === 3 && (
            <motion.div key="s3" initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} className="bg-white/3 border border-white/8 rounded-2xl p-8 text-center">
              <div className="w-16 h-16 rounded-2xl bg-violet-600/20 flex items-center justify-center mx-auto mb-6">
                <CreditCard className="w-8 h-8 text-violet-400" />
              </div>
              <h2 className="text-2xl font-bold mb-2">Start Your Free Trial</h2>
              <p className="text-white/40 text-sm mb-8">14 days free. No payment needed now.<br />You'll be reminded before your trial ends.</p>
              <div className="bg-white/5 rounded-xl p-4 mb-8 text-left space-y-2">
                {['14-day full access — no restrictions', 'No credit card required to start', 'Cancel anytime from your dashboard', 'Razorpay payment when trial ends'].map(f => (
                  <div key={f} className="flex items-center gap-2 text-sm text-white/70">
                    <CheckCircle className="w-4 h-4 text-violet-400 flex-shrink-0" />
                    {f}
                  </div>
                ))}
              </div>

              {/* Pay Now option */}
              <button onClick={submitStep3PayNow} disabled={payLoading || loading}
                className="w-full mb-3 py-3.5 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all text-emerald-400">
                {payLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {payLoading ? 'Opening payment...' : 'Pay Now & Activate Immediately'}
              </button>

              <div className="flex gap-3">
                <button onClick={() => setStep(2)} className="flex-1 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl font-medium flex items-center justify-center gap-2 transition-all">
                  <ChevronLeft className="w-4 h-4" /> Back
                </button>
                <button onClick={submitStep3} disabled={loading || payLoading}
                  className="flex-[2] py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><span>Start Free Trial</span><ChevronRight className="w-4 h-4" /></>}
                </button>
              </div>
            </motion.div>
          )}

          {/* ── STEP 4: Camera Setup ── */}
          {step === 4 && (
            <motion.div key="s4" initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} className="bg-white/3 border border-white/8 rounded-2xl p-8">
              <h2 className="text-2xl font-bold mb-1">Set Up Your Cameras</h2>
              <p className="text-white/40 text-sm mb-8">Enter each camera's IP. We'll auto-detect the brand and stream URL.</p>
              <div className="space-y-6 mb-6">
                {cameras.map((cam, idx) => (
                  <div key={idx} className="p-5 bg-white/3 border border-white/8 rounded-xl space-y-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-white/70">Camera {idx + 1}</span>
                      {cameras.length > 1 && (
                        <button onClick={() => removeCamera(idx)} className="text-xs text-red-400 hover:text-red-300">Remove</button>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <input value={cam.ip} onChange={e => updateCamera(idx, 'ip', e.target.value)}
                        className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-violet-500/50 transition-colors"
                        placeholder="192.168.1.100" />
                      <button onClick={() => probeCamera(idx)} disabled={cam.probeStatus === 'probing'}
                        className="px-4 py-2.5 bg-violet-600/80 hover:bg-violet-600 disabled:opacity-50 rounded-xl text-sm font-medium flex items-center gap-2 transition-all whitespace-nowrap">
                        {cam.probeStatus === 'probing' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wifi className="w-4 h-4" />}
                        {cam.probeStatus === 'probing' ? 'Detecting...' : 'Auto Detect'}
                      </button>
                    </div>
                    {cam.probeStatus === 'found' && (
                      <div className="flex items-center gap-3 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl">
                        <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                        <div className="text-sm">
                          <span className="text-emerald-400 font-medium">Camera found!</span>
                          <span className="text-white/50 ml-2">Brand: {cam.brand}</span>
                          {cam.rtsp_url && <div className="text-white/30 text-xs mt-0.5 font-mono truncate">{cam.rtsp_url}</div>}
                        </div>
                        {cam.thumbnail && <img src={`data:image/jpeg;base64,${cam.thumbnail}`} className="w-16 h-10 object-cover rounded-lg ml-auto flex-shrink-0" alt="preview" />}
                      </div>
                    )}
                    {cam.probeStatus === 'error' && (
                      <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
                        <div className="flex items-start gap-2">
                          <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                          <p className="text-sm text-white/60">{cam.diagnostics}</p>
                        </div>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                      <input value={cam.name} onChange={e => updateCamera(idx, 'name', e.target.value)}
                        className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500/50"
                        placeholder="Camera name (e.g. Entrance)" />
                      <input value={cam.location} onChange={e => updateCamera(idx, 'location', e.target.value)}
                        className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500/50"
                        placeholder="Location (e.g. Zone A)" />
                    </div>
                  </div>
                ))}
              </div>
              <button onClick={addCamera} className="w-full py-2.5 border border-dashed border-white/20 hover:border-violet-500/40 rounded-xl text-sm text-white/40 hover:text-white/70 transition-all mb-6">
                + Add Another Camera
              </button>
              <div className="flex gap-3">
                <button onClick={() => setStep(3)} className="flex-1 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl font-medium flex items-center justify-center gap-2 transition-all">
                  <ChevronLeft className="w-4 h-4" /> Back
                </button>
                <button onClick={submitStep4} disabled={loading}
                  className="flex-[2] py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><span>Save & Continue</span><ChevronRight className="w-4 h-4" /></>}
                </button>
              </div>
            </motion.div>
          )}

          {/* ── STEP 5: Install Agent ── */}
          {step === 5 && !agentData && (
            <motion.div key="s5" initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} className="bg-white/3 border border-white/8 rounded-2xl p-8">
              <h2 className="text-2xl font-bold mb-1">Install the Edge Agent</h2>
              <p className="text-white/40 text-sm mb-8">The Edge Agent runs on your device and connects your cameras to Vantag.</p>
              <div className="space-y-4 mb-8">
                {[
                  { icon: '📱', title: 'Android Phone or Tablet', desc: 'Best for 2–5 cameras. Uses your existing device.', type: 'android' },
                  { icon: '💻', title: 'Windows PC', desc: 'Best for 5–30 cameras. Install on your shop PC.', type: 'windows' },
                  { icon: '📦', title: 'Vantag Edge Box', desc: 'Plug-and-play device. Just connect power + ethernet.', type: 'edge_box' },
                ].map(opt => (
                  <div key={opt.type} className="p-4 bg-white/3 border border-white/8 rounded-xl flex items-start gap-4">
                    <span className="text-2xl">{opt.icon}</span>
                    <div>
                      <div className="font-medium">{opt.title}</div>
                      <div className="text-sm text-white/40 mt-0.5">{opt.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-3">
                <button onClick={() => setStep(4)} className="flex-1 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl font-medium flex items-center justify-center gap-2 transition-all">
                  <ChevronLeft className="w-4 h-4" /> Back
                </button>
                <button onClick={submitStep5} disabled={loading}
                  className="flex-[2] py-3.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><span>Generate Install Code</span><ChevronRight className="w-4 h-4" /></>}
                </button>
              </div>
            </motion.div>
          )}

          {/* ── STEP 5b: QR Code ── */}
          {step === 5 && agentData && (
            <motion.div key="s5b" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-white/3 border border-white/8 rounded-2xl p-8 text-center">
              <div className="w-16 h-16 rounded-2xl bg-emerald-600/20 flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-8 h-8 text-emerald-400" />
              </div>
              <h2 className="text-2xl font-bold mb-2">You're almost live!</h2>
              <p className="text-white/40 text-sm mb-8">Scan this QR code with your Android phone to connect it to Vantag.</p>

              {/* QR placeholder — in production use qrcode.react */}
              <div className="w-48 h-48 bg-white rounded-2xl flex items-center justify-center mx-auto mb-6">
                <div className="text-gray-800 text-xs text-center p-4 font-mono break-all">{agentData.api_key?.slice(0, 40)}</div>
              </div>

              <div className="text-xs text-white/30 font-mono mb-8 bg-white/5 rounded-lg px-4 py-2 break-all">{agentData.api_key}</div>

              <div className="flex gap-3 mb-6">
                <a href={agentData.download_links?.android} target="_blank" rel="noreferrer"
                  className="flex-1 py-3 bg-emerald-600/80 hover:bg-emerald-600 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all">
                  📱 Download Android App
                </a>
                <a href={agentData.download_links?.windows} target="_blank" rel="noreferrer"
                  className="flex-1 py-3 bg-white/8 hover:bg-white/12 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all">
                  💻 Windows Agent
                </a>
              </div>

              <button onClick={() => nav('/dashboard')}
                className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all">
                Go to Dashboard <ChevronRight className="w-4 h-4" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
