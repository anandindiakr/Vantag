/**
 * DownloadPage.tsx
 * =================
 * Edge Agent download & installation guide.
 *
 * Retailers download a small Python agent that runs on their local PC /
 * tablet / Raspberry Pi. The agent connects to their LAN cameras and relays
 * events + snapshots to the Vantag cloud (this VPS).
 */
import React from 'react';
import { Link } from 'react-router-dom';

const CodeBlock: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <pre className="bg-black/60 border border-white/10 rounded-lg p-4 text-sm text-violet-200 overflow-x-auto">
    <code>{children}</code>
  </pre>
);

export default function DownloadPage() {
  const apiKey = localStorage.getItem('vantag_tenant_id') || 'YOUR_TENANT_ID';
  const apiUrl = window.location.origin;

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <Link to="/dashboard" className="text-violet-400 hover:text-violet-300">
          ← Back to Dashboard
        </Link>
      </div>

      <h1 className="text-4xl font-bold mb-2">Install Vantag Edge Agent</h1>
      <p className="text-white/60 mb-8">
        The Edge Agent runs on your local PC/tablet/Raspberry Pi and connects
        your LAN cameras to Vantag cloud. Choose your platform below.
      </p>

      {/* ── Download buttons ─────────────────────────────────────────────── */}
      <section className="grid md:grid-cols-3 gap-4 mb-12">
        <a
          href="/downloads/vantag-agent-windows.zip"
          className="bg-gradient-to-br from-violet-600 to-purple-700 hover:from-violet-500 hover:to-purple-600 rounded-xl p-6 text-center transition-all"
        >
          <div className="text-5xl mb-3">🪟</div>
          <div className="font-bold text-lg">Windows</div>
          <div className="text-sm text-white/70 mt-1">Windows 10/11 · 64-bit</div>
          <div className="text-xs mt-3 px-3 py-1 bg-white/10 rounded-full inline-block">
            Download .zip
          </div>
        </a>

        <a
          href="/downloads/vantag-agent-linux.tar.gz"
          className="bg-gradient-to-br from-blue-600 to-indigo-700 hover:from-blue-500 hover:to-indigo-600 rounded-xl p-6 text-center transition-all"
        >
          <div className="text-5xl mb-3">🐧</div>
          <div className="font-bold text-lg">Linux / Raspberry Pi</div>
          <div className="text-sm text-white/70 mt-1">Ubuntu, Debian, Raspbian</div>
          <div className="text-xs mt-3 px-3 py-1 bg-white/10 rounded-full inline-block">
            Download .tar.gz
          </div>
        </a>

        <a
          href="/downloads/vantag-agent-mac.zip"
          className="bg-gradient-to-br from-slate-600 to-slate-800 hover:from-slate-500 hover:to-slate-700 rounded-xl p-6 text-center transition-all"
        >
          <div className="text-5xl mb-3">🍎</div>
          <div className="font-bold text-lg">macOS</div>
          <div className="text-sm text-white/70 mt-1">Intel + Apple Silicon</div>
          <div className="text-xs mt-3 px-3 py-1 bg-white/10 rounded-full inline-block">
            Download .zip
          </div>
        </a>
      </section>

      {/* ── Installation steps ───────────────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-2xl font-bold mb-6">Installation (5 minutes)</h2>

        <div className="space-y-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center font-bold">1</span>
              <h3 className="font-bold text-lg">Extract the downloaded file</h3>
            </div>
            <p className="text-white/60 ml-11">
              Windows / Mac: right-click → Extract. Linux: <code className="bg-black/40 px-1.5 py-0.5 rounded">tar -xzf vantag-agent-linux.tar.gz</code>
            </p>
          </div>

          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center font-bold">2</span>
              <h3 className="font-bold text-lg">Run the installer</h3>
            </div>
            <div className="ml-11">
              <p className="text-white/60 mb-2">Open a terminal in the extracted folder and run:</p>
              <CodeBlock>{`# Windows (PowerShell):
.\\install.ps1

# Linux / Mac:
./install.sh`}</CodeBlock>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center font-bold">3</span>
              <h3 className="font-bold text-lg">Paste your credentials</h3>
            </div>
            <div className="ml-11">
              <p className="text-white/60 mb-2">When prompted, paste these values (they are unique to your account):</p>
              <CodeBlock>{`Vantag Cloud URL : ${apiUrl}
Tenant ID        : ${apiKey}`}</CodeBlock>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center font-bold">4</span>
              <h3 className="font-bold text-lg">Agent auto-detects your cameras</h3>
            </div>
            <p className="text-white/60 ml-11">
              The agent scans your local network (192.168.x.x) for IP cameras and
              lists them in your Vantag dashboard. You then confirm which ones
              belong to which zone.
            </p>
          </div>

          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center font-bold">5</span>
              <h3 className="font-bold text-lg">Done — cameras go live</h3>
            </div>
            <p className="text-white/60 ml-11">
              Back here on the dashboard, cameras will flip from Offline to
              Online. Risk scores, alerts, and incidents will start flowing in
              real time.
            </p>
          </div>
        </div>
      </section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-2xl font-bold mb-6">Frequently asked questions</h2>
        <div className="space-y-4">
          <details className="bg-white/5 rounded-lg p-4 border border-white/10">
            <summary className="cursor-pointer font-bold">Why do I need an Edge Agent?</summary>
            <p className="mt-3 text-white/70">
              Your cameras live on your local network (private IPs like
              192.168.x.x). The Vantag cloud server cannot reach them directly —
              that's standard internet security. The Edge Agent is a small
              program that bridges your cameras to the cloud securely.
            </p>
          </details>

          <details className="bg-white/5 rounded-lg p-4 border border-white/10">
            <summary className="cursor-pointer font-bold">Do I need a PC? Can it run on a phone?</summary>
            <p className="mt-3 text-white/70">
              Low hardware requirements: any PC, tablet, Raspberry Pi 4 (or
              newer), or an always-on Android tablet works. For 2–5 cameras, a
              Pi 4 or an old laptop is plenty. A dedicated phone/tablet version
              is on the roadmap.
            </p>
          </details>

          <details className="bg-white/5 rounded-lg p-4 border border-white/10">
            <summary className="cursor-pointer font-bold">Is my video streamed to the cloud?</summary>
            <p className="mt-3 text-white/70">
              No — video processing happens locally on the Edge Agent. Only
              events (e.g., "sweep detected at 14:32 in Zone B") and evidence
              snapshots are uploaded. This keeps your video private and uses
              minimal bandwidth.
            </p>
          </details>

          <details className="bg-white/5 rounded-lg p-4 border border-white/10">
            <summary className="cursor-pointer font-bold">What if I don't have a PC or tablet?</summary>
            <p className="mt-3 text-white/70">
              We ship a pre-configured Vantag Edge Box (Raspberry Pi 4 in a
              case, ready to plug in). Contact us for pricing in your region.
            </p>
          </details>
        </div>
      </section>
    </div>
  );
}
