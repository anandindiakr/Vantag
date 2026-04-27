/**
 * SupportChat.tsx
 * ================
 * Floating chat widget in the bottom-right corner of every page.
 * Powered by Vantag Assistant (OpenAI GPT-4o backend at /api/support/chat).
 *
 * Can be opened and pre-seeded with a message from any page by dispatching:
 *   window.dispatchEvent(new CustomEvent('vantag:support-chat', {
 *     detail: { open: true, prefillMessage: 'Your message here' }
 *   }))
 */
import { useEffect, useRef, useState } from 'react';
import { MessageCircle, X, Send, Mail } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
}

const WELCOME: Msg = {
  role: 'assistant',
  content:
    "Hi! I'm Vantag Assistant. Ask me anything about setup, features, pricing, cameras, or technical issues — I'll try to help instantly.",
};

export default function SupportChat() {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([WELCOME]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [escalate, setEscalate] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Listen for external open/prefill events (e.g. from CamerasManage "Need help?" button)
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ open?: boolean; prefillMessage?: string }>).detail;
      if (detail?.open) {
        setOpen(true);
      }
      if (detail?.prefillMessage) {
        setInput(detail.prefillMessage);
      }
    };
    window.addEventListener('vantag:support-chat', handler);
    return () => window.removeEventListener('vantag:support-chat', handler);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, open]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const nextMsgs: Msg[] = [...messages, { role: 'user', content: text }];
    setMessages(nextMsgs);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/support/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: nextMsgs.map((m) => ({ role: m.role, content: m.content })),
          language: i18n.language || 'en',
        }),
      });
      const data = await res.json();
      setMessages([...nextMsgs, { role: 'assistant', content: data.reply || '…' }]);
      setEscalate(Boolean(data.escalate_to_email));
    } catch {
      setMessages([
        ...nextMsgs,
        {
          role: 'assistant',
          content:
            "I'm unable to reach the AI right now. Please email support@retail-vantag.com and we'll respond within 24 hours.",
        },
      ]);
      setEscalate(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating launcher */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-violet-600 to-purple-700 shadow-xl hover:scale-110 transition-all flex items-center justify-center text-white"
          aria-label="Open support chat"
        >
          <MessageCircle size={24} />
        </button>
      )}

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 w-[22rem] max-w-[calc(100vw-2rem)] h-[32rem] max-h-[calc(100vh-3rem)] bg-[#0a0a0f] border border-violet-500/30 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-violet-600 to-purple-700 px-4 py-3 flex items-center justify-between">
            <div>
              <div className="font-bold text-white">Vantag Assistant</div>
              <div className="text-xs text-white/80">AI support · answers in seconds</div>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white">
              <X size={20} />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#0a0a0f]">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                    m.role === 'user'
                      ? 'bg-violet-600 text-white'
                      : 'bg-white/10 text-white/90 border border-white/10'
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white/60">
                  Thinking…
                </div>
              </div>
            )}
          </div>

          {/* Escalation banner */}
          {escalate && (
            <a
              href="mailto:support@retail-vantag.com"
              className="bg-amber-500/20 text-amber-200 text-xs px-4 py-2 border-t border-amber-500/30 flex items-center gap-2 hover:bg-amber-500/30"
            >
              <Mail size={14} /> Need a human? Email support@retail-vantag.com
            </a>
          )}

          {/* Input */}
          <div className="p-3 border-t border-white/10 flex gap-2 bg-[#0a0a0f]">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send()}
              placeholder="Ask anything…"
              disabled={loading}
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:border-violet-500"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="bg-violet-600 hover:bg-violet-500 disabled:opacity-40 rounded-lg px-3 text-white"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
