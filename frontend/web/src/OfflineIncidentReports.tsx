import { useEffect, useState } from 'react';
import { localApi } from './offlineApi';
import './offlineReports.css';

const eventLabels: Record<string, string> = { count_evidence: 'People detection evidence', fall_detected: 'Fall candidate', crowding: 'Crowding', shoplifting: 'Suspected theft', inventory_movement: 'Inventory movement', restricted_zone: 'Restricted-area entry', loitering: 'Loitering', suspicious_behavior: 'Suspicious behaviour' };
const reviewLabels: Record<string, string> = { candidate: 'Needs review', confirmed: 'Operator confirmed', dismissed: 'Operator dismissed' };
type Incident = { event_id: string; camera_id: string; event_type: string; recorded_at: number; timestamp?: string; confidence?: number; people_visible: number | null; description?: string; verification_state: string; evidence?: Record<string, string>; review: { state: string; note: string; reviewed_at?: number } };
type Report = { items: Incident[]; total: number; page: number; page_size: number; generated_at: number; timezone: string };
const emptyFilters = { q: '', camera_id: '', event_type: '', start_day: '', end_day: '', min_people: '', review_state: '' };

export function IncidentReports({ cameras, site }: { cameras: { id?: string; name: string }[]; site: { name: string; timezone: string } }) {
  const [draft, setDraft] = useState(emptyFilters);
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [report, setReport] = useState<Report | null>(null);
  const [printReport, setPrintReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const query = (pageNumber: number, pageSize: number) => new URLSearchParams(Object.entries({ ...filters, page: String(pageNumber), page_size: String(pageSize) }).filter(([, value]) => value !== '')).toString();
  useEffect(() => {
    const controller = new AbortController();
    let timer = 0;
    const update = async () => {
      try { setReport(await localApi<Report>(`incidents?${query(page, 50)}`, undefined, 'GET', controller.signal)); setError(''); }
      catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Archive could not be loaded'); }
      finally { if (!controller.signal.aborted) timer = window.setTimeout(update, 10000); }
    };
    setReport(null);
    void update();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [filters, page, revision]);
  async function preparePrint() {
    setBusy(true); setError('');
    try { setPrintReport(await localApi<Report>(`incidents?${query(1, 1000)}`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Report preparation failed'); }
    finally { setBusy(false); }
  }
  async function print() {
    await Promise.all(Array.from(document.querySelectorAll<HTMLImageElement>('.incident-report img')).map(image => image.decode().catch(() => undefined)));
    window.print();
  }
  const displayed = printReport || report;
  const formatTime = (timestamp: number) => new Date(timestamp * 1000).toLocaleString(undefined, { timeZone: displayed?.timezone || site.timezone });
  return <section className={`panel incident-report ${printReport ? 'report-print-ready' : ''}`}>
    <div className="report-heading"><div><p className="eyebrow">VANTAG · LOCAL EVIDENCE ARCHIVE</p><h2>Incident report</h2><p>{site.name} · {displayed?.timezone || site.timezone}</p></div><div className="actions report-controls"><button className="secondary" disabled={busy || !report} onClick={() => void preparePrint()}>Prepare print / PDF</button>{printReport && <><button onClick={() => void print()}>Print / Save PDF</button><button className="secondary" onClick={() => setPrintReport(null)}>Return to results</button></>}</div></div>
    <p className="report-caution">Automated alerts are candidates, not proof of theft or a medically confirmed fall. Operator reviews are separate from AI verification. People visible, tracked appearances and incident totals are different measurements.</p>
    <form className="report-filters report-controls" onSubmit={event => { event.preventDefault(); setFilters({ ...draft }); setPage(1); setPrintReport(null); setMessage(''); }}>
      <label>Search saved records<input value={draft.q} maxLength={200} placeholder="Incident ID, camera name or description" onChange={event => setDraft({ ...draft, q: event.target.value })} /></label>
      <label>Incident camera<select value={draft.camera_id} onChange={event => setDraft({ ...draft, camera_id: event.target.value })}><option value="">All cameras</option>{cameras.map(camera => <option key={camera.id} value={camera.id}>{camera.name}</option>)}</select></label>
      <label>Incident type<select value={draft.event_type} onChange={event => setDraft({ ...draft, event_type: event.target.value })}><option value="">All types</option>{Object.entries(eventLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>From date (site time)<input type="date" value={draft.start_day} onChange={event => setDraft({ ...draft, start_day: event.target.value })} /></label>
      <label>To date (site time)<input type="date" value={draft.end_day} onChange={event => setDraft({ ...draft, end_day: event.target.value })} /></label>
      <label>Minimum people visible<input type="number" min={0} max={10000} value={draft.min_people} onChange={event => setDraft({ ...draft, min_people: event.target.value })} /></label>
      <label>Review status<select value={draft.review_state} onChange={event => setDraft({ ...draft, review_state: event.target.value })}><option value="">All review states</option>{Object.entries(reviewLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="actions"><button>Search archive</button><button type="button" className="secondary" onClick={() => { setDraft(emptyFilters); setFilters(emptyFilters); setPage(1); setPrintReport(null); }}>Clear filters</button></div>
    </form>
    {error && <p role="alert" className="error report-controls">{error}</p>}{message && <p role="status" className="success report-controls">{message}</p>}
    {displayed && <><div className="report-summary"><strong data-report-total>{displayed.total} matching records</strong><span>{printReport ? `Print selection: ${displayed.items.length} of ${displayed.total} records. Maximum 1,000; narrow the dates for a larger archive.` : `Page ${page} · up to 50 records per page · refreshes every 10 seconds`}</span><span>Generated: {formatTime(displayed.generated_at)}</span></div><p className="subtle">Filters: {Object.entries(filters).filter(([, value]) => value !== '').map(([key, value]) => `${key.replace(/_/g, ' ')}: ${value}`).join(' · ') || 'All saved records'}. Dates filter the local recording time. A blank people measurement means not measured—not zero.</p>
      {displayed.items.length === 0 && <p>No saved records match these filters. An empty archive does not establish that detection is working.</p>}
      {displayed.items.map(incident => <article className="incident-record" key={incident.event_id}><div className="report-record-heading"><h3>{eventLabels[incident.event_type] || incident.event_type.replace(/_/g, ' ')}</h3><span className={`badge ${incident.review.state === 'confirmed' ? 'good' : 'warning'}`}>{reviewLabels[incident.review.state] || 'Needs review'}</span></div><dl><dt>Incident ID</dt><dd>{incident.event_id}</dd><dt>Camera</dt><dd>{cameras.find(camera => camera.id === incident.camera_id)?.name || `${incident.camera_id} (not in current camera library)`}</dd><dt>Recorded locally</dt><dd>{formatTime(incident.recorded_at)}</dd>{incident.timestamp && <><dt>Source event time</dt><dd>{Number.isNaN(Date.parse(incident.timestamp)) ? 'Unavailable' : new Date(incident.timestamp).toLocaleString(undefined, { timeZone: displayed.timezone })}</dd></>}<dt>People visible</dt><dd>{incident.people_visible ?? 'Not measured'}</dd><dt>Detector score</dt><dd>{typeof incident.confidence === 'number' ? `${(incident.confidence * 100).toFixed(0)}% (model score, not accuracy)` : 'Not measured'}</dd><dt>AI verification</dt><dd>Not visually verified offline</dd>{incident.review.note && <><dt>Operator note</dt><dd>{incident.review.note}</dd></>}{incident.review.reviewed_at && <><dt>Reviewed by local owner</dt><dd>{formatTime(incident.review.reviewed_at)}</dd></>}</dl>{incident.description && <p>{incident.description}</p>}
        <div className="report-evidence">{Object.entries(incident.evidence || {}).map(([label, source]) => source.startsWith('/api/evidence/') ? <figure key={label}><a href={source} target="_blank" rel="noreferrer"><img loading={printReport ? 'eager' : 'lazy'} alt={`Saved evidence: ${label.replace(/_b64$/, '').replace(/[_.]/g, ' ')}`} src={source} /></a><figcaption>{label.replace(/_b64$/, '').replace(/[_.]/g, ' ')}</figcaption></figure> : null)}{!Object.keys(incident.evidence || {}).length && <p className="subtle">No saved image evidence for this record.</p>}</div>
        {!printReport && <ReviewForm incident={incident} onSaved={() => { setMessage('Review saved. This is an operator review, not automated verification.'); setRevision(value => value + 1); }} />}
      </article>)}
      {!printReport && <div className="actions report-controls"><button className="secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous results</button><span>Page {page} of {Math.max(1, Math.ceil(displayed.total / 50))}</span><button className="secondary" disabled={page * 50 >= displayed.total} onClick={() => setPage(page + 1)}>Next results</button></div>}
    </>}
    <footer className="report-footer">Private site evidence · Access restricted to the local owner · Saved records remain available after entitlement expiry.</footer>
  </section>;
}

function ReviewForm({ incident, onSaved }: { incident: Incident; onSaved: () => void }) {
  const [state, setState] = useState(incident.review.state);
  const [note, setNote] = useState(incident.review.note);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <details className="setup-details report-controls"><summary>Review this record</summary><form onSubmit={event => { event.preventDefault(); setBusy(true); setError(''); void localApi(`incidents/${encodeURIComponent(incident.event_id)}/review`, { state, note }).then(onSaved).catch(cause => setError(cause instanceof Error ? cause.message : 'Review could not be saved')).finally(() => setBusy(false)); }}><label>Review state for {incident.event_id}<select value={state} onChange={event => setState(event.target.value)}>{Object.entries(reviewLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Review note for {incident.event_id}<textarea maxLength={2000} value={note} onChange={event => setNote(event.target.value)} /></label><button disabled={busy}>Save review</button>{error && <p role="alert" className="error">{error}</p>}</form></details>;
}
