import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

export default function OfflineDemoTab() {
  const [request, setRequest] = useState({ tenant_id: '', device_id: '' });
  const [kind, setKind] = useState('evaluation');
  const [days, setDays] = useState(30);
  const [limit, setLimit] = useState(8);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [accounts, setAccounts] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    let active = true;
    void axios.get('/api/admin/tenants', { params: { per_page: 100 }, headers: { Authorization: `Bearer ${localStorage.getItem('vantag_token') || ''}` } }).then(({ data }) => { if (active) setAccounts(data.tenants || []); }).catch(() => { if (active) setError('Could not load accounts. Retry this tab or enter a verified tenant ID.'); });
    return () => { active = false; };
  }, []);
  const inputClass = 'w-full bg-slate-900 border border-white/20 rounded-lg p-3 mt-1 text-white';

  async function issue(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      const { data } = await axios.post('/api/agent/offline/admin/demo-entitlement', { ...request, licence_type: kind, days: kind === 'internal_demo' ? null : days, camera_limit: limit }, { headers: { Authorization: `Bearer ${localStorage.getItem('vantag_token') || ''}` } });
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url; link.download = 'vantag-demo-entitlement.json'; document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('Signed device licence downloaded. Import it in the target PC’s Licence & health page. This does not change the customer’s subscription or payment dates.');
    } catch (cause) {
      const detail = axios.isAxiosError(cause) ? cause.response?.data?.detail : null;
      setError(typeof detail === 'string' ? detail : 'Licence issuance failed. Check the request, account status and server signing configuration.');
    } finally { setBusy(false); }
  }

  return <section className="space-y-5 max-w-2xl">
    <h2 className="text-2xl font-bold">Offline demo licences</h2>
    <p className="text-white/70">Superadmin only. Customers retain paid/trial expiry plus seven days of grace. Internal team demos can be non-expiring, but are bound to one PC. Fully offline devices cannot be remotely revoked.</p>
    <p className="text-amber-300">The offline installer remains under validation. Issuing a licence does not qualify model redistribution rights or prove fall/theft accuracy. Do not distribute a live installation containing camera credentials or evidence.</p>
    <Link to="/help#offline-site-guide" className="inline-block text-cyan-300 underline underline-offset-4">Read offline setup, customer renewal and team demo instructions</Link>
    <a href="/handouts/vantag-offline-demo-team-manual.pdf" download className="inline-block text-cyan-300 underline underline-offset-4">Download the demo-team manual (PDF)</a>
    <ol className="list-decimal pl-5 space-y-2 text-sm text-white/75">
      <li>On the target PC: Licence &amp; health → Export device renewal request. Transfer that JSON here using USB or another secure method.</li>
      <li>Import the request below. Device ID identifies the target installation, not its NVR or camera. Select the correct account if no tenant was filled.</li>
      <li>Choose the usage policy and camera entitlement, then issue the signed response. The yellow warning concerns release validation, not a missing form field.</li>
      <li>Return the signed response to that same PC and use Import signed entitlement JSON. Do not import the original request as a licence.</li>
    </ol>
    <form onSubmit={issue} className="space-y-4">
      <fieldset disabled={busy} className="space-y-4">
        <label className="block">Import device renewal request (JSON)<input className={inputClass} type="file" accept=".json,application/json" onChange={event => { const file = event.target.files?.[0]; if (!file) return; setError(''); void (async () => { try { if (file.size > 65536) throw new Error('Request is too large'); const value = JSON.parse(await file.text()); if (value.version !== 1 || value.purpose !== 'offline_entitlement_renewal' || typeof value.device_id !== 'string' || !/^[0-9a-f]{64}$/.test(value.device_id) || (value.tenant_id != null && typeof value.tenant_id !== 'string')) throw new Error('Choose a device renewal request exported from the local console'); setRequest({ device_id: value.device_id, tenant_id: value.tenant_id || '' }); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Invalid request file'); } })(); }} /></label>
        <label className="block">Choose account<select className={inputClass} value={accounts.some(account => account.id === request.tenant_id) ? request.tenant_id : ''} onChange={event => setRequest(current => ({ ...current, tenant_id: event.target.value }))}><option value="">Select an account or enter its ID below</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name} · {account.id}</option>)}</select></label>
        <label className="block">Account / tenant ID<input className={inputClass} value={request.tenant_id} required maxLength={64} onChange={event => setRequest(current => ({ ...current, tenant_id: event.target.value }))} /></label>
        <label className="block">Device ID<input className={inputClass} value={request.device_id} required pattern="[0-9a-f]{64}" onChange={event => setRequest(current => ({ ...current, device_id: event.target.value }))} /></label>
        <label className="block">Usage policy<select className={inputClass} value={kind} onChange={event => setKind(event.target.value)}><option value="evaluation">Customer / dealer evaluation — time limited</option><option value="internal_demo">Internal team demo — no expiry, one PC only</option></select></label>
        {kind === 'evaluation' && <label className="block">Evaluation days<input className={inputClass} type="number" min={1} max={365} required value={days} onChange={event => setDays(Number(event.target.value))} /></label>}
        <label className="block">Concurrent camera entitlement<input className={inputClass} type="number" min={1} max={256} required value={limit} onChange={event => setLimit(Number(event.target.value))} /></label>
        <p className="text-white/60">This is a licence limit, not a hardware capacity guarantee. Start with one camera and confirm actual inference performance.</p>
        <button className="bg-violet-600 rounded-lg px-5 py-3 font-semibold" type="submit">{busy ? 'Signing…' : 'Issue and download device licence'}</button>
      </fieldset>
    </form>
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {message && <p role="status" className="text-emerald-300">{message}</p>}
  </section>;
}
