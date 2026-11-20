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
      {compact ? (
        <Link to="/how-it-works#offline-site-guide" className="inline-block rounded-lg border border-cyan-300/40 px-4 py-3 font-semibold text-cyan-200 hover:bg-cyan-400/10">Read setup, licensing and troubleshooting steps</Link>
      ) : (
        <>
          <h3 className="font-bold text-xl mb-3">From online download to offline monitoring</h3>
          <ol className="list-decimal pl-5 space-y-3 text-sm text-white/75 mb-6">
            <li><strong className="text-white">Prepare on an internet-connected PC.</strong> Sign in to your regional website and open Install Edge Agent / Downloads. Obtain the account-specific offline Windows package when available and the appropriate signed entitlement. If the button says “Under validation”, public download is not enabled; contact your administrator for controlled testing.</li>
            <li><strong className="text-white">Move the complete package to the camera PC.</strong> A USB drive is fine. Extract all files and run VantagAgent.exe from the extracted folder, not inside the ZIP. The Windows package includes its Python runtime and packaged dependencies; do not install Python separately. GPU driver compatibility is a separate requirement, not an automatic driver installation.</li>
            <li><strong className="text-white">Open the local console from the agent.</strong> Use the address opened or shown by the agent, not retail-vantag.com or another public domain. The local port may vary. Create the local owner login on first setup; your website login and NVR password do not sign you into this console.</li>
            <li><strong className="text-white">Set up the site and cameras locally.</strong> In Licence &amp; health, import the signed entitlement if needed and confirm its status. Set the site timezone. Add the camera/NVR IP, RTSP port, username, original password, brand/path and channel. Enter # literally in a separate password field; the app encodes it for the URL. In a manually assembled full RTSP URL, encode # as %23 inside the password only—do not change the NVR password to %23.</li>
            <li><strong className="text-white">Confirm video before enabling AI.</strong> Test the exact stream and verify an actual decoded frame. Ping or “device found” alone does not prove video access. Save each channel once, then draw and save zones, choose detection features and schedules, and start monitoring. Keep the PC awake and the agent running.</li>
            <li><strong className="text-white">Check readiness and test the real scene.</strong> Review model/provider readiness and per-camera diagnostics. Enable fall/theft detection explicitly where needed. Review local incidents and evidence after a controlled test. A loaded model or a demo incident does not establish real fall/theft accuracy; do not stage an unsafe fall.</li>
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
