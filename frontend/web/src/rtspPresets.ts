export type RtspPreset = { id: string; label: string; channelMax?: number; streams?: boolean; profile?: 'number' | 'token'; note: string; source: string };

export const rtspPresets: RtspPreset[] = [
  { id: 'hikvision', label: 'Hikvision NVR channel', channelMax: 64, streams: true, note: 'NVR channels start at 1. 101 = channel 1 main; 102 = channel 1 substream. Use the recorder IP, not the camera IP, when connecting through an NVR.', source: 'https://www.hikvision.com/content/dam/hikvision/en/support/faq/How%20to%20add%20IPC%20with%20RTSP%20Protocol%20in%20NVR.pdf' },
  { id: 'dahua', label: 'Dahua / CP Plus compatible channel', channelMax: 64, streams: true, note: 'Dahua-compatible devices: channel starts at 1; subtype 0 = main, 1 = substream. CP Plus models vary: confirm this format in the device manual.', source: 'https://www.dahuasecurity.com/asset/upload/uploads/soft/20191107/5-Dahua-Network-Camera-Web-3.0-Operation-Manual_V2.0.1.pdf' },
  { id: 'axis', label: 'Axis camera / encoder', channelMax: 64, note: 'Requests H.264 from the chosen video source using device-default quality, not an invented main/substream mapping. Single-sensor cameras normally use source 1. For a named stream profile use Custom and append &streamprofile=your-profile.', source: 'https://developer.axis.com/vapix/network-video/video-streaming' },
  { id: 'hanwha-camera', label: 'Hanwha Vision / Wisenet IP camera', profile: 'number', note: 'Use the actual configured profile number. Profile 2 is a vendor example, not a guaranteed substream. For a recorder, choose the separate Hanwha NVR preset.', source: 'https://support.hanwhavision.com/hc/en-001/articles/47782445700243-RTSP-URL-Information-for-Hanwha-Devices' },
  { id: 'hanwha-nvr', label: 'Hanwha Vision / Wisenet NVR', channelMax: 64, note: 'Choose the displayed camera channel (1-based); the wizard converts channel 1 to LiveChannel/0. Uses the NVR default stream. Confirm its RTSP port: some models use the last port in the configured device-port range, not 554.', source: 'https://support.hanwhavision.com/hc/en-001/articles/47782445700243-RTSP-URL-Information-for-Hanwha-Devices' },
  { id: 'bosch', label: 'Bosch BVIP camera / multi-input encoder', channelMax: 64, streams: true, note: 'BVIP live video: line selects the physical video input and inst selects encoding stream 1 or 2. This is not a universal Bosch recorder path; use the exact model manual for a recorder.', source: 'https://assets.catalog.boschbuildingtechnologies.com/public/documents/RTSP_VIP_Application_note_enUS_9007200806939915.pdf' },
  { id: 'ipro', label: 'i-PRO / Panasonic compatible IP camera', streams: true, note: 'i-PRO H.265/H.264 model command interface: stream_1 or stream_2. The codec and quality come from camera configuration. Older Panasonic models can differ; select Custom for their documented path.', source: 'https://i-pro.com/products_and_solutions/sites/default/files/2025-10/Command%20interface%20iPRO_H.265models_ver1.14.pdf' },
  { id: 'ipro-multi', label: 'i-PRO multi-sensor / fisheye quad mode', channelMax: 4, streams: true, note: 'Only multi-sensor models or fisheye cameras already configured for Quad Streams. Select sensor/view 1–4; this is not an NVR-channel preset.', source: 'https://i-pro.com/products_and_solutions/en/surveillance/faq-list/en124496' },
  { id: 'vivotek', label: 'VIVOTEK legacy RTSP access names', streams: true, note: 'Legacy/default access names: live.sdp and live2.sdp. Access names are configurable. Newer firmware may require a media-profile token instead; use the separate VIVOTEK profile preset.', source: 'https://vivotek.zendesk.com/hc/en-001/articles/900005560446--All-cameras-Anystream-compatible-How-to-use-the-Anystream-functionality-in-VIVOTEK-cameras' },
  { id: 'vivotek-profile', label: 'VIVOTEK newer firmware / profile token', profile: 'token', note: 'Firmware 2.2002.x.x and later: copy the actual token from Configuration → Media → Media profiles, then System → Parameters. Profile200 is only a vendor example; a nonexistent token will fail.', source: 'https://vivotek.zendesk.com/hc/en-001/articles/4952515434649--All-cameras-2-2002-x-x-and-later-version-How-to-get-RTSP-streaming-with-camera-firmware-version-2-2002-x-x-and-later-version' },
  { id: 'avigilon', label: 'Avigilon / Motorola compatible IP camera', streams: true, note: 'Uses defaultPrimary or defaultSecondary unicast. Confirm the device RTSP URI in its web UI. H4Pro encrypted streams do not support this direct RTSP method; H6A may require Dual Mode.', source: 'https://support.avigilon.com/s/article/Access-the-RTSP-Stream-or-Latest-JPEG-Image-from-an-H-264-Camera-or-Encoder?language=en_US' },
];

export function buildStreamPath(mode: string, channel: string, stream: string, profile = ''): string {
  const sub = stream === '02';
  switch (mode) {
    case 'hikvision': return `/Streaming/Channels/${channel}${stream}`;
    case 'dahua': return `/cam/realmonitor?channel=${channel}&subtype=${sub ? '1' : '0'}`;
    case 'axis': return `/axis-media/media.amp?camera=${channel}&videocodec=h264`;
    case 'hanwha-camera': return `/profile${profile}/media.smp`;
    case 'hanwha-nvr': return `/LiveChannel/${Number(channel) - 1}/media.smp`;
    case 'bosch': return `/?line=${channel}&inst=${sub ? '2' : '1'}`;
    case 'ipro': return `/Src/MediaInput/stream_${sub ? '2' : '1'}`;
    case 'ipro-multi': return `/Src/MediaInput/stream_${sub ? '2' : '1'}/ch_${channel}`;
    case 'vivotek': return sub ? '/live2.sdp' : '/live.sdp';
    case 'vivotek-profile': return `/media2/stream.sdp?profile=${encodeURIComponent(profile)}`;
    case 'avigilon': return `/default${sub ? 'Secondary' : 'Primary'}?streamType=u`;
    default: return '';
  }
}

export function inferStreamSetup(path: string): { mode: string; channel: string; stream: string; profile: string } {
  const url = new URL(path, 'rtsp://local');
  let channel = '1', stream = '02', profile = '';
  const hikvision = path.match(/^\/Streaming\/Channels\/([1-9]\d*)(01|02)$/i);
  if (hikvision) return { mode: 'hikvision', channel: hikvision[1], stream: hikvision[2], profile };
  if (url.pathname === '/cam/realmonitor') {
    channel = url.searchParams.get('channel') || '';
    stream = url.searchParams.get('subtype') === '0' ? '01' : '02';
  } else if (url.pathname === '/axis-media/media.amp') channel = url.searchParams.get('camera') || '1';
  else if (url.pathname === '/') { channel = url.searchParams.get('line') || ''; stream = url.searchParams.get('inst') === '1' ? '01' : '02'; }
  const hanwha = path.match(/^\/LiveChannel\/(\d+)\/media.smp$/);
  if (hanwha) channel = String(Number(hanwha[1]) + 1);
  const hanwhaProfile = path.match(/^\/profile([1-9]\d*)\/media.smp$/);
  if (hanwhaProfile) profile = hanwhaProfile[1];
  const ipro = path.match(/^\/Src\/MediaInput\/stream_([12])(?:\/ch_([1-4]))?$/);
  if (ipro) { stream = ipro[1] === '1' ? '01' : '02'; channel = ipro[2] || '1'; }
  if (url.pathname === '/media2/stream.sdp') profile = url.searchParams.get('profile') || '';
  if (url.pathname === '/live.sdp' || url.pathname === '/defaultPrimary') stream = '01';
  for (const preset of rtspPresets) {
    const candidate = new URL(buildStreamPath(preset.id, channel, stream, profile), 'rtsp://local');
    if (candidate.pathname === url.pathname && JSON.stringify([...candidate.searchParams.entries()].sort()) === JSON.stringify([...url.searchParams.entries()].sort())) return { mode: preset.id, channel, stream, profile };
  }
  return { mode: 'custom', channel: '1', stream: '02', profile: '' };
}
