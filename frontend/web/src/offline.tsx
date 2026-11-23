import React, { FormEvent, useEffect, useId, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { buildStreamPath, inferStreamSetup, rtspPresets } from './rtspPresets';
import './offline.css';
import { OfflineContextHelp } from './OfflineContextHelp';
import { IncidentReports } from './OfflineIncidentReports';
import { PeopleTools } from './OfflinePeopleTools';
import { localApi as api } from './offlineApi';

type Camera = { stream_info?: { host: string; port: number; path: string; path_complete?: boolean; channel: number | null; stream_type: string }; id?: string; name: string; enabled: boolean; person_quality?: { mode: string; confidence: number; confirmation_frames: number }; detections: Record<string, boolean>; detection_schedule: { enabled: boolean; start: string; end: string }; people_count_zones: Zone[]; inventory_zones: Zone[]; restricted_zones?: Zone[]; exclusion_zones: Zone[] };
type Zone = { id: string; bbox: number[]; normalized: boolean; label: string };
type StreamDiagnosis = { success: boolean; path: string | null; thumbnail?: string; message: string; brand_hint?: string | null; failed_stage?: string | null; stages: Record<string, string>; attempts: { candidate: number; status: number | null; authenticated_request: boolean }[] };
type Feedback = { location: string; kind: 'busy' | 'error' | 'success'; text: string } | null;
type DeviceProfiles = { profiles: { token: string; name: string; source: string; width?: string; height?: string }[]; media_endpoint: string; onvif_port: number; message: string; clock_note: string };
type ProbeResult = { success: boolean; thumbnail?: string; message: string };
type Count = { camera_id: string; people_visible: number; entries: number; updated_at: number };
type Status = { licence: { state: string; can_process: boolean; reason?: string; claims?: { expires_at: number | null; licence_type?: string; camera_limit: number } }; site: { name: string; timezone: string }; runtime: { running?: boolean; error?: string; detector?: Record<string, unknown>; calibration?: Record<string, unknown>; cameras?: { id: string; connected: boolean; connection_error?: string; fps: number; frame_age_sec?: number | null; fall_status?: { state: string; error?: string }; theft_status?: { state: string }; inventory_status?: { state: string }; person_quality?: { mode: string; error: string; rejected_this_frame: number; evaluated_at: number | null } }[]; advanced_features?: Record<string, string>; camera_capacity?: { configured: number; enabled: number; monitored: number; connected: number; entitlement_limit: number } } };
const functions = ['people_count', 'shoplifting', 'inventory_movement', 'fall_detected', 'restricted_zone', 'loitering', 'suspicious_behavior', 'crowding'];
const featureLabels: Record<string, string> = { people_count: 'People count', shoplifting: 'Theft / shoplifting candidates', inventory_movement: 'Shelf / inventory movement', fall_detected: 'Fall detection', restricted_zone: 'Restricted area / entry alert', loitering: 'Loitering', suspicious_behavior: 'Suspicious behaviour candidates', crowding: 'Crowding' };
const featureNotes: Record<string, string> = {
  people_count: 'Implemented: visible-person count and tracked appearances; not unique visitors or directional entry/exit. Field accuracy unvalidated.',
  shoplifting: 'Candidate heuristics only: person/object overlap and pose concealment; not proof of theft. Offline VLM verification unavailable.',
  inventory_movement: 'Requires a saved shelf zone and stable baseline. Visual change candidates, not reliable SKU stock or box quantities. Field accuracy unvalidated.',
  fall_detected: 'Pose transition candidates require an observed upright-to-horizontal sequence and working pose inference. Field fall accuracy unvalidated.',
  restricted_zone: 'Person-centre entry/presence candidates in a saved restricted rectangle. Enable the function and draw a restricted zone; not access authorization. Field accuracy unvalidated.',
  loitering: 'Dwell heuristic implemented; site thresholds and field accuracy unvalidated.',
  suspicious_behavior: 'Pacing/direction-change heuristic only; intent cannot be determined. Field accuracy unvalidated.',
  crowding: 'Visible-person threshold heuristic implemented; not calibrated venue capacity or field-validated crowd safety.',
};
const freshCamera = (): Camera => ({ name: '', enabled: true, detections: Object.fromEntries(functions.map(name => [name, false])), detection_schedule: { enabled: false, start: '09:00', end: '18:00' }, people_count_zones: [], inventory_zones: [], restricted_zones: [], exclusion_zones: [] });

function Console() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [setup, setSetup] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState('Overview');
  const [status, setStatus] = useState<Status | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [counts, setCounts] = useState<Count[]>([]);
  const [day, setDay] = useState(new Date().toLocaleDateString('en-CA'));
  const [camera, setCamera] = useState<Camera>(freshCamera());
  const [connection, setConnection] = useState({ ip: '', port: '554', username: '', password: '', path: '/Streaming/Channels/102' });
  const [streamMode, setStreamMode] = useState('hikvision');
  const [channel, setChannel] = useState('1');
  const [streamType, setStreamType] = useState('02');
  const [streamProfile, setStreamProfile] = useState('2');
  const preset = rtspPresets.find(item => item.id === streamMode);
  const [probeResult, setProbeResult] = useState<{ success: boolean; thumbnail?: string; message: string } | null>(null);
  const [diagnosis, setDiagnosis] = useState<StreamDiagnosis | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [onvifPort, setOnvifPort] = useState('0');
  const [deviceProfiles, setDeviceProfiles] = useState<DeviceProfiles | null>(null);
  const [profileToken, setProfileToken] = useState('');
  const [savedTests, setSavedTests] = useState<Record<string, ProbeResult>>({});
  const [selected, setSelected] = useState('');
  const [zoneType, setZoneType] = useState<'people_count_zones' | 'inventory_zones' | 'exclusion_zones' | 'restricted_zones'>('inventory_zones');
  const [tick, setTick] = useState(0);
  const [previewError, setPreviewError] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  const [setupSnapshot, setSetupSnapshot] = useState<{ cameraId: string; source: string } | null>(null);
  const [previewAspect, setPreviewAspect] = useState(16 / 9);
  const [zoneStart, setZoneStart] = useState<number[] | null>(null);
  const [zonesDirty, setZonesDirty] = useState(false);
  const active = !!status?.licence.can_process;
  const cameraForm = React.useRef<HTMLFormElement>(null);
  const activationMessage = status ? `Camera testing and saving require a valid signed offline entitlement for this PC. Licence: ${status.licence.state}. ${status.licence.reason || 'Export this PC’s device renewal request in Licence & health, send it to your administrator, then import the signed response on this PC.'}` : 'The local licence status has not loaded yet. Check that the local agent is running, then open Licence & health. Your entered camera details are kept.';

  function requireCameraAccess() {
    if (!active) throw new Error(activationMessage);
  }

  function beginNewCamera() {
    selectCamera(freshCamera());
    window.requestAnimationFrame(() => cameraForm.current?.querySelector<HTMLInputElement>('input[name="ip"]')?.focus());
  }

  async function action(work: () => Promise<unknown>, success = '', location = tab === 'Cameras' ? 'camera-save' : tab === 'Zones' ? 'zones' : 'global') {
    setBusy(true); setError(''); setMessage('');
    if (location !== 'global') setFeedback({ location, kind: 'busy', text: 'Working on this action…' });
    try {
      const result = await work();
      const text = typeof result === 'string' ? result : success;
      if (location === 'global') setMessage(text);
      else setFeedback(text ? { location, kind: 'success', text } : null);
    } catch (cause) {
      const text = cause instanceof Error ? cause.message : 'Action failed';
      if (location === 'global') setError(text);
      else setFeedback({ location, kind: 'error', text });
    } finally { setBusy(false); }
  }

  async function refresh() {
    const [nextStatus, nextCameras, nextCounts] = await Promise.all([api<Status>('status'), api<Camera[]>('cameras'), api<Count[]>(`counts?day=${encodeURIComponent(day)}`)]);
    setStatus(nextStatus); setCameras(nextCameras); setCounts(nextCounts);
  }

  useEffect(() => {
    api<{ setup_required: boolean }>('bootstrap').then(result => setSetup(result.setup_required)).catch(cause => setError(String(cause)));
    const expired = () => { setLoggedIn(false); setConnection({ ip: '', port: '554', username: '', password: '', path: '/Streaming/Channels/102' }); setProbeResult(null); };
    window.addEventListener('local-session-expired', expired);
    return () => window.removeEventListener('local-session-expired', expired);
  }, []);

  useEffect(() => {
    if (!loggedIn) return;
    let pending = false;
    const update = async () => {
      if (pending) return;
      pending = true;
      try { await refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Local service unavailable'); }
      finally { pending = false; }
    };
    void update();
    const timer = window.setInterval(update, 3000);
    return () => window.clearInterval(timer);
  }, [loggedIn, day]);

  useEffect(() => {
    if (!active || !selected || (tab !== 'Cameras' && tab !== 'Zones')) return;
    const timer = window.setInterval(() => { setTick(value => value + 1); setPreviewError(false); }, 1500);
    return () => window.clearInterval(timer);
  }, [active, selected, tab]);

  async function saveCamera(saved: Camera, rtspUrl = '') {
    requireCameraAccess();
    if (!saved.name.trim()) throw new Error('Enter a Camera name before saving.');
    const creating = !saved.id;
    const { stream_info: _streamInfo, ...configuration } = saved;
    if (tab === 'Cameras' && !rtspUrl && saved.stream_info && (connection.path !== saved.stream_info.path || connection.port !== String(saved.stream_info.port))) throw new Error('To change the saved channel/path or port, enter the device IP, username and actual password. No changes were saved.');
    const result = await api<{ id: string; applied: boolean; application_error: boolean; message: string }>('cameras', { ...configuration, rtsp_url: rtspUrl });
    if (creating) {
      setCamera(freshCamera()); setSelected(''); setProbeResult(null);
      if (preset?.channelMax) channelPath(String(Math.min(preset.channelMax, Number(channel) + 1)), streamType);
    } else {
      const updated = (await api<Camera[]>('cameras')).find(item => item.id === result.id);
      setCamera(updated || { ...saved, id: result.id }); setSelected(result.id);
    }
    setZonesDirty(false);
    await refresh();
    if (result.application_error) throw new Error(result.message);
    return creating ? `${saved.name} added as a separate camera. ${result.message} Ready to add the next channel.` : result.message;
  }

  function stream(detection = false) {
    requireCameraAccess();
    const ip = connection.ip.trim();
    if (!ip) throw new Error('Enter the NVR LAN IP address before testing video. The grey example is not an entered address.');
    const host = ip.includes(':') ? `[${ip.replace(/^\[|\]$/g, '')}]` : ip;
    if (/[/@?#\s]/.test(ip)) throw new Error('Enter only the NVR IP address, without rtsp://, a port or a path.');
    let validAddress = false;
    if (ip.includes(':')) {
      try { validAddress = new URL(`http://${host}`).hostname.startsWith('['); } catch { validAddress = false; }
    } else {
      const octets = ip.split('.');
      validAddress = octets.length === 4 && octets.every(octet => /^(0|[1-9]\d{0,2})$/.test(octet) && Number(octet) <= 255);
    }
    if (!validAddress) throw new Error('Enter a valid NVR IPv4 or IPv6 address, for example 192.168.1.102.');
    const port = Number(connection.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Enter an RTSP port from 1 to 65535 (usually 554).');
    if (!connection.username || !connection.password) throw new Error('Enter the NVR username and actual password to test or replace the stream. Use # as typed, not %23.');
    if (!detection && preset?.profile === 'number' && !/^[1-9]\d{0,2}$/.test(streamProfile)) throw new Error('Enter the actual configured profile number (1 to 999).');
    if (!detection && preset?.profile === 'token' && !/^[A-Za-z0-9_.-]{1,100}$/.test(streamProfile)) throw new Error('Enter the actual media-profile token from this camera, not an example token.');
    const path = connection.path || (detection ? '/' : '');
    if (!path.startsWith('/') || /[\s#]/.test(path)) throw new Error('The RTSP path must start with / and contain no spaces or #.');
    return `rtsp://${encodeURIComponent(connection.username)}:${encodeURIComponent(connection.password)}@${host}:${port}${path}`;
  }

  function changeConnection(update: Partial<typeof connection>) {
    setConnection(current => ({ ...current, ...update })); setProbeResult(null); setDiagnosis(null); setMessage(''); setError(''); setFeedback(null); setDeviceProfiles(null); setProfileToken('');
  }

  async function testSavedCamera(item: Camera) {
    setSavedTests(current => { const next = { ...current }; delete next[item.id!]; return next; });
    const result = await api<ProbeResult>(`cameras/${item.id}/test`, {});
    setSavedTests(current => ({ ...current, [item.id!]: result }));
    if (!result.success) throw new Error(result.message);
    return result.message;
  }

  async function detectStream() {
    setDiagnosis(null); setProbeResult(null);
    const url = stream(true);
    const selectedChannel = Number(channel);
    if (!Number.isInteger(selectedChannel) || selectedChannel < 1 || selectedChannel > 256) throw new Error('Choose a detection channel from 1 to 256.');
    setDetecting(true);
    try {
      const result = await api<StreamDiagnosis>('auto-detect', { rtsp_url: url, channel: selectedChannel });
      if (result.success && result.path) {
        setStreamMode('custom');
        setConnection(current => ({ ...current, path: result.path! }));
      }
      setDiagnosis(result);
    } finally { setDetecting(false); }
  }

  async function readDeviceProfiles() {
    setDeviceProfiles(null); setProfileToken(''); setDiagnosis(null); setProbeResult(null);
    const port = Number(onvifPort);
    if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Enter the ONVIF HTTP service port, or 0 to check common service ports without credentials first.');
    const result = await api<DeviceProfiles>('onvif/profiles', { rtsp_url: stream(true), onvif_port: port });
    setDeviceProfiles(result); setOnvifPort(String(result.onvif_port));
    return result.message;
  }

  async function testDeviceProfile() {
    if (!deviceProfiles || !profileToken) throw new Error('Read device profiles and choose the intended source/profile first.');
    setProbeResult(null); setDiagnosis(null);
    const result = await api<{ success: boolean; path: string | null; port: number; thumbnail?: string; message: string }>('onvif/test-profile', { rtsp_url: stream(true), onvif_port: Number(onvifPort), media_endpoint: deviceProfiles.media_endpoint, profile_token: profileToken });
    if (result.success && result.path) {
      setStreamMode('custom');
      setConnection(current => ({ ...current, path: result.path!, port: String(result.port) }));
    }
    setProbeResult(result);
    if (!result.success) throw new Error(result.message);
    return result.message;
  }

  function channelPath(nextChannel: string, nextType: string, mode = streamMode, profile = streamProfile) {
    setChannel(nextChannel); setStreamType(nextType); setStreamProfile(profile);
    changeConnection({ path: buildStreamPath(mode, nextChannel, nextType, profile) });
  }

  function selectCamera(item: Camera) {
    if (busy) return;
    setDiagnosis(null); setFeedback(null); setDeviceProfiles(null); setProfileToken('');
    if (item.id !== camera.id || !item.id) {
      const info = item.stream_info;
      const savedPath = info?.path || '/Streaming/Channels/102';
      const setup = inferStreamSetup(savedPath);
      setConnection({ ip: '', port: String(info?.port || 554), username: '', password: '', path: savedPath });
      setChannel(setup.channel); setStreamType(setup.stream); setStreamMode(info?.path_complete === false ? 'custom' : setup.mode); setStreamProfile(setup.profile); setProbeResult(null);
    }
    setCamera({ ...freshCamera(), ...item }); setSelected(item.id || ''); setPreviewError(false); setPreviewLoaded(false); setSetupSnapshot(null); setZonesDirty(false); setZoneStart(null); setMessage(''); setError('');
  }

  function finishZone(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!zoneStart) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const end = [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
    const box = [Math.min(zoneStart[0], end[0]), Math.min(zoneStart[1], end[1]), Math.max(zoneStart[0], end[0]), Math.max(zoneStart[1], end[1])];
    setZoneStart(null);
    if (box[2] - box[0] < 0.02 || box[3] - box[1] < 0.02) return;
    setZonesDirty(true); setMessage('');
    setCamera(current => ({ ...current, [zoneType]: [...(current[zoneType] || []), { id: crypto.randomUUID(), bbox: box, normalized: true, label: `${zoneType === 'inventory_zones' ? 'Shelf' : zoneType === 'exclusion_zones' ? 'Exclude' : zoneType === 'restricted_zones' ? 'Restricted' : 'Count'} ${(current[zoneType] || []).length + 1}` }] }));
  }

  const snapshot = tab === 'Zones' && setupSnapshot?.cameraId === selected ? setupSnapshot.source : '';
  const preview = selected && active ? <div className="preview editor-preview" style={{ width: Math.min(960, 320 * previewAspect), maxWidth: '100%', minHeight: previewLoaded ? 0 : 180, aspectRatio: String(previewAspect) }}><img alt="Latest locally decoded camera frame" src={snapshot || `/api/frame/${encodeURIComponent(selected)}?t=${tick}`} onLoad={event => { setPreviewError(false); setPreviewLoaded(true); if (event.currentTarget.naturalHeight) setPreviewAspect(event.currentTarget.naturalWidth / event.currentTarget.naturalHeight); }} onError={() => { setPreviewError(true); setPreviewLoaded(false); }} />{(!previewLoaded || previewError) && <p className="preview-warning">{tab === 'Zones' ? 'No camera image loaded. Choose Load camera image below to draw zones without starting monitoring, or start monitoring for live video.' : 'No recent video frame. Start monitoring or use Test saved to check the camera.'}</p>}{!previewError && <svg className="zone-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label="Camera zone outlines">{(['inventory_zones', 'people_count_zones', 'exclusion_zones', 'restricted_zones'] as const).flatMap(type => (camera[type] || []).map(zone => { const [left, top, right, bottom] = zone.bbox; const color = type === 'inventory_zones' ? '#fbbf24' : type === 'people_count_zones' ? '#2dd4bf' : type === 'restricted_zones' ? '#c084fc' : '#f87171'; return <g key={`${type}-${zone.id}`}><rect x={left * 1000} y={top * 1000} width={(right - left) * 1000} height={(bottom - top) * 1000} stroke={color} strokeWidth="3" vectorEffect="non-scaling-stroke" fill={color} fillOpacity="0.08" /><text x={left * 1000 + 8} y={top * 1000 + 32} fill={color} stroke="#020617" strokeWidth="3" paintOrder="stroke" fontSize="28">{zone.label}</text></g>; }))}</svg>}{tab === 'Zones' && previewLoaded && !previewError && <canvas width={640} height={360} aria-label="Drag to draw a rectangular zone over the camera image" onPointerDown={event => { const rect = event.currentTarget.getBoundingClientRect(); event.currentTarget.setPointerCapture(event.pointerId); setZoneStart([(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height]); }} onPointerUp={finishZone} onPointerCancel={() => setZoneStart(null)} />}</div> : <p>Select a saved camera with an active entitlement to view video.</p>;

  if (!loggedIn) return <main className="login-shell"><section className="panel login"><p className="eyebrow">VANTAG · OFFLINE SITE CONSOLE</p><h1>{setup ? 'Set up this PC' : 'Welcome back'}</h1><p>Your cameras, configuration and evidence stay on this computer. No internet login required.</p><form onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); void action(async () => { await api(setup ? 'setup' : 'login', { username: data.get('username'), password: data.get('password') }); setLoggedIn(true); setSetup(false); }); }}><label>Local username<input name="username" required autoComplete="username" maxLength={100} /></label><PasswordField label="Local password" name="password" minLength={setup ? 12 : 1} maxLength={256} required autoComplete={setup ? 'new-password' : 'current-password'} /><button disabled={busy}>{setup ? 'Create local owner' : 'Sign in locally'}</button></form>{error && <p role="alert" className="error">{error}</p>}<OfflineContextHelp screen="Login" /><p className="subtle">Development build. Not a validated offline release.</p></section></main>;

  return <div className="console-shell"><aside><div className="brand">VANTAG<span>Offline Site Console</span></div><nav>{['Overview', 'Video wall', 'Cameras', 'AI functions', 'Zones', 'People count', 'Incidents', 'People tools', 'Storage & backup', 'Licence & health'].map(name => <button key={name} className={tab === name ? 'selected' : ''} onClick={() => setTab(name)}>{name}</button>)}</nav><p className="subtle">Local PC only<br />No cloud connection<br /><small>Camera setup fix · 23 Nov 2026</small></p><button onClick={() => void action(async () => { await api('logout', {}); window.dispatchEvent(new Event('local-session-expired')); })}>Sign out</button></aside><main><header><div><p className="eyebrow">LOCAL OPERATIONS</p><h1>{status?.site.name || 'Your site'}</h1><p>{tab}</p></div><span className={`badge ${active ? 'good' : 'warning'}`}>Licence: {status?.licence.state || 'checking'}</span><OfflineContextHelp screen={tab} status={status} /></header><div className="notice">Development build · Core local workflows are under validation. Advanced AI is not advertised as available.</div>{error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="success">{message}</p>}
    {tab === 'Overview' && <><section className="metrics"><article className="panel"><p>Configured cameras</p><strong>{cameras.length}</strong></article><article className="panel"><p>Connected video streams</p><strong>{status?.runtime.cameras?.filter(item => item.connected).length ?? 0}</strong></article><article className="panel"><p>Monitoring</p><strong>{status?.runtime.running ? 'Running' : 'Stopped'}</strong></article></section><section className="panel"><h2>Site settings</h2><form key={status?.site.name} onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); void action(async () => { await api('site', { name: data.get('name'), timezone: data.get('timezone') }); await refresh(); }, 'Site saved'); }}><label>Site name<input name="name" defaultValue={status?.site.name} required /></label><label>Timezone<input name="timezone" defaultValue={status?.site.timezone || 'Asia/Singapore'} required placeholder="Asia/Jakarta" /></label><button disabled={busy}>Save site</button></form></section><section className="panel"><h2>Monitoring controls</h2><p>Camera and zone saves apply automatically while monitoring is running. Only the changed camera reconnects. If monitoring is stopped, use Start below.</p><div className="actions"><button disabled={!active || busy} onClick={() => void action(async () => { await api('monitoring/start', {}); await refresh(); }, 'Monitoring started')}>Start / apply configuration</button><button className="secondary" disabled={busy} onClick={() => void action(async () => { await api('monitoring/stop', {}); await refresh(); })}>Stop monitoring</button></div></section></>}
    {tab === 'Video wall' && <VideoWall cameras={cameras} runtimeCameras={status?.runtime.cameras || []} active={active} running={!!status?.runtime.running} busy={busy} onEditAi={item => { selectCamera(item); setTab('AI functions'); }} onConfigure={item => { selectCamera(item); setTab('Cameras'); }} onStart={() => void action(() => api('monitoring/start', {}), 'Monitoring started')} onStop={() => void action(() => api('monitoring/stop', {}), 'Monitoring stopped')} />}

    {tab === 'Cameras' && <div className="two-column camera-layout"><section className="panel"><h2>{camera.id ? `Editing: ${camera.name}` : 'Add an NVR channel'}</h2><p className="notice">{camera.id ? 'Saving updates this camera only. To add another channel, choose New camera below.' : 'New camera mode: saving creates a separate record and prepares the next channel. Use Test saved beside an existing camera to check its connection without retyping its password.'}</p><p>Use the NVR account and actual password, including #. The wizard encodes credentials once; do not replace # with %23 here.</p><form ref={cameraForm} key={camera.id || 'new'} onInvalid={event => { const input = event.target as HTMLInputElement; if (event.currentTarget.querySelector('input:invalid, select:invalid') === input) setFeedback({ location: 'camera-save', kind: 'error', text: `${input.name === 'name' ? 'Camera name' : input.name === 'ip' ? 'NVR / camera LAN IP' : 'Camera field'}: ${input.validationMessage}` }); }} onSubmit={event => { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); void action(async () => { const saved = { ...camera, name: String(data.get('name') || '') }; if (!connection.ip.trim() && (connection.username || connection.password)) throw new Error('Enter the NVR IP address together with the replacement credentials, or clear the username and password to keep the saved connection.'); return saveCamera(saved, connection.ip.trim() || !camera.id ? stream() : ''); }); }}><fieldset disabled={busy}><div className="section-kicker">Connection details</div><label>Camera name<input name="name" value={camera.name} onChange={event => setCamera(current => ({ ...current, name: event.target.value }))} required maxLength={200} /></label><div className="form-grid"><label>NVR / camera LAN IP<input name="ip" placeholder="Example only: 192.168.1.102" value={connection.ip} onChange={event => changeConnection({ ip: event.target.value })} required={!camera.id} /></label><label>RTSP port<input name="port" type="number" value={connection.port} onChange={event => changeConnection({ port: event.target.value })} min={1} max={65535} /></label><label>NVR username<input name="username" value={connection.username} onChange={event => changeConnection({ username: event.target.value })} autoComplete="off" /></label><PasswordField label="Actual NVR password" name="password" value={connection.password} onChange={event => changeConnection({ password: event.target.value })} autoComplete="new-password" /></div><label>Stream setup<select value={streamMode} onChange={event => { const mode = event.target.value; setStreamMode(mode); setProbeResult(null); const chosen = rtspPresets.find(item => item.id === mode); if (chosen) channelPath(String(Math.min(Number(channel) || 1, chosen.channelMax || 1)), streamType, mode, chosen.profile === 'number' ? '2' : ''); else if (mode === 'onvif') changeConnection({ path: '' }); }}>{rtspPresets.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}<option value="onvif">ONVIF / device-provided RTSP path</option><option value="custom">Custom RTSP path / another brand</option></select></label><div className="form-grid">{preset?.channelMax && <label>NVR channel / video source<select value={channel} onChange={event => channelPath(event.target.value, streamType)}>{Array.from({ length: preset.channelMax }, (_, index) => <option key={index + 1} value={index + 1}>Channel {index + 1}</option>)}</select></label>}{preset?.streams && <label>Video stream<select value={streamType} onChange={event => channelPath(channel, event.target.value)}><option value="02">Stream 2 / substream (device settings apply)</option><option value="01">Stream 1 / main stream (device settings apply)</option></select></label>}{preset?.profile && <label>{preset.profile === 'number' ? 'Configured profile number' : 'Actual media-profile token'}<input value={streamProfile} required type={preset.profile === 'number' ? 'number' : 'text'} min={preset.profile === 'number' ? 1 : undefined} max={preset.profile === 'number' ? 999 : undefined} maxLength={100} onChange={event => channelPath(channel, streamType, streamMode, event.target.value)} /></label>}</div><label>RTSP path<input name="path" value={connection.path} readOnly={!!preset} onChange={event => changeConnection({ path: event.target.value })} /></label><p className="subtle">{preset ? preset.note : streamMode === 'onvif' ? 'ONVIF is a discovery/control protocol, not a universal RTSP path. Copy the exact RTSP path and port returned by your device’s GetStreamUri or supplied in its manual. /onvif/device_service is an HTTP service, not a video URL.' : 'Use the exact path and query parameters from the device manual. Choosing a brand does not identify the device automatically.'}</p>{preset && <p className="subtle">Manufacturer-documented template; not hardware-tested for every model. Only a successful Test decoded video verifies this device, path and credentials. <a href={preset.source} target="_blank" rel="noreferrer">Manufacturer reference (internet required)</a></p>}<p className="subtle">Non-Chinese brand options include Axis, Hanwha Vision, Bosch, i-PRO, VIVOTEK and Avigilon. Procurement compliance depends on the exact model and local rules, not the brand label alone.</p>{camera.stream_info?.path_complete === false && <p className="warning">Some saved query parameters are hidden for security. Leave IP blank to preserve the full protected connection. To replace it, enter the complete device-supplied path and credentials.</p>}{camera.id && <p>Leave IP blank to keep the saved protected stream credentials.</p>}<details className="setup-details"><summary>Advanced connection tools</summary><p className="subtle">Use these only when the normal video test fails. Saved-camera testing is available beside each saved camera.</p><section aria-label="Automatic stream detection"><h3>Find a working RTSP path</h3><p>Tests this IP and port only. Stops at authentication rejection; never guesses passwords. A brand hint is not confirmed manufacturer identification. At most 10 candidate paths; usually under 30 seconds.</p><label>Channel for automatic detection<input type="number" min={1} max={256} value={channel} onChange={event => { setChannel(event.target.value); setDiagnosis(null); }} /></label><button type="button" className="secondary" disabled={!active || busy} onClick={() => void action(detectStream, '', 'detect')}>{detecting ? 'Detecting stream…' : 'Auto-detect / diagnose stream'}</button>{detecting && <p role="status">Checking RTSP response, account access, candidate paths and actual video decoding. No settings are saved automatically.</p>}<LocalFeedback feedback={feedback} location="detect" />{diagnosis && <StreamDiagnosisPanel result={diagnosis} />}</section><section className="onvif-panel" aria-label="Device-reported stream profiles"><h3>Unknown brand? Read actual device profiles (ONVIF)</h3><p>Reads video profiles advertised by this device, without guessing its brand. ONVIF must be enabled; some recorders require a separate ONVIF user with live-view rights. This does not change recorder settings.</p><label>ONVIF HTTP service port (0 = discover)<input type="number" min={0} max={65535} value={onvifPort} onChange={event => { setOnvifPort(event.target.value); setDeviceProfiles(null); setProfileToken(''); }} /></label><button type="button" className="secondary" disabled={!active || busy} onClick={() => void action(readDeviceProfiles, '', 'onvif')}>Read device profiles</button>{deviceProfiles && <><p>{deviceProfiles.clock_note}</p><label>Device video source / profile<select value={profileToken} onChange={event => { setProfileToken(event.target.value); setProbeResult(null); }}><option value="">Choose the intended camera profile</option>{deviceProfiles.profiles.map(profile => <option key={profile.token} value={profile.token}>{profile.name} · Source {profile.source}{profile.width ? ` · ${profile.width}×${profile.height}` : ''}</option>)}</select></label><button type="button" className="secondary" disabled={!active || busy || !profileToken} onClick={() => void action(testDeviceProfile, '', 'onvif')}>Test selected profile</button></>}<LocalFeedback feedback={feedback} location="onvif" /><p className="subtle">Only a decoded frame confirms success. Review the resulting path and preview before saving. Rejection does not prove your web-login password is wrong; check account and RTSP/ONVIF permissions.</p></section></details><details className="setup-details"><summary>AI detection and schedules</summary><CameraAiSettings camera={camera} onChange={setCamera} /></details>{!active && <section className="notice" role="region" aria-label="Camera activation required"><h3>{status ? `Camera activation required · ${status.licence.state}` : 'Checking local device activation'}</h3><p>{activationMessage}</p><p>You can enter camera details now. Website login does not activate this offline PC. Keep this form open while obtaining the signed licence; do not reinstall or delete your site.</p><button className="secondary" type="button" onClick={() => setTab('Licence & health')}>Open device activation</button></section>}<div className="actions"><button disabled={busy}>Save camera</button><button className="secondary" type="button" disabled={busy} onClick={() => { setProbeResult(null); void action(async () => { const result = await api<{ success: boolean; thumbnail?: string; message: string }>('probe', { rtsp_url: stream() }); setProbeResult(result); }); }}>{busy ? 'Please wait…' : 'Test decoded video'}</button><button type="button" className="secondary" disabled={busy} onClick={beginNewCamera}>New camera</button></div><LocalFeedback feedback={feedback} location="camera-save" />{probeResult && <div role={probeResult.success ? 'status' : 'alert'} className={probeResult.success ? 'success' : 'error'}><p>{probeResult.message}{probeResult.success ? '. This confirms video decoding, not AI accuracy. Save the camera to apply it automatically if monitoring is running; otherwise start monitoring on Overview.' : ' A reachable NVR alone does not confirm video. Check RTSP permissions and try another channel or stream.'}</p>{probeResult.success && probeResult.thumbnail && <img alt="Frame decoded during this connection test" style={{ maxWidth: '100%' }} src={`data:image/jpeg;base64,${probeResult.thumbnail}`} />}</div>}</fieldset></form></section><section><div className="panel"><div className="section-heading"><div><div className="section-kicker">Camera library</div><h2>Saved cameras</h2></div><span className="pill">{cameras.length} saved</span></div><div className="library-summary"><span className={`status-dot ${status?.runtime.running ? 'online' : ''}`} /><strong>{status?.runtime.running ? `${status.runtime.cameras?.filter(item => item.connected).length || 0} cameras streaming` : 'Monitoring is stopped'}</strong><span>{status?.licence.claims?.camera_limit ? `Entitlement: ${status.licence.claims.camera_limit} concurrent cameras` : 'Capacity follows the imported entitlement'}</span></div><div className="actions"><button className="secondary" disabled={!active || busy} onClick={() => void action(() => api('monitoring/start', {}), 'Monitoring started. Waiting for decoded video.', 'camera-library')}>Start monitoring</button><button className="secondary" onClick={() => setTab('Video wall')}>Open video wall</button></div><LocalFeedback feedback={feedback} location="camera-library" />{cameras.map(item => { const live = status?.runtime.cameras?.find(entry => entry.id === item.id); return <div className={`camera-row ${camera.id === item.id ? 'selected' : ''}`} key={item.id}><div className="camera-row-heading"><button className="secondary camera-name" onClick={() => selectCamera(item)}>{item.name}</button><span className={`stream-state ${live?.connected ? 'is-live' : ''}`}>{!item.enabled ? 'Disabled' : live?.connected ? 'Live' : status?.runtime.running ? 'No video' : 'Stopped'}</span></div><span className="stream-identity">{item.stream_info ? `${item.stream_info.host}:${item.stream_info.port} · ${item.stream_info.channel === null ? 'Custom path' : `Channel ${item.stream_info.channel}`} · ${item.stream_info.stream_type} · ${item.stream_info.path}` : 'No connected video'}</span>{live?.connection_error && <p className="camera-reason">{live.connection_error}</p>}<div className="camera-actions"><button className="secondary" disabled={busy} aria-label={`Edit AI ${item.name}`} onClick={() => { selectCamera(item); setTab('AI functions'); }}>Edit AI functions</button><button className="secondary" disabled={busy} aria-label={`Edit zones ${item.name}`} onClick={() => { selectCamera(item); setTab('Zones'); }}>Edit zones</button><button className="secondary" disabled={!active || busy} aria-label={`Test saved ${item.name}`} onClick={() => void action(() => testSavedCamera(item), '', `saved-${item.id}`)}>Test saved</button><button className="danger" disabled={!active || busy} aria-label={`Remove ${item.name}`} onClick={() => { if (window.confirm(`Remove ${item.name}? Other cameras will keep running. Saved incidents will remain available.`)) void action(() => api(`cameras/${item.id}`, {}, 'DELETE'), 'Camera removed; other streams were left running.', 'camera-library'); }}>Remove</button></div><LocalFeedback feedback={feedback} location={`saved-${item.id}`} />{savedTests[item.id!]?.thumbnail && <img className="saved-test-preview" src={`data:image/jpeg;base64,${savedTests[item.id!].thumbnail}`} alt={`${item.name} decoded test frame`} />}</div>; })}{cameras.length === 0 && <div className="empty-state"><h3>No cameras saved yet</h3><p>Add a connection, test its video, then save it.</p></div>}</div>{preview}{selected && <section className="panel" aria-label="Selected camera analytics"><h3>Detection readiness</h3>{(['fall_status', 'theft_status', 'inventory_status'] as const).map((key, index) => <p key={key}><strong>{['Fall', 'Theft', 'Shelf'][index]}: </strong>{status?.runtime.cameras?.find(item => item.id === selected)?.[key]?.state || 'Monitoring not running for this camera'}</p>)}<p>Enable the required AI functions above and save. Shelf detection also needs a saved shelf zone. Test one camera first; enabling a function does not validate its accuracy.</p></section>}</section></div>}
    {tab === 'AI functions' && <section className="panel"><h2>{selected ? `AI functions for ${camera.name}` : 'AI functions'}</h2><p>Select a saved camera, choose its AI functions, then save. You do not need to add the camera again or re-enter its password. While monitoring runs, only this camera applies the change; other cameras keep running.</p><label>Camera<select aria-label="Camera" value={selected} disabled={busy} onChange={event => { const item = cameras.find(entry => entry.id === event.target.value); selectCamera(item || freshCamera()); }}><option value="">Select a camera</option>{cameras.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{selected ? <form onSubmit={event => { event.preventDefault(); void action(() => saveCamera(camera), '', 'ai'); }}><fieldset disabled={!active || busy}><CameraAiSettings camera={camera} onChange={setCamera} /><div className="actions"><button>Save AI functions</button><button type="button" className="secondary" onClick={() => setTab('Zones')}>Edit zones for {camera.name}</button></div></fieldset><LocalFeedback feedback={feedback} location="ai" /><h3>Detection readiness</h3>{(['fall_status', 'theft_status', 'inventory_status'] as const).map((key, index) => <p key={key}><strong>{['Fall', 'Theft', 'Shelf'][index]}: </strong>{status?.runtime.cameras?.find(item => item.id === selected)?.[key]?.state || 'Monitoring not running for this camera'}</p>)}<p className="notice">Fall and theft detection produce review candidates, not guaranteed alarms or proof of theft. Their field accuracy is not qualified. Fall/theft use the camera view minus exclusion masks; they are AI switches, not separate zone types. Shelf and restricted-entry detection require their corresponding saved zones.</p></form> : <p>Save a camera in Cameras first, then select it here.</p>}</section>}
    {tab === 'Zones' && <section className="panel"><h2>Camera zones</h2><label>Camera<select aria-label="Camera" value={selected} disabled={busy} onChange={event => { const item = cameras.find(entry => entry.id === event.target.value); selectCamera(item || freshCamera()); }}><option value="">Select a camera</option>{cameras.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Zone type<select aria-label="Zone type" value={zoneType} onChange={event => setZoneType(event.target.value as typeof zoneType)}><option value="inventory_zones">Shelf / inventory</option><option value="people_count_zones">People count</option><option value="restricted_zones">Restricted area / entry alert</option><option value="exclusion_zones">Exclude from detection</option></select></label><p>Drag a rectangle, then Save zones. Yellow: inventory; teal: people count; purple: restricted entry; red: exclusion. Enable the corresponding AI function. Help with this screen explains limits.</p>{zonesDirty && <p className="warning">Unsaved zone changes</p>}{snapshot && <p className="notice">Frozen setup image, not live video. Use Load camera image again to refresh it. Saving zones does not start monitoring.</p>}{preview}<div className="actions"><button className="secondary" disabled={!active || !selected || busy} onClick={() => void action(async () => { const cameraId = selected; const result = await api<ProbeResult>(`cameras/${encodeURIComponent(cameraId)}/test`, {}); if (!result.success || !result.thumbnail) throw new Error(result.message || 'No decoded image returned. Check this camera in Cameras.'); setSetupSnapshot({ cameraId, source: `data:image/jpeg;base64,${result.thumbnail}` }); setPreviewError(false); return 'Setup snapshot loaded. This is a still image, not live video. Draw your zones and save.'; }, '', 'zones')}>Load camera image</button><button className="secondary" disabled={!selected || busy} onClick={() => setTab('AI functions')}>Edit AI functions</button><button disabled={!active || !selected || busy} onClick={() => void action(() => saveCamera(camera))}>Save zones</button><button className="secondary" disabled={busy} onClick={() => { setCamera(current => ({ ...current, [zoneType]: [] })); setZonesDirty(true); setMessage(''); }}>Clear selected zone type</button></div><LocalFeedback feedback={feedback} location="zones" /></section>}
    {tab === 'People count' && <section className="panel"><h2>People count history</h2><div className="actions"><label>Site-local date<input type="date" value={day} onChange={event => setDay(event.target.value)} /></label><a className="button secondary" href={`/api/counts.csv?day=${day}`}>Download CSV</a><button className="secondary" onClick={() => window.print()}>Print report</button></div><p>Entries are tracked appearances, not guaranteed unique people or directional door crossings. Overlapping camera views can count the same person. A restart can begin a new track.</p><table><thead><tr><th>Camera</th><th>People visible at last sample</th><th>Tracked appearances</th><th>Last sample</th></tr></thead><tbody>{cameras.map(item => { const row = counts.find(entry => entry.camera_id === item.id); return <tr key={item.id}><td>{item.name}</td><td>{row ? row.people_visible : 'No sample'}</td><td>{row ? row.entries : 'No sample'}</td><td>{row ? `${new Date(row.updated_at * 1000).toLocaleString(undefined, { timeZone: status?.site.timezone })}${Date.now() / 1000 - row.updated_at > 10 ? ' (stale)' : ''}` : 'Not measured'}</td></tr>; })}</tbody></table></section>}
    {tab === 'Incidents' && <IncidentReports cameras={cameras} site={status?.site || { name: 'Local site', timezone: 'UTC' }} />}
    {tab === 'Licence & health' && <><section className="panel"><h2>Offline entitlement</h2><p><a href="/assets/vantag-offline-demo-team-manual.pdf" download>Download the offline demo-team manual (PDF)</a> · <a href="/assets/vantag-offline-demo-team-manual.html" target="_blank" rel="noreferrer">Read setup instructions</a></p><ol><li>On this PC, choose Export device renewal request below. It downloads this installation’s Device ID; do not enter the NVR IP as a Device ID.</li><li>Transfer that request JSON to an internet-connected PC. Your administrator imports it on the website under Admin → Offline demos, selects the correct account and usage policy, then issues a signed device licence.</li><li>Bring the signed response back to this same PC and select it in Import signed entitlement JSON. The request file is not a licence.</li><li>Confirm licence status before starting monitoring. An internal team demo licence has no expiry but is bound to this PC; customer validity and camera entitlement follow the issued licence.</li></ol><p>Status: {status?.licence.state}. {status?.licence.reason}</p>{status?.licence.claims && <p>{status.licence.claims.licence_type === 'internal_demo' ? 'Internal team demo — no expiry; bound to this device only' : status.licence.claims.expires_at != null ? `Expires ${new Date(status.licence.claims.expires_at * 1000).toLocaleString()}; grace ends ${new Date((status.licence.claims.expires_at + 7 * 86400) * 1000).toLocaleString()}` : 'Invalid expiry'}. Camera limit: {status.licence.claims.camera_limit}.</p>}<p>After seven days of grace, live viewing and new AI processing stop. Saved evidence and reports stay accessible. Import a signed renewal to resume.</p><label>Import signed entitlement JSON<input type="file" accept=".json,application/json" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void action(async () => { if (file.size > 65536) throw new Error('Entitlement file is too large'); await api('licence', JSON.parse(await file.text())); await refresh(); }, 'Signed entitlement imported'); }} /></label><a className="button secondary" href="/api/renewal-request">Export device renewal request</a></section><section className="panel"><h2>Actual AI runtime status</h2><RuntimeHealth runtime={status?.runtime} /><p>Implementation audit: an enabled switch is not evidence of successful detection. Cameras need connected video, an allowed schedule and recent successful inference.</p><dl>{functions.map(name => <React.Fragment key={name}><dt><strong>{name.replace(/_/g, ' ')}</strong></dt><dd>{featureNotes[name]}</dd></React.Fragment>)}</dl><h3>Unavailable advanced features</h3><dl>{Object.entries(status?.runtime.advanced_features || {}).map(([name, reason]) => <React.Fragment key={name}><dt>{name.replace(/_/g, ' ')}</dt><dd>{reason}</dd></React.Fragment>)}</dl><p>GPU use is shown only after real inference succeeds. CPU fallback and unavailable advanced capabilities must remain visible.</p></section></>}
    {tab === 'People tools' && <PeopleTools cameras={cameras} timezone={status?.site.timezone || 'UTC'} active={active} />}
    {tab === 'Storage & backup' && <StoragePanel />}
  </main></div>;
}

function CameraAiSettings({ camera, onChange }: { camera: Camera; onChange: React.Dispatch<React.SetStateAction<Camera>> }) {
  return <><fieldset><legend>AI functions (off until selected)</legend><div className="ai-function-grid">{functions.map(name => <div key={name}><label className="check"><input type="checkbox" checked={!!camera.detections[name]} onChange={event => onChange(current => ({ ...current, detections: { ...current.detections, [name]: event.target.checked } }))} />{featureLabels[name]}</label><p className="subtle">{featureNotes[name]}</p></div>)}</div></fieldset><fieldset><legend>Person detection quality</legend><p>Precision mode requires human body landmarks as well as a person detection. It helps reject furniture, but can miss partially hidden people and uses more processing. Neither mode requires a person to move or stand upright.</p><label>Person validation mode<select value={camera.person_quality?.mode || 'balanced'} onChange={event => onChange(current => ({ ...current, person_quality: { confidence: 0.6, confirmation_frames: 3, ...current.person_quality, mode: event.target.value } }))}><option value="precision">Precision — detector + pose confirmation</option><option value="balanced">Balanced — detector + repeated observations</option></select></label><div className="form-row"><label>Minimum person model score<input type="number" min={0.4} max={0.95} step={0.05} value={camera.person_quality?.confidence ?? 0.6} onChange={event => onChange(current => ({ ...current, person_quality: { mode: 'balanced', confirmation_frames: 3, ...current.person_quality, confidence: Number(event.target.value) } }))} /></label><label>Observations before counting<input type="number" min={2} max={10} value={camera.person_quality?.confirmation_frames ?? 3} onChange={event => onChange(current => ({ ...current, person_quality: { mode: 'balanced', confidence: 0.6, ...current.person_quality, confirmation_frames: Number(event.target.value) } }))} /></label></div><p className="subtle">A model score is not measured accuracy. Confirmation introduces a short delay dependent on actual processing FPS. Validate empty chairs, seated people and walking people on this camera before relying on counts.</p></fieldset><fieldset><legend>Schedule (site timezone)</legend><label className="check"><input type="checkbox" checked={camera.detection_schedule.enabled} onChange={event => onChange(current => ({ ...current, detection_schedule: { ...current.detection_schedule, enabled: event.target.checked } }))} />Use daily schedule</label><div className="form-row">{(['start', 'end'] as const).map(boundary => <label key={boundary}>{boundary === 'start' ? 'Start' : 'End'}<input type="time" value={camera.detection_schedule[boundary]} onChange={event => onChange(current => ({ ...current, detection_schedule: { ...current.detection_schedule, [boundary]: event.target.value } }))} required /></label>)}</div><p>Enabled theft detection stays active at all times. Other enabled AI functions follow this daily window. Overnight windows are supported; equal times mean all day.</p></fieldset><label className="check"><input type="checkbox" checked={camera.enabled} onChange={event => onChange(current => ({ ...current, enabled: event.target.checked }))} />Camera enabled</label></>;
}

function RuntimeHealth({ runtime }: { runtime?: Status['runtime'] }) {
  const detector = runtime?.detector || {};
  const calibration = runtime?.calibration || {};
  const finiteNumber = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  const count = finiteNumber(detector.inference_count);
  const latency = finiteNumber(detector.last_inference_ms);
  const providers: Record<string, string> = { CPUExecutionProvider: 'CPU (ONNX Runtime)', CUDAExecutionProvider: 'NVIDIA GPU (CUDA)', DmlExecutionProvider: 'GPU (DirectML)' };
  const provider = typeof detector.provider === 'string' ? providers[detector.provider] || 'Unrecognised provider' : 'Not selected yet';
  const hasError = !!(runtime?.error || detector.error || calibration.error);
  const verified = detector.is_preferred === true;
  const connected = runtime?.cameras?.filter(camera => camera.connected).length ?? 0;
  const summary = {
    monitoring: runtime?.running ? 'Running' : 'Stopped',
    detector_architecture: verified ? 'Preferred YOLO26 verified' : 'Not verified',
    execution_provider: provider,
    successful_inference_calls: count,
    last_inference_ms: latency,
    calibration_ms: finiteNumber(calibration.inference_ms),
    fallback_reported: !!calibration.fallback_reason,
    error_reported: hasError,
    monitored_cameras: runtime?.cameras?.length ?? 0,
    connected_cameras: connected,
  };
  return <section aria-label="Runtime health summary" className="runtime-health">
    <h3>Runtime health summary</h3>
    <dl>
      <dt>Monitoring</dt><dd>{runtime ? summary.monitoring : 'Checking local service…'}</dd>
      <dt>Health</dt><dd>{hasError ? 'Needs attention' : runtime?.running ? 'Monitoring started — check each camera below' : 'Not monitoring'}</dd>
      <dt>People detector</dt><dd>{verified ? 'YOLO26 architecture verified' : 'Not verified'}</dd>
      <dt>Processing device</dt><dd>{provider}</dd>
      <dt>Connected video</dt><dd>{connected} of {runtime?.cameras?.length ?? 0} monitored cameras</dd>
      <dt>Successful model calls</dt><dd>{count === null ? 'Not measured' : count.toLocaleString()}</dd>
      <dt>Last model latency</dt><dd>{latency === null || !count ? 'Not measured' : `${latency.toFixed(1)} ms`}</dd>
    </dl>
    {hasError && <p role="alert" className="error">The local runtime reported a problem. Check camera diagnostics and recording space. If it persists, contact support with the technical summary below; private error paths are not displayed here.</p>}
    {!!calibration.fallback_reason && <p className="notice">{detector.provider === 'CPUExecutionProvider' ? 'CPU fallback is active after an acceleration attempt failed.' : 'An earlier processing-device attempt failed; the device shown above was selected instead.'} Camera capacity must be checked on this PC.</p>}
    <h3>Person validation by camera</h3>{runtime?.cameras?.map(camera => <p key={camera.id}><strong>{camera.id}: </strong>{camera.person_quality?.error || (camera.person_quality?.evaluated_at ? `${camera.person_quality.mode}; ${camera.person_quality.rejected_this_frame} candidates rejected in last frame; evaluated ${new Date(camera.person_quality.evaluated_at * 1000).toLocaleTimeString()}` : 'No recent person validation')}</p>)}<p className="subtle">Model-call totals include startup calibration and do not prove recent live-camera inference or detection accuracy. Check connected video, frame freshness and each camera’s detection readiness.</p>
    <details className="setup-details"><summary>Technical details (for support)</summary><p>Privacy-filtered summary. Local file paths, raw error messages, camera credentials and evidence are omitted.</p><pre>{JSON.stringify(summary, null, 2)}</pre></details>
  </section>;
}

function PasswordField({ label, ...properties }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  return <div className="password-field"><label htmlFor={id}>{label}</label><div className="password-control"><input {...properties} id={id} type={visible ? 'text' : 'password'} onBlur={event => { if (!event.relatedTarget?.closest('.password-control')) setVisible(false); properties.onBlur?.(event); }} /><button type="button" className="password-toggle" aria-label={`${visible ? 'Hide' : 'Show'} password characters`} aria-pressed={visible} onClick={() => setVisible(current => !current)}><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />{visible && <path d="m3 3 18 18" />}</svg><span aria-hidden="true">{visible ? 'Hide' : 'Show'}</span></button></div></div>;
}

function LocalFeedback({ feedback, location }: { feedback: Feedback; location: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!feedback || feedback.location !== location || feedback.kind === 'busy' || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    if (rect.top < 0 || rect.bottom > window.innerHeight) ref.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [feedback, location]);
  if (!feedback || feedback.location !== location) return null;
  return <div ref={ref} role={feedback.kind === 'error' ? 'alert' : 'status'} className={`inline-feedback ${feedback.kind === 'error' ? 'error' : feedback.kind === 'success' ? 'success' : 'notice'}`}>{feedback.text}</div>;
}

function StreamDiagnosisPanel({ result }: { result: StreamDiagnosis }) {
  return <div role={result.success ? 'status' : 'alert'} className={result.success ? 'success' : 'error'}>
    <h3>{result.success ? 'Video verified — review before saving' : `Stopped at: ${result.failed_stage || 'unknown stage'}`}</h3>
    <p>{result.message}</p>
    <dl>{Object.entries(result.stages).map(([stage, state]) => <React.Fragment key={stage}><dt>{stage}</dt><dd>{state}</dd></React.Fragment>)}</dl>
    <p>Brand hint from RTSP headers: {result.brand_hint || 'Unknown — device did not identify its brand'}. Compatible paths alone do not identify a manufacturer.</p>
    <p>{result.attempts.length} candidate description checks. {result.attempts.map(attempt => `#${attempt.candidate}: ${attempt.status || 'no RTSP status'}${attempt.authenticated_request ? ' after authentication request' : ''}`).join('; ')}</p>
    {result.success && result.thumbnail && <img alt="Video frame verified during automatic detection" style={{ maxWidth: '100%' }} src={`data:image/jpeg;base64,${result.thumbnail}`} />}
  </div>;
}

function VideoWall({ cameras, runtimeCameras, active, running, busy, onEditAi, onConfigure, onStart, onStop }: { cameras: Camera[]; runtimeCameras: NonNullable<Status['runtime']['cameras']>; active: boolean; running: boolean; busy: boolean; onEditAi: (camera: Camera) => void; onConfigure: (camera: Camera) => void; onStart: () => void; onStop: () => void }) {
  const [layout, setLayout] = useState('auto');
  const [page, setPage] = useState(0);
  const [compact, setCompact] = useState(true);
  const [wallError, setWallError] = useState('');
  const wall = React.useRef<HTMLElement>(null);
  const columns = layout === 'auto' ? cameras.length <= 4 ? 2 : cameras.length <= 9 ? 3 : 4 : Number(layout);
  const pageSize = columns * columns;
  const pages = Math.max(1, Math.ceil(cameras.length / pageSize));
  const currentPage = Math.min(page, pages - 1);
  const visibleCameras = cameras.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  async function fullscreen() {
    setWallError('');
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (wall.current?.requestFullscreen) await wall.current.requestFullscreen();
      else setWallError('Fullscreen is unavailable in this browser. Use the browser fullscreen control.');
    } catch { setWallError('Fullscreen was not permitted. Use the browser fullscreen control.'); }
  }
  return <section ref={wall} className={`video-wall-section ${compact ? 'wall-compact' : ''}`}><div className="wall-heading"><div><div className="section-kicker">Live operations</div><h2>Video wall</h2><p className="subtle">{cameras.length} saved cameras · {runtimeCameras.filter(item => item.connected).length} active streams · {running ? 'Monitoring running' : 'Monitoring stopped'}</p></div><div className="actions"><button disabled={!active || busy} onClick={onStart}>Start monitoring</button><button className="secondary" disabled={busy} onClick={onStop}>Stop monitoring</button></div></div><div className="wall-toolbar"><label>Wall layout<select value={layout} onChange={event => { setLayout(event.target.value); setPage(0); }}><option value="auto">Auto-fit</option><option value="2">2 × 2 · 4 cameras</option><option value="3">3 × 3 · 9 cameras</option><option value="4">4 × 4 · 16 cameras</option></select></label><label className="check"><input type="checkbox" checked={compact} onChange={event => setCompact(event.target.checked)} />Compact tiles</label><button className="secondary" onClick={() => void fullscreen()}>Fullscreen wall</button><details className="wall-ai-help"><summary>How to enable and test AI</summary><p>Video alone does not enable AI. Choose Edit AI on a camera (or open AI functions in the sidebar) → select the required functions → Save AI functions. Shelf detection also needs a saved shelf zone. Expand the per-camera AI switches below to see whether functions are off, waiting or analysing; this does not establish accuracy. Shared capture uses no extra camera logins.</p></details>{pages > 1 && <div className="wall-pagination"><button className="secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous wall page</button><span>{currentPage + 1} / {pages}</span><button className="secondary" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>Next wall page</button></div>}</div>{wallError && <div role="alert" className="error">{wallError}</div>}{!active && <div className="notice">Live viewing is unavailable until a valid offline entitlement is imported. Saved incidents and exports remain available.</div>}{cameras.length === 0 ? <div className="empty-state"><h3>Your cameras will appear here</h3><p>Add cameras in the Cameras page, then start monitoring.</p></div> : <div className={`video-wall wall-columns-${columns}`}>{visibleCameras.map(camera => { const live = runtimeCameras.find(item => item.id === camera.id); return <article className="camera-tile wall-tile" key={camera.id}><div className="camera-tile-title"><h3>{camera.name}</h3><button className="secondary wall-ai-edit" aria-label={`Edit AI ${camera.name}`} onClick={() => onEditAi(camera)}>Edit AI</button><span className={`stream-state ${live?.connected ? 'is-live' : ''}`}>{!camera.enabled ? 'Disabled' : live?.connected ? 'Live' : running ? 'No video' : 'Stopped'}</span></div>{active && camera.enabled && <WallFrame cameraId={camera.id!} name={camera.name} />}<div className="wall-tile-metrics"><p className="subtle">{camera.stream_info?.host} · Channel {camera.stream_info?.channel ?? 'custom'}</p><p className="subtle">{live?.frame_age_sec == null ? 'No current frame' : `Frame age ${live.frame_age_sec.toFixed(1)}s`} · Capture FPS {live?.fps ?? 0}</p></div>{live?.connection_error && !live.connected && <p className="camera-reason">{live.connection_error}</p>}<details className="wall-analytics" open={!compact}><summary>AI switches · Fall {camera.detections.fall_detected ? 'on' : 'off'} · Theft {camera.detections.shoplifting ? 'on' : 'off'} · Shelf {camera.detections.inventory_movement ? 'on' : 'off'}</summary>{(['fall_status', 'theft_status', 'inventory_status'] as const).map((key, index) => <p key={key} className="subtle wall-fall-state">{['Fall', 'Theft', 'Shelf'][index]} detection: {live?.[key]?.state || (camera.detections[['fall_detected', 'shoplifting', 'inventory_movement'][index]] ? 'Monitoring not running for this camera' : 'Off for this camera')}</p>)}</details><button className="secondary wall-configure" onClick={() => onConfigure(camera)}>Configure {camera.name}</button></article>; })}</div>}</section>;
}

function WallFrame({ cameraId, name }: { cameraId: string; name: string }) {
  const [source, setSource] = useState('');
  const [unavailable, setUnavailable] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    let timer = 0;
    const update = async () => {
      try {
        if (!document.hidden) {
          const response = await fetch(`/api/frame/${encodeURIComponent(cameraId)}?t=${Date.now()}`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
          if (response.status === 401) window.dispatchEvent(new Event('local-session-expired'));
          if (!response.ok) throw new Error('No recent frame');
          const blob = await response.blob();
          if (controller.signal.aborted) return;
          const previous = objectUrl;
          objectUrl = URL.createObjectURL(blob);
          setSource(objectUrl); setUnavailable(false);
          if (previous) URL.revokeObjectURL(previous);
        }
      } catch {
        if (!controller.signal.aborted) setUnavailable(true);
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(update, 1000);
      }
    };
    void update();
    return () => { controller.abort(); window.clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [cameraId]);
  return <div className="preview wall-frame">{source && <img alt={`Latest local frame: ${name}`} src={source} />}{unavailable && <p className="preview-warning">No recent frame. Check monitoring and RTSP diagnostics.</p>}</div>;
}

function StoragePanel() {
  const [storage, setStorage] = useState<{ used_bytes: number; quota_bytes: number; free_bytes: number; can_record: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const refresh = () => api<NonNullable<typeof storage>>('storage').then(setStorage);
  useEffect(() => { void refresh().catch(cause => setError(String(cause))); }, []);

  async function run(work: () => Promise<unknown>) {
    setBusy(true); setError(''); setMessage('');
    try { await work(); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Storage action failed'); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <h2>Storage & private backups</h2>
    <p>Records are retained until you explicitly restore or remove them. Internet loss never evicts incidents. New recording stops at the configured quota or below 256 MB free disk space; existing data remains accessible.</p>
    {storage && <>
      <p>{(storage.used_bytes / 1048576).toFixed(1)} MB used · {(storage.free_bytes / 1073741824).toFixed(1)} GB free on disk · {storage.can_record ? 'Recording space available' : 'Storage full — new recording blocked'}</p>
      <form key={storage.quota_bytes} onSubmit={event => {
        event.preventDefault();
        const value = Number(new FormData(event.currentTarget).get('quota'));
        void run(async () => { await api('storage', { quota_mb: value }); setMessage('Storage quota saved'); });
      }}>
        <label>Site data quota (MB)<input name="quota" type="number" min={256} max={1048576} defaultValue={storage.quota_bytes / 1048576} required /></label>
        <button disabled={busy}>Save quota</button>
      </form>
    </>}
    <p>Backups contain private evidence and encrypted camera credentials. Keep them secure. Credential restoration requires the original Windows user account. Restoration replaces site data but never rolls back your current local owner, device binding or entitlement.</p>
    <a className="button secondary" href="/api/backup">Download private backup ZIP</a>
    <label>Restore a private backup (up to 2 GB)<input type="file" accept=".zip,application/zip" disabled={busy} onChange={event => {
      const file = event.target.files?.[0];
      if (!file || !confirm('This replaces current camera configuration, counts and incidents and stops monitoring. Export a current backup first. Continue?')) return;
      void run(async () => {
        if (file.size > 2 * 1024 ** 3) throw new Error('Backup exceeds the 2 GB console restore limit');
        const response = await fetch('/api/restore', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip', 'X-Vantag-Restore': 'replace-site-data' }, body: file });
        if (!response.ok) { const detail = await response.json().catch(() => ({})); throw new Error(detail.detail || 'Backup restore failed'); }
        setMessage('Site restored. Review cameras and restart monitoring when ready.');
      });
    }} /></label>
    {busy && <p role="status">Processing local storage action…</p>}
    {message && <p role="status" className="success">{message}</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

createRoot(document.getElementById('root')!).render(<Console />);
