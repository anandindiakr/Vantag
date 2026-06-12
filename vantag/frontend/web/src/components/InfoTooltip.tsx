// frontend/web/src/components/InfoTooltip.tsx
// Small inline help icon that shows plain-English tooltip on hover/click.

import { HelpCircle } from 'lucide-react';

export default function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="inline-block ml-1 group relative cursor-help">
      <HelpCircle className="w-3.5 h-3.5 text-white/40 hover:text-cyan-400 transition inline-block align-middle" />
      <span className="absolute left-full ml-2 top-0 hidden group-hover:block z-50 w-64 p-3 bg-slate-800 border border-cyan-500/30 rounded-lg text-xs text-white/80 shadow-xl pointer-events-none">
        {text}
      </span>
    </span>
  );
}
