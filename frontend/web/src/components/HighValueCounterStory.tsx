/**
 * HighValueCounterStory.tsx — animated explainer for the Help Center.
 *
 * Two auto-playing tabs:
 *   "How it works"   — the theft sequence (approach → reach-in → withdraw →
 *                      tray change → grab-and-run) as an animated counter scene.
 *   "How to configure" — the 5 point-and-click setup steps.
 */
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { DoorOpen, Gem, MousePointerClick, Play, Pause } from 'lucide-react';

type WorksStep = {
  title: string;
  caption: string;
  alert: { label: string; sev: string; color: string } | null;
  personX: number;
  handIn: boolean;
  gems: number;
};

type ConfigureStep = {
  icon: typeof MousePointerClick;
  title: string;
  desc: string;
};

const HOW_IT_WORKS: WorksStep[] = [
  { title: 'Customer approaches the counter', caption: 'A person walks up to the serving counter, just like any browsing customer.', alert: null, personX: 150, handIn: false, gems: 3 },
  { title: 'Hand reaches into the tray', caption: 'The detector tracks the person and watches their hand cross into the display tray.', alert: null, personX: 400, handIn: true, gems: 3 },
  { title: 'Hand withdraws — Case Hand Reach fires', caption: 'A hand entering and withdrawing is the classic palm-and-pull motion.', alert: { label: 'CASE HAND REACH', sev: 'HIGH', color: '#fbbf24' }, personX: 400, handIn: false, gems: 3 },
  { title: 'Tray contents change — Tray Change fires', caption: 'The tray is no longer as it was a moment ago while the person is still at the counter.', alert: { label: 'TRAY CHANGE', sev: 'HIGH', color: '#f59e0b' }, personX: 430, handIn: false, gems: 1 },
  { title: 'Case → Exit at speed — Grab & Run fires', caption: 'The suspect bolts from the display case to the door — a classic snatch-and-run.', alert: { label: 'GRAB & RUN', sev: 'CRITICAL', color: '#f43f5e' }, personX: 810, handIn: false, gems: 1 },
];

const HOW_TO_CONFIGURE: ConfigureStep[] = [
  { icon: MousePointerClick, title: 'Open High-Value Counter', desc: 'In the sidebar, open the High-Value Counter page and pick the counter camera.' },
  { icon: Gem, title: 'Draw the Serving Counter', desc: 'Click points around the customer-side counter surface where people stand.' },
  { icon: Gem, title: 'Draw the Display Tray', desc: 'Trace a tight shape around the tray or case a hand reaches into. Tight = accurate.' },
  { icon: DoorOpen, title: 'Draw Case + Exit', desc: 'Outline the display case and the exit door (and optionally the approach corridor).' },
  { icon: Play, title: 'Save & Test', desc: 'Save, then fire the demo from Demo Center or run a real walk-through with staff.' },
];

export default function HighValueCounterStory() {
  const [tab, setTab] = useState<'works' | 'configure'>('works');
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);

  const total = tab === 'works' ? HOW_IT_WORKS.length : HOW_TO_CONFIGURE.length;

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % total), 2600);
    return () => clearTimeout(t);
  }, [playing, step, total]);

  const resetFor = (next: 'works' | 'configure') => {
    setTab(next);
    setStep(0);
    setPlaying(true);
  };

  const ws = HOW_IT_WORKS[step] ?? HOW_IT_WORKS[0];

  return (
    <div className="rounded-2xl border border-amber-400/20 bg-[#0d1117] overflow-hidden">
      {/* Header + tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-white/8">
        <div className="flex items-center gap-2">
          <Gem className="w-5 h-5 text-amber-400" />
          <span className="font-syne font-bold text-white">High-Value Counter — animated story</span>
        </div>
        <div className="flex items-center gap-1 bg-white/5 border border-white/8 rounded-full p-1">
          <button
            onClick={() => resetFor('works')}
            className={`px-3.5 py-1.5 rounded-full text-sm font-semibold transition-colors ${tab === 'works' ? 'bg-amber-400 text-black' : 'text-white/60 hover:text-white'}`}
          >
            How it works
          </button>
          <button
            onClick={() => resetFor('configure')}
            className={`px-3.5 py-1.5 rounded-full text-sm font-semibold transition-colors ${tab === 'configure' ? 'bg-amber-400 text-black' : 'text-white/60 hover:text-white'}`}
          >
            How to configure
          </button>
        </div>
      </div>

      <div className="p-6">
        {tab === 'works' ? (
          <>
            {/* Scene */}
            <div className="relative rounded-xl border border-white/8 bg-[#080c10] overflow-hidden">
              <svg viewBox="0 0 900 300" className="w-full h-auto">
                {/* floor */}
                <line x1="0" y1="278" x2="900" y2="278" stroke="#1e293b" strokeWidth="2" />

                {/* exit door */}
                <rect x="752" y="96" width="96" height="182" rx="6" fill="#1a2236" stroke="#f43f5e" strokeWidth="2" />
                <text x="775" y="150" fill="#f43f5e" fontSize="16" fontWeight="700">EXIT</text>

                {/* counter + tray */}
                <rect x="372" y="168" width="190" height="110" rx="6" fill="#1a2236" stroke="#22d3ee" strokeWidth="1.5" />
                <rect x="362" y="150" width="210" height="18" rx="3" fill="#164e63" opacity="0.7" />
                <rect x="418" y="126" width="130" height="26" rx="4" fill="#78350f" stroke="#f59e0b" strokeWidth="2" />

                {/* gems in the tray */}
                <motion.g animate={{ opacity: ws.gems >= 3 ? 1 : 0 }} transition={{ duration: 0.4 }}>
                  <circle cx="444" cy="139" r="6" fill="#fbbf24" />
                  <circle cx="472" cy="139" r="6" fill="#fcd34d" />
                </motion.g>
                <motion.g animate={{ opacity: ws.gems >= 1 ? 1 : 0 }} transition={{ duration: 0.4 }}>
                  <circle cx="500" cy="139" r="6" fill="#fbbf24" />
                </motion.g>

                {/* hand reaching into the tray */}
                <motion.g
                  animate={{ opacity: ws.handIn ? 1 : 0, y: ws.handIn ? 0 : 26 }}
                  transition={{ duration: 0.4 }}
                >
                  <circle cx="468" cy="150" r="9" fill="#fbbf24" stroke="#0d1117" strokeWidth="3" />
                </motion.g>

                {/* person */}
                <motion.g
                  animate={{ x: ws.personX }}
                  transition={{ duration: 0.7, ease: 'easeInOut' }}
                >
                  <circle cx="0" cy="196" r="20" fill="#1e293b" stroke="#64748b" strokeWidth="2" />
                  <path d="M-58,250 Q0,220 58,250 L58,268 Q0,248 -58,268 Z" fill="#1e293b" stroke="#64748b" strokeWidth="2" />
                </motion.g>

                {/* case zone (dashed, near counter) */}
                <rect x="372" y="120" width="210" height="160" rx="8" fill="none" stroke="#a78bfa" strokeWidth="1.5" strokeDasharray="6 5" opacity="0.55" />
              </svg>

              {/* alert toast */}
              <div className="absolute top-3 left-1/2 -translate-x-1/2">
                <AnimatePresence mode="wait">
                  {ws.alert && (
                    <motion.div
                      key={step}
                      initial={{ opacity: 0, y: -12, scale: 0.9 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -12, scale: 0.9 }}
                      className="flex items-center gap-2 px-4 py-2 rounded-full border font-mono-alt text-xs font-bold tracking-widest"
                      style={{ background: `${ws.alert.color}18`, borderColor: `${ws.alert.color}55`, color: ws.alert.color }}
                    >
                      <span className="w-2 h-2 rounded-full animate-blink-live" style={{ background: ws.alert.color }} />
                      {ws.alert.label} · {ws.alert.sev}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            {/* caption */}
            <div className="mt-5 text-center min-h-[64px]">
              <AnimatePresence mode="wait">
                <motion.div key={step} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                  <h4 className="font-syne font-bold text-white text-lg mb-1">{ws.title}</h4>
                  <p className="text-white/50 text-sm font-body-alt">{ws.caption}</p>
                </motion.div>
              </AnimatePresence>
            </div>
          </>
        ) : (
          <div className="space-y-3">
            {HOW_TO_CONFIGURE.map((s, i) => (
              <motion.div
                key={s.title}
                animate={{
                  opacity: i === step ? 1 : i < step ? 0.55 : 0.35,
                  scale: i === step ? 1.01 : 1,
                }}
                transition={{ duration: 0.4 }}
                className={`flex items-start gap-4 p-4 rounded-xl border transition-colors ${
                  i === step ? 'border-amber-400/40 bg-amber-400/5' : 'border-white/8 bg-white/[0.02]'
                }`}
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${i === step ? 'bg-amber-400 text-black' : 'bg-white/5 text-white/40'}`}>
                  <s.icon className="w-5 h-5" />
                </div>
                <div>
                  <h4 className={`font-semibold text-[15px] mb-0.5 ${i === step ? 'text-amber-300' : 'text-white'}`}>
                    <span className="font-mono-alt mr-2 text-xs text-white/30">0{i + 1}</span>
                    {s.title}
                  </h4>
                  <p className="text-sm text-white/45 font-body-alt">{s.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        {/* Controls */}
        <div className="mt-6 flex items-center justify-center gap-4">
          <button
            onClick={() => setPlaying((p) => !p)}
            className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 text-white/70 hover:text-white hover:border-white/25 text-sm font-semibold transition-all"
          >
            {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            {playing ? 'Pause' : 'Play'}
          </button>
          <div className="flex gap-1.5">
            {Array.from({ length: total }).map((_, i) => (
              <button
                key={i}
                onClick={() => { setStep(i); setPlaying(false); }}
                className={`h-2 rounded-full transition-all ${i === step ? 'w-6 bg-amber-400' : 'w-2 bg-white/20 hover:bg-white/40'}`}
                aria-label={`Step ${i + 1}`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
