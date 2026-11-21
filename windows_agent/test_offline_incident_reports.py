import base64
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from agent.local.licensing import EntitlementStatus
from agent.local.server import create_app
from agent.local.store import SiteStore


@pytest.fixture
def archive(tmp_path):
    store = SiteStore(tmp_path)
    store.set('site', {'name': 'Report site', 'timezone': 'Asia/Singapore'})
    for index in range(215):
        store.record_event({'event_id': f'event-{index:03}', 'camera_id': 'pantry', 'event_type': 'fall_detected', 'metadata': {'note': 'Archived fall'}})
    store.record_event({'event_id': 'crowd', 'camera_id': 'office', 'event_type': 'crowding', 'metadata': {'person_count': 6}, 'snapshot_b64': base64.b64encode(b'evidence').decode()})
    licence = SimpleNamespace(status=lambda: EntitlementStatus('expired'))
    with TestClient(create_app(store, licence, None), base_url='http://127.0.0.1') as client:
        client.post('/api/setup', json={'username': 'owner', 'password': 'test-only-unique-password'})
        yield store, client


def test_archive_search_reaches_beyond_latest_two_hundred(archive):
    store, client = archive
    response = client.get('/api/incidents', params={'q': 'event-000'})
    assert response.status_code == 200
    assert [item['event_id'] for item in response.json()['items']] == ['event-000']
    first = client.get('/api/incidents', params={'page_size': 50}).json()
    second = client.get('/api/incidents', params={'page_size': 50, 'page': 2}).json()
    assert first['total'] == 216
    assert len(first['items']) == len(second['items']) == 50
    assert not ({item['event_id'] for item in first['items']} & {item['event_id'] for item in second['items']})


def test_report_filters_measured_people_without_inventing_missing_counts(archive):
    _, client = archive
    result = client.get('/api/incidents', params={'min_people': 5, 'camera_id': 'office', 'event_type': 'crowding'}).json()
    assert result['total'] == 1
    assert result['items'][0]['people_visible'] == 6
    assert client.get('/api/incidents', params={'min_people': 0, 'event_type': 'fall_detected'}).json()['total'] == 0


def test_report_uses_site_local_dates_and_rejects_invalid_ranges(archive):
    store, client = archive
    stamp = datetime(2026, 11, 20, 17, tzinfo=timezone.utc).timestamp()
    with store.connect() as connection:
        connection.execute('UPDATE events SET created_at=? WHERE id=?', (stamp, 'event-000'))
    assert client.get('/api/incidents', params={'q': 'event-000', 'start_day': '2026-11-21', 'end_day': '2026-11-21'}).json()['total'] == 1
    assert client.get('/api/incidents', params={'start_day': '2026-11-22', 'end_day': '2026-11-20'}).status_code == 400
    assert client.get('/api/incidents', params={'min_people': -1}).status_code == 422
    assert client.get('/api/incidents', params={'page_size': 1001}).status_code == 422


def test_operator_review_is_persistent_audited_and_not_ai_verification(archive):
    store, client = archive
    response = client.post('/api/incidents/crowd/review', json={'state': 'confirmed', 'note': 'Six people visible in evidence'})
    assert response.status_code == 200
    result = client.get('/api/incidents', params={'review_state': 'confirmed'}).json()
    assert result['total'] == 1
    assert result['items'][0]['review']['state'] == 'confirmed'
    assert result['items'][0]['verification_state'] == 'not_verified_offline'
    assert result['items'][0]['evidence']['snapshot_b64'].startswith('/api/evidence/')
    assert SiteStore(store.directory).incident_search(review_state='confirmed')['total'] == 1
    assert client.post('/api/incidents/crowd/review', json={'state': 'made_up'}).status_code == 422
    assert client.post('/api/incidents/missing/review', json={'state': 'dismissed'}).status_code == 404
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit WHERE action LIKE 'Incident review:%'").fetchone()[0] == 1


def test_reports_require_local_login(archive):
    _, client = archive
    client.cookies.clear()
    assert client.get('/api/incidents').status_code == 401
    assert client.post('/api/incidents/crowd/review', json={'state': 'confirmed'}).status_code == 401
