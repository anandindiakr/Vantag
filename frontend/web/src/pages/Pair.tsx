/**
 * Pair.tsx
 * ========
 * Public landing page opened when a user scans the Edge Agent pairing QR code
 * with their phone. The QR encodes a deep link of the form:
 *
 *     https://<region-domain>/pair#<base64-payload>
 *
 * where <base64-payload> is base64(JSON{ api_key, tenant_id, api_url, device_type }).
 *
 * Scanning the QR with any phone camera now opens this page, which explains
 * exactly what the pairing credential is for and how to finish setup — instead
 * of showing a meaningless raw string.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Shield, Copy, CheckCircle, Download, Monitor, Terminal, AlertCircle } from 'lucide-react';

interface PairPayload {
  api_key: string;
  tenant_id?: string;
  api_url?: string;
  device_type?: string;
}

function decodePayload(): PairPayload | null {
  // Credential travels in the URL fragment (#...) so it never hits the server logs.
  const raw = (window.location.hash || '').replace(/^#/, '');
  if (!raw) return null;
  try {
    const json = atob(decodeURIComponent(raw));
    const obj = JSON.parse(json);
    if (obj && typeof obj.api_key === 'string') return obj as PairPayload;
  } catch {
    // Fall through: maybe the QR encoded a bare api_key (older agents).
  }
  // Backwards-compat: treat the fragment itself as a raw api_key.
  return raw.length > 8 ? { api_key: raw } : null;
}

export default function Pair() {
  const payload = React.useMemo(decodePayload, []);
  const [copied, setCopied] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const apiBase = payload?.api_url || window.location.origin;

  const copyKey = async () => {
    if (!payload?.api_key) return;
    try {
      await navigator.clipboard.writeText(payload.api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Could not copy automatically — please select and copy the key manually.');
    }
  };

  const downloadAgent = async (platform: 'windows' | 'linux') => {
    setError(null);
    setBusy(platform);
    try {
      const res = await fetch(`${apiBase}/api/agent/download?platform=${platform}`);
      if (!res.ok) throw new Error(`Download failed (${res.status}).`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vantag-edge-agent-${platform}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e?.message || 'Download failed. Open this page on the PC where you will run the agent.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex flex-col items-center px-4 py-12">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(99,102,241,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(99,102,241,0.03)_1px,transparent_1px)] bg-[size:60px_60px] pointer-events-none" />

      <Link to="/" className="flex items-center gap-2 mb-8 relative">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
          <Shield className="w-4 h-4" />
        </div>
        <span className="text-lg font-bold">Vantag</span>
      </Link>

      <div className="w-full max-w-lg relative">
        {!payload ? (
          <div className="bg-white/3 border border-white/8 rounded-2xl p-8 text-center">
            <AlertCircle className="w-10 h-10 text-amber-400 mx-auto mb-4" />
            <h1 className="text-xl font-bold mb-2">Invalid pairing link</h1>
            <p className="text-white/50 text-sm">
              This pairing QR code looks incomplete or has expired. Please go back to the
              dashboard onboarding and generate a fresh Edge Agent pairing code.
            </p>
            <Link to="/onboarding" className="inline-block mt-6 px-5 py-3 bg-violet-600 hover:bg-violet-500 rounded-xl font-semibold">
              Back to setup
            </Link>
          </div>
        ) : (
          <div className="bg-white/3 border border-white/8 rounded-2xl p-8">
            <div className="w-14 h-14 rounded-2xl bg-emerald-600/20 flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-7 h-7 text-emerald-400" />
            </div>
            <h1 className="text-2xl font-bold text-center mb-1">Pair your Edge Agent</h1>
            <p className="text-white/50 text-sm text-center mb-6">
              This QR is your <strong className="text-white/80">Edge Agent pairing key</strong>. It is not an app to
              install on your phone — it connects the Vantag Edge Agent (running on a PC near
              your cameras) to your account.
            </p>

            {/* Pairing key */}
            <div className="bg-white/5 rounded-xl p-4 mb-6">
              <div className="text-xs text-white/40 mb-2">Pairing key</div>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono text-violet-200 break-all">{payload.api_key}</code>
                <button onClick={copyKey} className="shrink-0 p-2 rounded-lg bg-white/8 hover:bg-white/15 transition-all">
                  {copied ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              {payload.tenant_id && (
                <div className="text-[11px] text-white/30 mt-2">Account: {payload.tenant_id}</div>
              )}
            </div>

            {/* Steps */}
            <div className="space-y-3 mb-6">
              <h2 className="text-sm font-semibold text-white/70">How to finish setup</h2>
              {[
                'On a Windows or Linux PC that is on the SAME network as your cameras, download the Edge Agent below.',
                'Unzip and run the agent (run.bat on Windows, run.sh on Linux).',
                'When it asks for a pairing key, paste the key above — or scan this same QR from the agent\u2019s setup screen.',
                'The agent auto-discovers your cameras and they appear on your dashboard within a minute.',
              ].map((t, i) => (
                <div key={i} className="flex gap-3 text-sm text-white/60">
                  <span className="shrink-0 w-6 h-6 rounded-full bg-violet-600/30 text-violet-200 text-xs flex items-center justify-center font-bold">{i + 1}</span>
                  <span>{t}</span>
                </div>
              ))}
            </div>

            {/* Download buttons */}
            <div className="flex gap-3 mb-3">
              <button onClick={() => downloadAgent('windows')} disabled={busy !== null}
                className="flex-1 py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all">
                <Monitor className="w-4 h-4" /> {busy === 'windows' ? 'Preparing…' : 'Windows Agent'}
              </button>
              <button onClick={() => downloadAgent('linux')} disabled={busy !== null}
                className="flex-1 py-3 bg-white/8 hover:bg-white/12 disabled:opacity-50 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all">
                <Terminal className="w-4 h-4" /> {busy === 'linux' ? 'Preparing…' : 'Linux / Pi'}
              </button>
            </div>

            <p className="text-[11px] text-white/30 text-center flex items-center justify-center gap-1.5">
              <Download className="w-3 h-3" /> Tip: open this page on the PC where the agent will run to download directly.
            </p>

            {error && (
              <div className="mt-4 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
