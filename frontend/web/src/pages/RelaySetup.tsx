import { useEffect, useState } from 'react';
import { Lock, Wifi, Cpu, Usb, Cable, FlaskConical, Download, Save, Loader2, CheckCircle2, ArrowLeft, ArrowRight } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { api } from '../hooks/useApi';

interface RelayType {
  type: string;
  label: string;
  needs: string[];
}

interface FieldDef {
  key: string;
  label: string;
  placeholder?: string;
  type?: 'text' | 'number' | 'toggle';
}

const FIELDS: Record<string, FieldDef[]> = {
  http: [
    { key: 'http_url', label: 'Relay URL (generic REST)', placeholder: 'http://192.168.1.50/relay/0' },
    { key: 'http_url_template', label: 'URL template (Shelly/Tasmota style)', placeholder: 'http://192.168.1.50/relay/0?turn={action}' },
    { key: 'http_method', label: 'HTTP method', placeholder: 'POST' },
  ],
  gpio: [
    { key: 'gpio_pin', label: 'GPIO pin (BCM)', type: 'number', placeholder: '17' },
    { key: 'gpio_active_high', label: 'Active high', type: 'toggle' },
  ],
  serial: [
    { key: 'serial_port', label: 'Serial port', placeholder: '/dev/ttyUSB0 or COM3' },
    { key: 'serial_baud', label: 'Baud rate', type: 'number', placeholder: '9600' },
    { key: 'serial_lock_cmd', label: 'Lock command', placeholder: 'LOCK' },
    { key: 'serial_unlock_cmd', label: 'Unlock command', placeholder: 'UNLOCK' },
  ],
  modbus_tcp: [
    { key: 'modbus_host', label: 'Modbus host', placeholder: '192.168.1.51' },
    { key: 'modbus_port', label: 'Port', type: 'number', placeholder: '502' },
    { key: 'modbus_unit', label: 'Unit ID', type: 'number', placeholder: '1' },
    { key: 'modbus_coil', label: 'Coil', type: 'number', placeholder: '0' },
    { key: 'modbus_unlock_value', label: 'Unlock value = ON', type: 'toggle' },
  ],
};

const TYPE_ICONS: Record<string, React.ReactNode> = {
  simulate: <FlaskConical size={20} />,
  http: <Wifi size={20} />,
  gpio: <Cpu size={20} />,
  serial: <Usb size={20} />,
  modbus_tcp: <Cable size={20} />,
};

export default function RelaySetup() {
  const [types, setTypes] = useState<RelayType[]>([]);
  const [step, setStep] = useState(1);
  const [relayType, setRelayType] = useState('simulate');
  const [settings, setSettings] = useState<Record<string, string | number | boolean>>({});
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api.get('/relay/types')
      .then((r) => setTypes(r.data.types ?? []))
      .catch(() => setTypes([]));
    api.get('/relay/settings')
      .then((r) => {
        const s = r.data.settings ?? {};
        if (s.relay_type) setRelayType(s.relay_type);
        setSettings(s);
      })
      .catch(() => undefined);
  }, []);

  const currentType = types.find((t) => t.type === relayType);
  const fields = FIELDS[relayType] ?? [];

  const setField = (key: string, value: string | number | boolean) =>
    setSettings((prev) => ({ ...prev, [key]: value }));

  const buildPayload = () => ({ relay_type: relayType, ...settings });

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await api.post('/relay/test', { action: 'unlock', ...buildPayload() });
      toast.success(res.data.message ?? 'Test command sent');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await api.get('/relay/drivers', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'vantag-relay-drivers.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setDownloading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await api.put('/relay/settings', buildPayload());
      toast.success('Relay configuration saved');
      setSettings(res.data.settings ?? {});
      setStep(3);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const input = (field: FieldDef) => {
    const val = settings[field.key] ?? '';
    if (field.type === 'toggle') {
      return (
        <button
          type="button"
          onClick={() => setField(field.key, !val)}
          className={clsx(
            'relative w-12 h-6 rounded-full transition-colors',
            val ? 'bg-vantag-green' : 'bg-slate-600'
          )}
        >
          <span
            className={clsx(
              'absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform',
              val ? 'translate-x-6' : 'translate-x-0.5'
            )}
          />
        </button>
      );
    }
    return (
      <input
        type={field.type ?? 'text'}
        value={val as string | number}
        placeholder={field.placeholder}
        onChange={(e) =>
          setField(field.key, field.type === 'number' ? Number(e.target.value) : e.target.value)
        }
        className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-vantag-red/60"
      />
    );
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-vantag-red/15 ring-1 ring-vantag-red/40">
          <Lock size={20} className="text-vantag-red" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Door Relay Setup</h1>
          <p className="text-sm text-slate-400">Configure the physical relay that locks/unlocks your door.</p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 my-6 text-xs font-medium">
        {['Relay type', 'Connection', 'Test & save'].map((label, i) => {
          const n = i + 1;
          return (
            <div key={label} className="flex items-center gap-2">
              <span
                className={clsx(
                  'flex items-center justify-center w-6 h-6 rounded-full',
                  step >= n ? 'bg-vantag-red text-white' : 'bg-slate-700 text-slate-400'
                )}
              >
                {step > n ? <CheckCircle2 size={14} /> : n}
              </span>
              <span className={step >= n ? 'text-slate-200' : 'text-slate-500'}>{label}</span>
              {n < 3 && <span className="text-slate-600">—</span>}
            </div>
          );
        })}
      </div>

      {/* Step 1 — choose type */}
      {step === 1 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {types.map((t) => (
            <button
              key={t.type}
              type="button"
              onClick={() => { setRelayType(t.type); setStep(2); }}
              className={clsx(
                'flex items-start gap-3 p-4 rounded-xl border text-left transition-all',
                relayType === t.type
                  ? 'border-vantag-red bg-vantag-red/10'
                  : 'border-slate-700 bg-slate-800/60 hover:border-slate-500'
              )}
            >
              <span className="text-vantag-red mt-0.5">{TYPE_ICONS[t.type] ?? <Cpu size={20} />}</span>
              <span>
                <span className="block text-sm font-semibold text-slate-100">{t.label}</span>
                <span className="block text-xs text-slate-400 mt-1 capitalize">Type: {t.type}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Step 2 — configure */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-slate-300">
            <span className="text-vantag-red">{TYPE_ICONS[relayType] ?? <Cpu size={20} />}</span>
            {currentType?.label ?? relayType}
          </div>
          {fields.map((f) => (
            <label key={f.key} className="block">
              <span className="block text-xs font-medium text-slate-400 mb-1">{f.label}</span>
              {input(f)}
            </label>
          ))}
          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-700/50"
            >
              <ArrowLeft size={16} /> Back
            </button>
            <button
              type="button"
              onClick={() => setStep(3)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-vantag-red text-white text-sm font-semibold hover:bg-vantag-red/90"
            >
              Continue <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Step 3 — test & save */}
      {step === 3 && (
        <div className="space-y-5">
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
            <h2 className="text-sm font-semibold text-slate-200 mb-1">Ready to test</h2>
            <p className="text-xs text-slate-400">
              Press <span className="text-slate-200">Test</span> to fire an unlock command at the relay. Your on-site
              edge agent will actuate it and report the door state back to the dashboard.
            </p>
            <div className="flex flex-wrap gap-3 mt-4">
              <button
                type="button"
                onClick={handleTest}
                disabled={testing}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-vantag-green/15 text-vantag-green border border-vantag-green/40 text-sm font-semibold hover:bg-vantag-green/25 disabled:opacity-60"
              >
                {testing ? <Loader2 size={16} className="animate-spin" /> : <FlaskConical size={16} />}
                Test unlock
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-vantag-red text-white text-sm font-semibold hover:bg-vantag-red/90 disabled:opacity-60"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                Save configuration
              </button>
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-700/50 disabled:opacity-60"
              >
                {downloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} Download driver pack
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 text-xs text-slate-400 space-y-1">
            <p className="font-semibold text-slate-300">Compatible with most relay hardware:</p>
            <p>• WiFi / HTTP relays — Shelly, Tasmota, ESPHome, Sonoff, and any REST relay</p>
            <p>• GPIO relays on a Raspberry Pi or single-board computer</p>
            <p>• Serial / USB / RS-485 relay boards</p>
            <p>• Modbus TCP relay boards</p>
            <p className="pt-1 text-slate-500">The edge agent auto-discovers common relays on your network where possible.</p>
          </div>
        </div>
      )}
    </div>
  );
}
