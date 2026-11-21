import { FormEvent, useEffect, useId, useState } from 'react';

type HelpStatus = {
  licence: { state: string; can_process: boolean };
  runtime: {
    running?: boolean;
    error?: string;
    cameras?: { id: string; connected: boolean; connection_error?: string }[];
    camera_capacity?: { configured: number; connected: number; entitlement_limit: number };
  };
};

const guides = [
  { words: /password|credential|401|403|#|%23|login/i, text: 'Local login is separate from your website account and your NVR account. In camera password fields, type the actual NVR password including #, not %23. Encoding is automatic. A password-free RTSP 401 is only an authentication challenge; an authenticated rejection may mean media permissions, account lockout, the wrong channel or firmware incompatibility. Web login and ping do not prove video access. Use Test saved connection or Read device profiles (ONVIF); do not repeatedly guess passwords.' },
  { words: /camera|channel|rtsp|nvr|connect|offline|three|four|\b[34]\b/i, text: 'Use the recorder LAN IP and recorder credentials when connecting through an NVR, not the camera IP/password. Select its channel and substream. Test video and check the returned picture before saving. A guessed brand path is not verified video. When the brand is unknown, Read device profiles (ONVIF) asks the device for its paths; ONVIF may require a separate enabled account. Saved cards show host and channel to avoid duplicates. Adding a camera does not require stopping other cameras. There is no built-in three-camera cap; licence entitlement, device sessions and PC capacity still apply.' },
  { words: /fall|pose/i, text: 'Enable fall detection for this camera and check Detection readiness for recent pose analysis, not just a connected stream. The candidate detector needs a visible upright-to-horizontal transition; a person already lying down is not an observed fall. Masks and schedules apply. Do not stage a real fall: use safe recorded test footage or supervised professional testing. Field accuracy has not been qualified; this is not a certified safety alarm.' },
  { words: /theft|shoplift|conceal/i, text: 'Enable shoplifting for the intended camera and check its Detection readiness. It currently runs person/object proximity and concealment-pose heuristics, not proof of theft or a qualified local VLM. Shoplifting currently stays enabled outside the general detection schedule. Check exclusion masks and saved evidence. A missing alert is not proof no theft occurred; positive and negative field clips are still required.' },
  { words: /shelf|inventory|box|sku|product/i, text: 'Enable inventory movement, select the saved camera in Zones, draw a tight shelf rectangle, and save. Keep the shelf still while the baseline forms. Test one visible change at a time and review location and before/after evidence in Incidents. People hiding the shelf, lighting and small/distant objects can prevent reliable results. These are visual-change candidates, not exact SKU or inventory-box quantities.' },
  { words: /zone|mask|restrict/i, text: 'In Zones select the saved camera and zone type, drag a rectangle over the image, then save. Changes apply to this camera while other cameras keep running. Exclusion masks suppress detections in their area; avoid masking the test target. For restricted entry, choose Restricted area, draw and save its rectangle, and enable Restricted zone for this camera. First observed person-centre presence creates a review candidate; continuous occupancy is not a fresh entry and identity/access authorization is not checked. Field accuracy is unvalidated.' },
  { words: /count|people|visitor/i, text: 'People count shows the last visible-person sample and tracked appearances, not unique visitors or directional door entries. Check sample time, camera connection and recent inference. Draw a count zone if needed and avoid exclusion masks over the doorway. Compare manual counts against recorded clips; model calls alone do not establish counting accuracy.' },
  { words: /licen[cs]e|renew|device|expir|install|download|start/i, text: 'Download the specific Offline Site Console ZIP, extract all files, and run START-OFFLINE.cmd. Keep _internal beside VantagAgent.exe. Python is bundled; system GPU drivers are not installed or replaced. The browser must open 127.0.0.1, not a public website. Export the device renewal request here, have your administrator issue a signed licence on a connected PC, then import the signed response on this PC. The request is not a licence. Internal team demo licences have no expiry but remain device-bound.' },
  { words: /incident|report|evidence|alert|storage|backup/i, text: 'Incidents lists locally saved candidate alerts; an empty list is not evidence that detection works. Start monitoring, enable the analytic, check its readiness and test using known footage. Check Licence & health and storage errors if evidence is missing. Back up before upgrades and export reports before maintenance. Backups contain private site data; keep them secure. Never delete site data or reset the PC to fix a connection.' },
];

const screenGuide: Record<string, number> = { Login: 0, Cameras: 1, 'Video wall': 1, Zones: 5, 'People count': 6, 'Licence & health': 7, 'Storage & backup': 8, Incidents: 8, Overview: 7 };

export function OfflineContextHelp({ screen, status }: { screen: string; status?: HelpStatus | null }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const panelId = useId();
  useEffect(() => { setQuestion(''); setAnswer(''); }, [screen]);
  const capacity = status?.runtime.camera_capacity;
  const failed = status?.runtime.cameras?.filter(camera => !camera.connected) || [];
  function ask(event: FormEvent) {
    event.preventDefault();
    const match = guides.find(guide => guide.words.test(question));
    setAnswer(match?.text || 'No matching offline guide. Use the guidance for this screen and the downloadable manual, or give support the camera/channel, exact message and test time. Do not share passwords. This helper cannot inspect arbitrary screenshots or invent a diagnosis.');
  }
  return <section className="context-help" aria-label="Offline contextual help">
    <button type="button" className="secondary" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>Help with this screen</button>
    {open && <div id={panelId} className="context-help-body">
      <h2>Current screen: {screen}</h2>
      <p className="subtle">Offline guided assistant · uses this page and current runtime status. No cloud, screenshot upload, local language model or automatic configuration changes.</p>
      {status && <div className="notice"><p>Monitoring: {status.runtime.running ? 'running' : 'stopped'}. Licence: {status.licence.state}.</p>{capacity && <p>{capacity.connected} of {capacity.configured} saved cameras have connected video. Signed monitoring entitlement: {capacity.entitlement_limit}. This is not a measured PC capacity rating.</p>}{!status.licence.can_process && <p>Import a valid signed entitlement in Licence &amp; health before live viewing or processing.</p>}{status.runtime.error && <p>Runtime needs attention. Open Licence &amp; health before relying on new alerts.</p>}{failed.length > 0 && <p>{failed.length} monitored stream(s) have no fresh video. {failed.some(camera => /401|403|auth/i.test(camera.connection_error || '')) ? 'An authentication/access response (401/403) was reported. This does not by itself establish a wrong password; use the saved connection test and ONVIF profiles.' : 'Check the saved connection test for each failed stream before changing brand or channel.'}</p>}</div>}
      <p>{guides[screenGuide[screen] ?? 7].text}</p>
      <form onSubmit={ask}><label>What do you need help with?<input value={question} maxLength={300} onChange={event => setQuestion(event.target.value)} placeholder="For example: password has #, fourth camera, fall detection" required /></label><button type="submit">Show guidance</button></form>
      {answer && <p role="status" className="context-answer">{answer}</p>}
      {screen !== 'Login' && <a href="/assets/vantag-offline-demo-team-manual.html" target="_blank" rel="noreferrer">Open step-by-step offline manual</a>}
    </div>}
  </section>;
}
