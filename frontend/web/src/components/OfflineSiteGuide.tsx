import { useEffect } from 'react';
import { Link } from 'react-router-dom';

export default function OfflineSiteGuide({ compact = false }: { compact?: boolean }) {
  useEffect(() => {
    if (window.location.hash !== '#offline-site-guide') return;
    const frame = window.requestAnimationFrame(() => document.getElementById('offline-site-guide')?.scrollIntoView());
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <section id="offline-site-guide" aria-labelledby="offline-guide-title" className="scroll-mt-8 mb-12 rounded-2xl border border-cyan-400/25 bg-cyan-400/5 p-5 sm:p-8 text-white">
      <p className="text-xs font-semibold uppercase tracking-widest text-cyan-300 mb-2">Online and offline are different operating modes</p>
      <h2 id="offline-guide-title" className="text-2xl sm:text-3xl font-bold mb-4">Use the website online. Run your site locally offline.</h2>
      <p className="text-white/75 leading-relaxed mb-5">
        Local AI processing is not the same as a fully offline setup. The existing online Edge Agent uses the hosted website for camera setup and remote viewing. The separate Windows Offline Site Console lets you configure LAN cameras, view them and review supported local AI incidents on the agent PC without opening a public website.
      </p>
      <p className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100 mb-6">
        Check Downloads for current availability. Public offline installation remains gated until clean-PC disconnected checks, model redistribution approval and representative fall/theft testing are complete. A demo licence does not bypass these release checks. Do not use the standard online download expecting disconnected onboarding.
      </p>
      <div className="grid md:grid-cols-2 gap-5 mb-6">
        <div>
          <h3 className="font-bold text-lg mb-2">Online Edge Agent + website</h3>
          <p className="text-sm text-white/70 leading-relaxed">Use your website account to configure cameras and access hosted dashboards, remote live viewing and cloud services. The agent PC must reach the cameras over the LAN and the cloud over the internet. An internet outage does not turn this into the Offline Site Console.</p>
        </div>
        <div>
          <h3 className="font-bold text-lg mb-2">Offline Site Console · Windows</h3>
          <p className="text-sm text-white/70 leading-relaxed">Use a separate local owner login on the same PC running the offline agent. Cameras/NVR, PC and LAN must remain powered and connected; public internet is not needed for supported local operation under a valid entitlement. The console is not available on another laptop or phone.</p>
        </div>
      </div>
      <h3 className="font-bold text-lg mb-2">Why use the offline console?</h3>
      <ul className="list-disc pl-5 space-y-2 text-sm text-white/70 mb-6">
        <li>Onboard cameras and run demonstrations at sites without public internet.</li>
        <li>View the video wall and saved local evidence on the site PC without a hosted dashboard.</li>
        <li>Keep site configuration and records locally; transfer renewals by file instead of requiring a cloud check at every startup.</li>
      </ul>
      <div className="flex flex-wrap gap-3 mb-6" aria-label="Demo team manuals">
        <a href="/handouts/vantag-offline-demo-team-manual.pdf" download className="inline-block rounded-lg bg-cyan-300 px-4 py-3 font-semibold text-slate-950">Download offline demo-team manual (PDF)</a>
        <a href="/handouts/vantag-offline-demo-team-manual.html" target="_blank" rel="noreferrer" className="inline-block rounded-lg border border-cyan-300/40 px-4 py-3 font-semibold text-cyan-200">Read the full step-by-step manual</a>
      </div>
      {compact ? (
        <Link to="/how-it-works#offline-site-guide" className="inline-block rounded-lg border border-cyan-300/40 px-4 py-3 font-semibold text-cyan-200 hover:bg-cyan-400/10">Read setup, licensing and troubleshooting steps</Link>
      ) : (
        <>
          <h3 className="font-bold text-xl mb-3">From online download to offline monitoring</h3>
          <ol className="list-decimal pl-5 space-y-3 text-sm text-white/75 mb-6">
            <li><strong className="text-white">Prepare on an internet-connected PC.</strong> Sign in to your regional website and open Install Edge Agent / Downloads. Choose the separate Offline Site Console package when available, not the online Windows agent. If it says “Under validation”, no approved public offline installer is available; ask your administrator about authorised controlled testing. Save the manual before travelling.</li>
            <li><strong className="text-white">Extract the complete package on the camera PC.</strong> Transfer it by USB if needed. Right-click the ZIP → Extract All, wait for completion and run START-OFFLINE.cmd from the extracted folder (or VantagAgent.exe with the supplied offline config.json). Keep _internal beside it. The package carries its own Python runtime; no separate Python installation is required. GPU drivers are not installed automatically.</li>
            <li><strong className="text-white">Create or use the local owner login.</strong> Open the current http://127.0.0.1 address shown by the running agent on that same PC. The port can change; do not use a public website or another laptop. First setup requires a local username and password of at least 12 characters. Save them securely. An existing site needs its existing local owner login, not website or NVR credentials.</li>
            <li><strong className="text-white">Export this PC’s licence request.</strong> Open Licence &amp; health → Export device renewal request. Save vantag-renewal-request.json and transfer it to the administrator’s internet-connected PC. Device ID is generated by the local installation; it is not the NVR IP or customer email.</li>
            <li><strong className="text-white">Administrator: issue the signed response.</strong> On the website open Admin → Offline demos → Import device renewal request (JSON). Select the correct account even if the request has no tenant yet. Confirm the Device ID, choose evaluation days or authorised internal team demo, and set the camera entitlement. Click Issue and download device licence. Copy the downloaded signed response back to the target PC.</li>
            <li><strong className="text-white">Import the response, not the request.</strong> On the target PC use Licence &amp; health → Import signed entitlement JSON. Choose the administrator’s signed licence, normally vantag-demo-entitlement.json. Wait for confirmation and check the licence status. The yellow development warning is separate: a valid licence does not complete release qualification.</li>
            <li><strong className="text-white">Configure site time and each NVR channel.</strong> In Overview save Site name and Timezone. In Cameras enter the actual LAN IP, RTSP port, device username and original password. Type # literally in the separate password field; the wizard encodes it once. Only in an externally assembled full URL does # become %23 inside the password. Select the intended channel/path: Hikvision channel 1 substream commonly uses /Streaming/Channels/102; channel 2 uses /Streaming/Channels/202, not 103. Templates depend on the device.</li>
            <li><strong className="text-white">Verify a real frame, then save.</strong> Click Test decoded video and confirm the intended room. Ping or “device found” is insufficient. Save camera, confirm its channel in Saved cameras and use New camera for the next channel. Unknown brand? Expand Advanced connection tools and read actual ONVIF profiles where supported, or use Auto-detect / diagnose stream. Neither tool bypasses authentication.</li>
            <li><strong className="text-white">Start monitoring and save zones.</strong> In Overview click Start / apply configuration. Use Video wall for simultaneous views. In Zones choose the camera and zone type, drag a rectangle and Save zones. In Cameras → AI detection and schedules select the required features and Save camera. Saves apply while running; only the changed camera reconnects. Enabled theft detection stays active at all times; other enabled functions follow the saved daily schedule.</li>
            <li><strong className="text-white">Validate, record and back up.</strong> Check per-camera readiness, current frames and Licence &amp; health. Run safe controlled positive and negative tests, then review local Incidents, evidence and People count. Record genuine misses and delays; a loaded model or simulated incident is not accuracy proof. Download a private backup from Storage &amp; backup and keep it secure. Offline records do not automatically sync to the website.</li>
          </ol>
          <div className="grid md:grid-cols-2 gap-5 mb-6">
            <div>
              <h3 className="font-bold text-lg mb-2">What stays online?</h3>
              <p className="text-sm text-white/70 leading-relaxed">Account management, package downloads, payments, hosted dashboards, off-site live access, cloud AI/support chat, email, SMS and WhatsApp require internet and their configured services. Offline records do not automatically sync to the website. Advanced AI, face matching, search and assistant features must not be assumed available: only use capabilities shown as ready with qualified packaged models and sufficient hardware.</p>
            </div>
            <div>
              <h3 className="font-bold text-lg mb-2">Customer validity and renewal</h3>
              <p className="text-sm text-white/70 leading-relaxed">A customer entitlement follows the authorised paid/trial/extension period, then seven days of grace. After grace, live viewing and new AI stop; saved records, exports and renewal remain accessible. Export a device request, transfer it to an internet-connected PC, obtain a newer signed entitlement and import it locally. An online extension does not update an isolated PC until the signed file is imported.</p>
            </div>
          </div>
          <details className="rounded-xl border border-white/15 bg-black/20 p-4 mb-4">
            <summary className="cursor-pointer font-semibold">Superadmin: customers, evaluations and internal demo PCs</summary>
            <div className="mt-3 space-y-3 text-sm text-white/75">
              <p>Sign in on the website as your superadmin and open Admin → Offline demos. On the target PC, open Licence &amp; health and export its device renewal request. Transfer the JSON file to the connected PC and choose Import device renewal request (JSON). Select the correct account, confirm Account / tenant ID and Device ID, then choose Usage policy.</p>
              <p>For Customer / dealer evaluation, enter Evaluation days (1–365). For Internal team demo, no expiry date is required. Set Concurrent camera entitlement to the authorised limit—not a hardware capacity promise. Choose Issue and download device licence, transfer the downloaded JSON back and import it in the target PC’s Licence &amp; health page. Confirm the licence status there.</p>
              <p>Use a time-limited evaluation for customers/dealers. Use a permanent internal demo licence only for authorised team demo PCs; non-expiring does not mean transferable to unlimited PCs. Each device needs its own request and licence. This is licence issuance, not an employee-user management screen.</p>
              <p>Use Admin → Tenants for customer accounts and approved access extensions. Offline demo licences do not create employee accounts, mark invoices paid, change subscription/payment dates, or replace tenant and partner management. Do not share your superadmin credentials or a customer-specific package publicly.</p>
            </div>
          </details>
          <details className="rounded-xl border border-white/15 bg-black/20 p-4">
            <summary className="cursor-pointer font-semibold">If the local console or camera does not open</summary>
            <p className="mt-3 text-sm text-white/75 leading-relaxed">Confirm the agent is running and open its current local address on that same PC. If the website fails without internet, use the local console instead. For cameras, verify LAN access, the exact NVR channel/path and RTSP permissions. RTSP 401 means the device rejected authentication/permissions; ping and web login do not prove RTSP access. Try an H.264 sub-stream and close competing viewers when resources are limited. Check diagnostics before assuming that another password encoding or a brand change will fix it.</p>
          </details>
        </>
      )}
    </section>
  );
}
