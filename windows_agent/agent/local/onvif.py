from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import requests
from requests.auth import HTTPDigestAuth

SOAP = 'http://www.w3.org/2003/05/soap-envelope'
DEVICE = 'http://www.onvif.org/ver10/device/wsdl'
MEDIA = 'http://www.onvif.org/ver10/media/wsdl'
SCHEMA = 'http://www.onvif.org/ver10/schema'


def _xml(content: bytes):
    if len(content) > 1048576 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('ONVIF response exceeds safe limits or contains unsupported XML declarations.')
    try:
        return ElementTree.fromstring(content)
    except ElementTree.ParseError:
        raise ValueError('This port did not return a valid ONVIF SOAP response.') from None


def _same_device(endpoint: str, host: str, scheme: str) -> str:
    parts = urlsplit(endpoint)
    if parts.scheme != scheme or parts.hostname != host or parts.username or parts.password or parts.fragment or not parts.path.startswith('/'):
        raise ValueError('Device advertised an address outside the selected device or protocol. It was not contacted.')
    try:
        port = parts.port
    except ValueError:
        raise ValueError('Device advertised an invalid service port.') from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Device advertised an invalid service port.')
    return endpoint


class OnvifReader:
    def __init__(self, rtsp_url: str, port: int = 0):
        self.parts = urlsplit(rtsp_url)
        self.host = self.parts.hostname
        self.username = unquote(self.parts.username or '')
        self.password = unquote(self.parts.password or '')
        if not self.username or not self.password:
            raise ValueError('Enter the actual device username and password before ONVIF discovery.')
        self.port = port
        self.created = None
        self.clock_note = 'Device clock could not be read; PC UTC time is used for ONVIF security.'
        self.session = requests.Session()
        self.session.trust_env = False

    def close(self):
        self.session.close()

    def _request(self, endpoint: str, operation: str, namespace: str, body: str = '', *, authenticated: bool = True):
        _same_device(endpoint, self.host, 'http')
        header = ''
        if authenticated:
            created = self.created or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            nonce = secrets.token_bytes(20)
            digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + self.password.encode()).digest()).decode()
            header = f'<s:Header><Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" s:mustUnderstand="1"><UsernameToken><Username>{escape(self.username)}</Username><Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</Password><Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</Nonce><Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created></UsernameToken></Security></s:Header>'
        envelope = f'<s:Envelope xmlns:s="{SOAP}" xmlns:t="{namespace}" xmlns:tt="{SCHEMA}">{header}<s:Body><t:{operation}>{body}</t:{operation}></s:Body></s:Envelope>'
        try:
            with self.session.post(endpoint, data=envelope.encode(), headers={'Content-Type': f'application/soap+xml; charset=utf-8; action="{namespace}/{operation}"'}, auth=HTTPDigestAuth(self.username, self.password) if authenticated else None, timeout=(1.5, 3), allow_redirects=False, stream=True) as response:
                content = bytearray()
                for chunk in response.iter_content(8192):
                    content.extend(chunk)
                    if len(content) > 1048576:
                        raise ValueError('ONVIF response exceeds the 1 MB diagnostic limit.')
                if response.status_code in {401, 403}:
                    if authenticated:
                        raise ValueError('ONVIF account access was rejected. The ONVIF account can differ from the web/NVR account. Verify ONVIF is enabled and its user has media/live-view access. No other passwords were tried.')
                    return None
                status = response.status_code
                if status not in {200, 400, 500}:
                    if not authenticated:
                        raise ValueError('No ONVIF service response on this port.')
                    raise ValueError(f'ONVIF returned HTTP {status}. Check the ONVIF service port and whether media access is enabled.')
        except requests.RequestException:
            raise ValueError('ONVIF service did not respond. Check its HTTP service port, LAN access and whether ONVIF is enabled. No settings were changed.') from None
        document = _xml(bytes(content))
        if document.tag != f'{{{SOAP}}}Envelope':
            raise ValueError('This port did not return an ONVIF SOAP envelope.')
        fault = document.find(f'.//{{{SOAP}}}Fault')
        if fault is not None:
            if not authenticated:
                return document
            codes = ' '.join(node.text or '' for node in fault.iter() if node.tag.endswith('}Value'))
            if any(value in codes.lower() for value in ('notauthorized', 'failedauthentication', 'invalidsecurity')):
                raise ValueError('ONVIF security was rejected even after checking the device clock. Verify its ONVIF-specific user, media permissions and account lockout; web login alone does not validate ONVIF access.')
            raise ValueError('Device returned an ONVIF SOAP fault for this read-only media operation. It may not support the standard media service.')
        if status != 200:
            raise ValueError(f'ONVIF returned HTTP {status} without a usable media response.')
        return document

    def connect(self) -> str:
        candidates = [self.port] if self.port else [80, 8899, 8999, 8080, 8000]
        fallback = None
        for port in candidates:
            endpoint = f'http://{self.host}:{port}/onvif/device_service'
            try:
                document = self._request(endpoint, 'GetSystemDateAndTime', DEVICE, authenticated=False)
            except ValueError:
                continue
            if document is None:
                fallback = fallback or endpoint
                continue
            utc = document.find(f'.//{{{SCHEMA}}}UTCDateTime')
            if utc is not None:
                try:
                    values = [int(utc.findtext(f'{{{SCHEMA}}}{section}/{{{SCHEMA}}}{name}')) for section, name in [('Date', 'Year'), ('Date', 'Month'), ('Date', 'Day'), ('Time', 'Hour'), ('Time', 'Minute'), ('Time', 'Second')]]
                    moment = datetime(*values, tzinfo=timezone.utc)
                    self.created = moment.strftime('%Y-%m-%dT%H:%M:%SZ')
                    skew = abs((moment - datetime.now(timezone.utc)).total_seconds())
                    self.clock_note = f'Device UTC used for ONVIF security; observed clock difference approximately {round(skew)} seconds. Device time was not changed.'
                except (TypeError, ValueError):
                    pass
            self.port = port
            return endpoint
        if fallback:
            self.port = urlsplit(fallback).port
            return fallback
        raise ValueError('No ONVIF service found on the selected/common ports. Enable ONVIF in the device, check its configured ONVIF HTTP port, and retry with that port. No credentials were sent during port discovery.')

    def profiles(self) -> dict:
        endpoint = self.connect()
        capabilities = self._request(endpoint, 'GetCapabilities', DEVICE, '<t:Category>Media</t:Category>')
        media = capabilities.findtext(f'.//{{{SCHEMA}}}Media/{{{SCHEMA}}}XAddr')
        if not media:
            raise ValueError('Device did not advertise an ONVIF media service. Obtain its exact RTSP path from the installer.')
        _same_device(media, self.host, 'http')
        document = self._request(media, 'GetProfiles', MEDIA)
        profiles = []
        for profile in document.findall(f'.//{{{MEDIA}}}Profiles')[:64]:
            token = profile.get('token', '')
            if not token or len(token) > 200:
                continue
            profiles.append({'token': token, 'name': profile.findtext(f'{{{SCHEMA}}}Name') or token, 'source': profile.findtext(f'{{{SCHEMA}}}VideoSourceConfiguration/{{{SCHEMA}}}SourceToken') or 'Unknown source', 'width': profile.findtext(f'{{{SCHEMA}}}VideoEncoderConfiguration/{{{SCHEMA}}}Resolution/{{{SCHEMA}}}Width'), 'height': profile.findtext(f'{{{SCHEMA}}}VideoEncoderConfiguration/{{{SCHEMA}}}Resolution/{{{SCHEMA}}}Height')})
        if not profiles:
            raise ValueError('ONVIF responded but returned no usable media profiles for this account.')
        return {'profiles': profiles, 'media_endpoint': media, 'onvif_port': self.port, 'message': 'Device-reported media profiles, not guessed brand paths. Choose the intended source/profile, then test its actual video. Nothing has been saved.', 'clock_note': self.clock_note}

    def stream(self, media: str, token: str) -> str:
        _same_device(media, self.host, 'http')
        self.connect()
        body = f'<t:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></t:StreamSetup><t:ProfileToken>{escape(token)}</t:ProfileToken>'
        document = self._request(media, 'GetStreamUri', MEDIA, body)
        uri = document.findtext(f'.//{{{SCHEMA}}}Uri')
        if not uri:
            raise ValueError('Device did not return an ONVIF RTSP stream URI for this profile.')
        parts = urlsplit(uri)
        if parts.scheme != 'rtsp' or parts.hostname != self.host or parts.fragment or not parts.path.startswith('/'):
            raise ValueError('Device advertised a stream outside the selected device. It was not contacted; ask the installer to correct its ONVIF stream address.')
        if not 1 <= (parts.port or 554) <= 65535:
            raise ValueError('Device returned an invalid RTSP port.')
        authority = f'{quote(self.username, safe="")}:{quote(self.password, safe="")}@{self.host}:{parts.port or 554}'
        return urlunsplit(('rtsp', authority, parts.path, parts.query, ''))
