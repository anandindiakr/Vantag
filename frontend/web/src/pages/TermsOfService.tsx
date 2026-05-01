import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';

const LAST_UPDATED = '1 May 2026';

export default function TermsOfService() {
  useEffect(() => {
    document.title = 'Terms of Service | Vantag';
    let m = document.querySelector('meta[name="description"]');
    if (!m) {
      m = document.createElement('meta');
      m.setAttribute('name', 'description');
      document.head.appendChild(m);
    }
    m.setAttribute('content',
      'Vantag Terms of Service — user obligations, acceptable use, subscription billing, SLA, liability limits and governing law for India, Singapore and Malaysia.'
    );
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-200">
      <header className="border-b border-white/10 px-6 py-4">
        <Link to="/" className="text-violet-400 hover:text-violet-300 text-sm">&larr; Back to Vantag</Link>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-12 prose prose-invert">
        <h1 className="text-4xl font-bold text-white mb-2">Terms of Service</h1>
        <p className="text-slate-400 text-sm">Last updated: {LAST_UPDATED}</p>

        <h2 className="text-2xl font-semibold text-white mt-10">1. Acceptance</h2>
        <p>By creating an account or using the Vantag Platform you (&quot;Customer&quot;) agree to be legally bound by these Terms. If you do not agree, do not use the Platform.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">2. The service</h2>
        <p>Vantag provides a hardware-agnostic retail security and predictive analytics platform comprising: (a) an Edge Agent installed on Customer premises; (b) cloud dashboards and APIs; (c) mobile apps; (d) paid subscription tiers.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">3. Account &amp; security</h2>
        <ul className="list-disc pl-6 space-y-1">
          <li>You must provide accurate registration information.</li>
          <li>You are responsible for every action taken through your account.</li>
          <li>Notify us within 24 hours of any suspected credential compromise.</li>
          <li>You must be 18+ and authorised to bind your business.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">4. Acceptable use</h2>
        <p>You will NOT use the Platform to:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>Record individuals in private areas (toilets, changing rooms, staff break rooms without consent).</li>
          <li>Circumvent local CCTV signage or privacy notification laws.</li>
          <li>Ingest feeds you do not own or have written authorisation to process.</li>
          <li>Reverse-engineer, scrape or resell the service.</li>
          <li>Send abusive, defamatory or unlawful content through our support chat.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">5. Subscription &amp; billing</h2>
        <ul className="list-disc pl-6 space-y-1">
          <li>Plans are monthly/annual, auto-renewing. Prices are shown in local currency (INR, SGD, MYR).</li>
          <li>All prices are exclusive of GST/SST; applicable taxes are added at checkout.</li>
          <li>Payments are processed by Razorpay. Chargebacks incur a flat admin fee.</li>
          <li>You may cancel at any time; no refunds for partial billing periods.</li>
          <li>We may suspend accounts with overdue invoices &gt; 7 days.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">6. Service level (SLA)</h2>
        <p>Cloud dashboard target uptime: <strong>99.5%</strong> monthly, excluding scheduled maintenance announced ≥ 48 hours in advance. Edge Agent continues to operate fully even during cloud outages. Credits for breach: 10% of monthly fee per full 1% below target.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">7. Data</h2>
        <p>You retain all IP in your video footage, camera metadata and configuration. You grant us a limited licence to process that data solely to operate the Platform, per the <Link to="/privacy" className="text-violet-400">Privacy Policy</Link>.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">8. IP &amp; licence</h2>
        <p>The Platform, AI models and Edge Agent binaries remain our property. We grant you a non-exclusive, non-transferable licence to use them strictly for your own retail operations during the subscription term.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">9. Warranty disclaimer</h2>
        <p>The Platform is provided &quot;AS IS&quot; and &quot;AS AVAILABLE&quot;. We do NOT warrant that AI detections are 100% accurate; Customer is responsible for final action on any alert. Vantag is a decision-support tool, not a substitute for trained security personnel or law enforcement.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">10. Limitation of liability</h2>
        <p>Our aggregate liability for any claim is capped at <strong>12 months of fees paid</strong> immediately preceding the event. We are not liable for indirect, consequential, incidental, loss of profit, loss of data or punitive damages.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">11. Indemnity</h2>
        <p>You will indemnify us against third-party claims arising from your unlawful use of the Platform, your breach of these Terms, or your violation of privacy laws in your operating jurisdiction.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">12. Termination</h2>
        <p>Either party may terminate for material breach uncured after 14 days' written notice. On termination, cloud access ceases within 24 hours and data is purged within 90 days unless legal hold applies.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">13. Governing law &amp; venue</h2>
        <ul className="list-disc pl-6 space-y-1">
          <li>India customers (retailnazar.com / .in / .info): laws of India; Mumbai courts.</li>
          <li>Singapore customers (retail-vantag.com): laws of Singapore; SIAC arbitration.</li>
          <li>Malaysia customers (retailjagajaga.com / jagajaga.my): laws of Malaysia; KL courts.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">14. Changes</h2>
        <p>Material changes are notified 30 days in advance. Continued use constitutes acceptance.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">15. Contact</h2>
        <p>Legal: <strong>legal@retail-vantag.com</strong> &nbsp;|&nbsp; Support: <strong>support@retail-vantag.com</strong></p>
      </main>
    </div>
  );
}
