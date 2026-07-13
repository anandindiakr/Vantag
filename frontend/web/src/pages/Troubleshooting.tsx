import { useState } from 'react';
import toast from 'react-hot-toast';
import {
  WifiOff,
  Camera,
  AlertTriangle,
  Network,
  Cpu,
  Eye,
  Map,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  Info,
  HelpCircle,
  ThumbsUp,
  ThumbsDown,
  Send,
} from 'lucide-react';

interface Section {
  id: string;
  icon: React.ReactNode;
  title: string;
  content: React.ReactNode;
}

function Accordion({ sections }: { sections: Section[] }) {
  const [open, setOpen] = useState<string | null>(sections[0]?.id ?? null);
  return (
    <div className="space-y-2">
      {sections.map((s) => (
        <div key={s.id} className="rounded-xl border border-slate-700/60 overflow-hidden">
          <button
            className="w-full flex items-center gap-3 px-5 py-4 bg-vantag-card hover:bg-slate-700/40 transition-colors text-left"
            onClick={() => setOpen(open === s.id ? null : s.id)}
          >
            <span className="text-vantag-red">{s.icon}</span>
            <span className="flex-1 text-sm font-semibold text-slate-100">{s.title}</span>
            {open === s.id ? (
              <ChevronUp size={16} className="text-slate-400" />
            ) : (
              <ChevronDown size={16} className="text-slate-400" />
            )}
          </button>
          {open === s.id && (
            <div className="px-5 pb-5 pt-3 bg-slate-900/60 text-sm text-slate-300 space-y-4">
              {s.content}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Step({ n, text }: { n: number; text: React.ReactNode }) {
  return (
    <div className="flex gap-3 items-start">
      <span className="mt-0.5 flex-shrink-0 w-6 h-6 rounded-full bg-vantag-red/20 text-vantag-red text-xs font-bold flex items-center justify-center">
        {n}
      </span>
      <p className="leading-relaxed">{text}</p>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg bg-amber-600/10 border border-amber-600/30 p-3 text-amber-200 text-xs">
      <Info size={14} className="flex-shrink-0 mt-0.5" />
      <span>{children}</span>
    </div>
  );
}

function Good({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg bg-green-600/10 border border-green-600/30 p-3 text-green-200 text-xs">
      <CheckCircle size={14} className="flex-shrink-0 mt-0.5" />
      <span>{children}</span>
    </div>
  );
}

const sections: Section[] = [
  {
    id: 'camera-offline',
    icon: <WifiOff size={18} />,
    title: 'Camera Showing Offline',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          A camera shows "Offline" when the Vantag Edge Agent cannot connect to it. Work through these steps in order.
        </p>
        <Step n={1} text={<><strong>Is the Edge Agent running?</strong> Open Retail Vantag on your Windows PC. The tray icon must be green. If not, double-click <code className="bg-slate-800 px-1 rounded">retail-vantag.exe</code> to start it.</>} />
        <Step n={2} text={<><strong>Are you on the same network?</strong> The PC running the Edge Agent and the cameras/NVR must be on the same LAN (same router/Wi-Fi). If your laptop is on mobile data, cameras will never be reachable.</>} />
        <Step n={3} text={<><strong>Ping the camera/NVR</strong> — open Command Prompt and type <code className="bg-slate-800 px-1 rounded">ping 192.168.254.50</code> (use your NVR IP). If it times out, the network path is blocked.</>} />
        <Step n={4} text={<><strong>Check RTSP port</strong> — NVRs and cameras use port 554 for RTSP. Make sure no firewall or router rule is blocking it.</>} />
        <Step n={5} text={<><strong>Re-enter camera credentials</strong> — go to <em>Manage Cameras → Edit</em>, confirm the username/password match those on the NVR web interface (default Hikvision: admin / your-password).</>} />
        <Note>The Vantag cloud server cannot reach your LAN cameras directly — only the Edge Agent on your local network can. The camera status is reported by the agent back to the cloud every 30 seconds.</Note>
      </>
    ),
  },
  {
    id: 'rtsp',
    icon: <Camera size={18} />,
    title: 'RTSP Stream & NVR Setup',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          RTSP (Real Time Streaming Protocol) is the standard video path. NVR-connected cameras must always be accessed through the NVR, not directly by individual camera IP.
        </p>

        <div className="rounded-lg bg-slate-800/60 p-4 space-y-2">
          <p className="text-xs font-semibold text-slate-200 mb-2">Hikvision NVR — Channel RTSP paths</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-400">
                <th className="text-left pb-2">Channel</th>
                <th className="text-left pb-2">Main stream (HD)</th>
                <th className="text-left pb-2">Sub stream (low)</th>
              </tr>
            </thead>
            <tbody className="space-y-1">
              {[1,2,3,4,5,6,7,8].map((ch) => (
                <tr key={ch} className="border-t border-slate-700/40">
                  <td className="py-1 text-slate-300">Cam {ch}</td>
                  <td className="py-1 font-mono text-green-300">rtsp://admin:PASSWORD@192.168.254.50:554/Streaming/Channels/{ch}01</td>
                  <td className="py-1 font-mono text-amber-300">…/{ch}02</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Step n={1} text={<>Replace <code className="bg-slate-800 px-1 rounded">PASSWORD</code> with your NVR admin password and <code className="bg-slate-800 px-1 rounded">192.168.254.50</code> with your NVR IP.</>} />
        <Step n={2} text={<>Paste the full RTSP URL into Manage Cameras → Add Camera → RTSP URL field.</>} />
        <Step n={3} text={<>Click <strong>Save</strong>. The Edge Agent will attempt to connect within 30 seconds and update the camera status to Online.</>} />

        <Note>Use the <strong>sub stream</strong> (…02) for lower CPU usage. Use main stream only if you need full HD for AI analysis.</Note>
        <Good>Auto-detect works by sending this URL probe task to the Edge Agent. If the agent is offline, auto-detect will show "No agent available" — start the agent first.</Good>
      </>
    ),
  },
  {
    id: 'network',
    icon: <Network size={18} />,
    title: 'Remote Access & Different Networks',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          You can monitor your store cameras from anywhere in the world — here is how the architecture works and what to do in different scenarios.
        </p>

        <div className="rounded-lg bg-slate-800/60 p-4 text-xs space-y-3">
          <p className="font-semibold text-slate-200">How remote viewing works</p>
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="w-24 text-vantag-red font-medium">Camera/NVR</span>
              <span>→</span>
              <span className="text-slate-300">Edge Agent (your LAN PC)</span>
              <span>→</span>
              <span className="text-vantag-green font-medium">Vantag Cloud</span>
              <span>→</span>
              <span className="text-slate-300">Your phone/laptop anywhere</span>
            </div>
          </div>
          <p>The Edge Agent is the bridge. It reads the camera locally and sends AI results + snapshots to the cloud. <strong>You never need to open any port on your router.</strong></p>
        </div>

        <Step n={1} text={<><strong>You are at home, store is open:</strong> As long as the Edge Agent PC at the store is running and connected to internet, you see live data in the Vantag dashboard from any browser or phone.</>} />
        <Step n={2} text={<><strong>You are on mobile data:</strong> No difference — Vantag uses WebSocket over HTTPS. Works on any network.</>} />
        <Step n={3} text={<><strong>Store camera feed not visible:</strong> Check that the Edge Agent PC has internet access and has not gone to sleep. Use Windows Settings → Power → Sleep → Never for the store PC.</>} />
        <Step n={4} text={<><strong>Multiple stores:</strong> Install the Edge Agent on one PC per store. Each store gets its own Agent ID automatically.</>} />

        <Note>Live video streaming (raw frames) is NOT sent to the cloud — only AI events, snapshots, and alerts. This keeps your bandwidth usage low and improves privacy.</Note>
      </>
    ),
  },
  {
    id: 'agent',
    icon: <Cpu size={18} />,
    title: 'Edge Agent — Install & Keep Running',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          The Edge Agent is a small Windows program that runs on the store PC and handles all local camera work.
        </p>
        <Step n={1} text={<>Download from <em>Install Edge Agent</em> in the sidebar. Extract the ZIP to any folder (e.g. <code className="bg-slate-800 px-1 rounded">C:\Vantag\</code>).</>} />
        <Step n={2} text={<>Run <code className="bg-slate-800 px-1 rounded">retail-vantag.exe</code> (or <code className="bg-slate-800 px-1 rounded">run.bat</code>). The tray icon appears — green = connected.</>} />
        <Step n={3} text={<>To make it start automatically with Windows: right-click <code className="bg-slate-800 px-1 rounded">run.bat</code> → Create shortcut → press <kbd className="bg-slate-700 px-1 rounded">Win+R</kbd> → type <code className="bg-slate-800 px-1 rounded">shell:startup</code> → paste the shortcut there.</>} />
        <Step n={4} text={<>If the agent gets stuck at "Scanning…" it has finished ONVIF probing but found no cameras. This is normal for NVR setups. Click <strong>Skip</strong> and add cameras manually via RTSP URL.</>} />
        <Step n={5} text={<>After updating the Vantag app, re-download and replace the agent folder to get the latest version. The version number is shown in Agent Status → Version.</>} />

        <Note>Keep the store PC awake: Settings → System → Power & Sleep → set both to "Never". The agent cannot work if Windows goes to sleep.</Note>
        <Good>You do NOT need Docker on the store PC. Docker is only used on the cloud server (VPS). Users only need the Edge Agent exe.</Good>
      </>
    ),
  },
  {
    id: 'ai-settings',
    icon: <Eye size={18} />,
    title: 'AI Functions — What They Do & How to Tune',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          All AI detections run inside the Edge Agent on your store PC using the YOLOv8 model. Here is what each function does and how to adjust it.
        </p>

        <div className="space-y-4">
          {[
            {
              name: 'Shoplifting Detection',
              desc: 'Fires when a person stays near a bag/backpack for more than 2 seconds — the classic "item-dwell" pattern.',
              tip: 'Set sensitivity higher in areas with dense product shelves. Lower it near waiting zones to reduce false alarms.',
            },
            {
              name: 'Restricted Zone',
              desc: 'Fires when any detected person enters a polygon zone you draw in the Zone Editor.',
              tip: 'Draw tight polygons. Larger zones trigger more often. Use for stockrooms, staff areas, ATM zones.',
            },
            {
              name: 'Crowding / Overcrowding',
              desc: 'Fires when more than N people are detected in a zone simultaneously. N is set in camera settings.',
              tip: 'Start with N=5 and adjust. A 3m × 3m counter area becomes "crowded" at around 3–4 people.',
            },
            {
              name: 'Loitering',
              desc: 'Fires when a person stays in one spot for more than the configured duration (default 30 seconds).',
              tip: 'Increase the timer for areas where customers naturally wait (checkout). Decrease for corridors.',
            },
            {
              name: 'Fall Detection',
              desc: "Fires when a person's bounding box aspect ratio suddenly changes from tall (standing) to wide (fallen).",
              tip: 'Works best with top-down or 45° angle cameras. Side-on cameras may miss some falls.',
            },
            {
              name: 'Suspicious Behaviour',
              desc: 'A composite rule: rapid back-and-forth movement + proximity to items triggers this alert.',
              tip: 'This is the most sensitive setting. Use a high confidence threshold (0.6+) in busy stores.',
            },
          ].map((item) => (
            <div key={item.name} className="rounded-lg bg-slate-800/40 border border-slate-700/40 p-3 space-y-1">
              <p className="font-semibold text-slate-100 text-xs">{item.name}</p>
              <p className="text-xs text-slate-300">{item.desc}</p>
              <p className="text-xs text-amber-300"><span className="font-medium">Tip: </span>{item.tip}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-lg bg-slate-800/60 p-4 text-xs space-y-2">
          <p className="font-semibold text-slate-200">Confidence Slider</p>
          <p className="text-slate-300">
            Each camera has a confidence slider (0.3 – 0.9) in <em>Manage Cameras → Edit → AI Settings</em>.
          </p>
          <ul className="list-disc list-inside text-slate-400 space-y-1">
            <li><strong>Low (0.3–0.4):</strong> Catches more events but more false alarms — good for proof-of-concept testing.</li>
            <li><strong>Medium (0.5–0.6):</strong> Balanced — recommended for most retail stores.</li>
            <li><strong>High (0.7+):</strong> Fewer alerts, only confident detections — good for busy stores with many people.</li>
          </ul>
        </div>
      </>
    ),
  },
  {
    id: 'zone-editor',
    icon: <Map size={18} />,
    title: 'Zone Editor — How to Draw & Use Zones',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          Zones let you define areas on the camera frame. AI rules like Restricted Zone, Crowding, and Loitering only fire inside these zones.
        </p>

        <Step n={1} text={<>Go to <em>Zone Editor</em> in the sidebar. Select a camera from the dropdown at the top.</>} />
        <Step n={2} text={<>The live camera snapshot appears. <strong>Click once</strong> to place the first corner of your zone polygon.</>} />
        <Step n={3} text={<>Continue clicking to add more corners. A minimum of 3 clicks creates a triangle. Most zones work best as rectangles (4 clicks).</>} />
        <Step n={4} text={<>After placing all corners, <strong>double-click</strong> or click the <em>Close Polygon</em> button to complete the shape.</>} />
        <Step n={5} text={<>Give the zone a name (e.g. "Cash Counter", "Back Store") and choose the zone type: Restricted, Counting, or Loitering.</>} />
        <Step n={6} text={<>Click <strong>Save Zone</strong>. The zone is stored and the agent applies it immediately.</>} />

        <div className="rounded-lg bg-slate-800/60 p-4 text-xs space-y-2">
          <p className="font-semibold text-slate-200">Zone Types Explained</p>
          <ul className="list-disc list-inside text-slate-400 space-y-1">
            <li><strong>Restricted:</strong> Alert fires the moment anyone enters this area.</li>
            <li><strong>Counting:</strong> Tracks how many people are inside — used for crowd detection.</li>
            <li><strong>Loitering:</strong> Alert fires if someone stays inside for longer than the timer setting.</li>
            <li><strong>Safe Zone:</strong> The opposite of Restricted — alert fires when someone LEAVES this area unexpectedly (e.g. a child's play area).</li>
          </ul>
        </div>

        <Note>If dragging feels sluggish, use a mouse instead of a touchpad. On a touchscreen, use slow deliberate taps. The canvas redraws at 30 fps.</Note>
        <Good>Tip: Draw zones slightly inside the actual physical boundary — camera lens distortion at edges can cause stray detections just outside a tight zone.</Good>
      </>
    ),
  },
  {
    id: 'qr-pair',
    icon: <HelpCircle size={18} />,
    title: 'QR Pairing — What It Is & How to Use',
    content: (
      <>
        <p className="text-slate-400 text-xs mb-3">
          The QR code at the end of setup encodes your API key and server URL so the Edge Agent knows which account to connect to.
        </p>
        <Step n={1} text={<>Complete onboarding steps 1–4. On Step 5, a QR code is displayed.</>} />
        <Step n={2} text={<>On the <strong>Windows PC</strong> where the Edge Agent will run, open the agent and click <em>Scan QR or Paste Key</em>. The agent reads the QR from your phone/screen.</>} />
        <Step n={3} text={<>Alternatively, from the <em>Install Edge Agent</em> page, download the ZIP — the included <code className="bg-slate-800 px-1 rounded">config.json</code> is already pre-filled with your API key.</>} />
        <Step n={4} text={<>If the QR failed to generate, go to <em>Agent Status</em> page, copy the API key shown there, and paste it into the agent's <em>Paste Key</em> field manually.</>} />
        <Note>The QR code is one-time but the API key is permanent. You can always retrieve your key from Agent Status or Account page.</Note>
      </>
    ),
  },
];

export default function Troubleshooting() {
  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-vantag-red/20">
          <AlertTriangle size={22} className="text-vantag-red" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Troubleshooting Guide</h1>
          <p className="text-sm text-slate-400">Step-by-step fixes for the most common issues</p>
        </div>
      </div>

      {/* Quick-links */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {sections.map((s) => (
          <button
            key={s.id}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-vantag-card border border-slate-700/60 text-xs text-slate-300 hover:text-slate-100 hover:bg-slate-700/40 transition-colors text-left"
            onClick={() => {
              document.getElementById(`ts-${s.id}`)?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            <span className="text-vantag-red">{s.icon}</span>
            {s.title}
          </button>
        ))}
      </div>

      {/* Accordion */}
      <div id="ts-accordion">
        <Accordion sections={sections.map((s) => ({ ...s, id: `ts-${s.id}` }))} />
      </div>

      {/* Feedback Form */}
      <FeedbackForm />

      {/* Still stuck */}
      <div className="rounded-xl bg-vantag-card border border-slate-700/60 p-5 space-y-2">
        <p className="text-sm font-semibold text-slate-100">Still stuck?</p>
        <p className="text-xs text-slate-400">
          Email us at{' '}
          <a href="mailto:support@retail-vantag.com" className="text-vantag-red hover:underline">
            support@retail-vantag.com
          </a>{' '}
          with a screenshot and we will respond within 24 hours.
        </p>
      </div>
    </div>
  );
}

// ── Feedback form ───────────────────────────────────────────────────────────
const topicOptions = [
  'Camera Offline',
  'RTSP / NVR Setup',
  'Remote Access',
  'Edge Agent Install',
  'AI Functions',
  'Zone Editor',
  'QR Pairing',
  'Other',
];

function FeedbackForm() {
  const [helpful, setHelpful] = useState<'yes' | 'no' | null>(null);
  const [topic, setTopic] = useState('');
  const [message, setMessage] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [sending, setSending] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!helpful) {
      toast.error('Please tell us if this page was helpful');
      return;
    }
    setSending(true);
    try {
      await fetch('/api/support/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('vantag_token') ?? ''}`,
        },
        body: JSON.stringify({
          page: 'troubleshooting',
          helpful: helpful === 'yes',
          topic: topic || 'Not specified',
          message,
        }),
      });
    } catch {
      // silently ignore network errors — feedback is best-effort
    } finally {
      setSending(false);
      setSubmitted(true);
    }
  };

  if (submitted) {
    return (
      <div className="rounded-xl bg-vantag-card border border-green-600/40 p-6 flex flex-col items-center gap-3 text-center">
        <CheckCircle size={28} className="text-green-400" />
        <p className="text-sm font-semibold text-slate-100">Thanks for your feedback!</p>
        <p className="text-xs text-slate-400">We read every submission and use it to improve the guides.</p>
        <button
          className="text-xs text-vantag-red hover:underline mt-1"
          onClick={() => { setSubmitted(false); setHelpful(null); setTopic(''); setMessage(''); }}
        >
          Submit another
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-vantag-card border border-slate-700/60 p-5 space-y-5">
      <div className="flex items-center gap-2">
        <Send size={16} className="text-vantag-red" />
        <p className="text-sm font-semibold text-slate-100">Was this guide helpful?</p>
      </div>

      {/* Thumbs */}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => setHelpful('yes')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
            helpful === 'yes'
              ? 'bg-green-600/20 border-green-500/60 text-green-300'
              : 'border-slate-700 text-slate-400 hover:border-green-500/40 hover:text-green-300'
          }`}
        >
          <ThumbsUp size={15} /> Yes, it helped
        </button>
        <button
          type="button"
          onClick={() => setHelpful('no')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
            helpful === 'no'
              ? 'bg-red-600/20 border-red-500/60 text-red-300'
              : 'border-slate-700 text-slate-400 hover:border-red-500/40 hover:text-red-300'
          }`}
        >
          <ThumbsDown size={15} /> No, I still need help
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Topic */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-400">Which topic were you looking for help with?</label>
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-vantag-red/60"
          >
            <option value="">Select a topic…</option>
            {topicOptions.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {/* Message */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-400">
            {helpful === 'no'
              ? 'Tell us what you were trying to do and what went wrong:'
              : 'Any other comments or suggestions? (optional)'}
          </label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            placeholder={helpful === 'no' ? 'e.g. "Camera still shows offline after following step 3…"' : 'e.g. "Add a video walkthrough"'}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:ring-1 focus:ring-vantag-red/60"
          />
        </div>

        <button
          type="submit"
          disabled={sending}
          className="flex items-center gap-2 px-5 py-2 bg-vantag-red hover:bg-red-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Send size={14} />
          {sending ? 'Sending…' : 'Send feedback'}
        </button>
      </form>
    </div>
  );
}
