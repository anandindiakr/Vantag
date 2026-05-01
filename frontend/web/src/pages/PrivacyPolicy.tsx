import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';

const LAST_UPDATED = '1 May 2026';

export default function PrivacyPolicy() {
  useEffect(() => {
    document.title = 'Privacy Policy | Vantag';
    let m = document.querySelector('meta[name="description"]');
    if (!m) {
      m = document.createElement('meta');
      m.setAttribute('name', 'description');
      document.head.appendChild(m);
    }
    m.setAttribute('content',
      'Vantag Privacy Policy — how we collect, use, store and protect CCTV and personal data under GDPR, DPDP Act (India), PDPA (Singapore) and PDPA (Malaysia).'
    );
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-200">
      <header className="border-b border-white/10 px-6 py-4">
        <Link to="/" className="text-violet-400 hover:text-violet-300 text-sm">&larr; Back to Vantag</Link>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-12 prose prose-invert">
        <h1 className="text-4xl font-bold text-white mb-2">Privacy Policy</h1>
        <p className="text-slate-400 text-sm">Last updated: {LAST_UPDATED}</p>

        <h2 className="text-2xl font-semibold text-white mt-10">1. Who we are</h2>
        <p>Vantag (&quot;we&quot;, &quot;our&quot;, &quot;us&quot;) operates the Vantag Retail Intelligence platform distributed under the brands Vantag (Singapore), Retail Nazar (India) and Retail Jaga Jaga (Malaysia). References to &quot;Platform&quot; include our websites, mobile apps, Edge Agent software and cloud APIs.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">2. What data we collect</h2>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Account data</strong>: name, email, phone, business name, role, preferred language and country.</li>
          <li><strong>Store metadata</strong>: shop name, address, camera labels, zone polygons, floor-plan diagrams you upload.</li>
          <li><strong>Camera data</strong>: RTSP URLs, camera IPs, credentials (encrypted at rest), health-check results.</li>
          <li><strong>Event data</strong>: incident type, timestamp, camera, confidence score, bounding boxes and a short evidence clip (default 10 seconds).</li>
          <li><strong>Billing data</strong>: plan, invoice history, Razorpay payment identifiers. We do NOT store card numbers — Razorpay is PCI-DSS Level 1.</li>
          <li><strong>Technical data</strong>: IP address, browser, device fingerprint, login timestamps, API request logs.</li>
        </ul>
        <p>Raw video footage stays on your Edge device by default. Only short evidence clips attached to a triggered incident are uploaded to our cloud — never continuous recording.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">3. Why we collect it (lawful basis)</h2>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Contract performance</strong> — to operate the service you subscribed to.</li>
          <li><strong>Legitimate interest</strong> — to detect fraud, prevent abuse and secure the Platform.</li>
          <li><strong>Consent</strong> — for marketing emails; you can opt out at any time.</li>
          <li><strong>Legal obligation</strong> — tax records, lawful law-enforcement requests.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">4. How long we keep it</h2>
        <ul className="list-disc pl-6 space-y-1">
          <li>Account data: for the life of your subscription + 7 years for tax records.</li>
          <li>Incident evidence clips: default 30 days, configurable 15–90 days per tenant plan.</li>
          <li>Audit logs: 1 year.</li>
          <li>Backups: 35 days rolling, encrypted.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">5. Who we share it with</h2>
        <p>We do <strong>not</strong> sell your data. We share only with:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>Infrastructure vendors (Hostinger VPS in Singapore/Mumbai) under DPA.</li>
          <li>Razorpay for payment processing.</li>
          <li>Email delivery (SMTP provider) for transactional mail.</li>
          <li>Law-enforcement when compelled by a valid legal order.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">6. Your rights</h2>
        <p>You can request access, correction, deletion, export, or restriction of your personal data at any time by writing to <a className="text-violet-400" href="mailto:privacy@retail-vantag.com">privacy@retail-vantag.com</a>. We respond within 30 days.</p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>India (DPDP Act 2023)</strong>: you are the Data Principal; we are the Data Fiduciary.</li>
          <li><strong>Singapore (PDPA 2012)</strong>: access + correction rights under sections 21 &amp; 22.</li>
          <li><strong>Malaysia (PDPA 2010)</strong>: access + correction rights under sections 30 &amp; 34.</li>
          <li><strong>EU/UK (GDPR/UK-GDPR)</strong>: all Articles 15–22 rights apply.</li>
        </ul>

        <h2 className="text-2xl font-semibold text-white mt-10">7. Security</h2>
        <p>TLS 1.2+ in transit, AES-256 at rest, scrypt-hashed passwords, SOC-2-aligned access controls, quarterly penetration tests, hardware-isolated Edge inference (video never leaves the store unless it becomes an incident).</p>

        <h2 className="text-2xl font-semibold text-white mt-10">8. Cookies</h2>
        <p>We use strictly necessary cookies (auth session, CSRF) and a preference cookie for language/region. No third-party advertising cookies.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">9. Children</h2>
        <p>The Platform is intended for B2B use. We do not knowingly collect data from anyone under 18.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">10. Changes to this policy</h2>
        <p>We will notify account admins by email at least 14 days before any material change. Archived versions are available on request.</p>

        <h2 className="text-2xl font-semibold text-white mt-10">11. Contact &amp; grievance</h2>
        <p>Grievance Officer: <strong>privacy@retail-vantag.com</strong><br/>
        Postal: Vantag Data Protection Office, Singapore &amp; Mumbai offices.</p>
      </main>
    </div>
  );
}
