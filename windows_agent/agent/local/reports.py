from __future__ import annotations

import json
import time
from datetime import date, datetime, time as clock_time, timedelta
from zoneinfo import ZoneInfo


PEOPLE_SQL = """CASE WHEN typeof(json_extract(e.data, '$.people_visible')) = 'integer'
    THEN json_extract(e.data, '$.people_visible')
    WHEN typeof(json_extract(e.data, '$.metadata.person_count')) = 'integer'
    THEN json_extract(e.data, '$.metadata.person_count') END"""


def search_incidents(store, *, q: str = '', camera_id: str = '', event_type: str = '', start_day: str = '', end_day: str = '', min_people: int | None = None, review_state: str = '', page: int = 1, page_size: int = 50) -> dict:
    timezone = store.get('site', {}).get('timezone', 'UTC')
    conditions = []
    values = []
    if start_day and end_day and date.fromisoformat(start_day) > date.fromisoformat(end_day):
        raise ValueError('Start date must not be after end date')
    for value, operator, next_day in ((start_day, '>=', False), (end_day, '<', True)):
        if value:
            boundary = date.fromisoformat(value) + timedelta(days=int(next_day))
            conditions.append(f'e.created_at {operator} ?')
            values.append(datetime.combine(boundary, clock_time.min, ZoneInfo(timezone)).timestamp())
    if camera_id:
        conditions.append('e.camera_id=?')
        values.append(camera_id)
    if event_type:
        conditions.append("json_extract(e.data, '$.event_type')=?")
        values.append(event_type)
    if min_people is not None:
        conditions.append(f'({PEOPLE_SQL})>=?')
        values.append(min_people)
    if review_state:
        conditions.append("COALESCE(r.state, 'candidate')=?")
        values.append(review_state)
    if q.strip():
        conditions.append("(e.id LIKE ? ESCAPE '\\' OR COALESCE(json_extract(c.data, '$.name'),'') LIKE ? ESCAPE '\\' OR COALESCE(json_extract(e.data, '$.description'),'') LIKE ? ESCAPE '\\')")
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        values.extend([pattern] * 3)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    source = ' FROM events e LEFT JOIN incident_reviews r ON r.event_id=e.id LEFT JOIN cameras c ON c.id=e.camera_id'
    with store.connect() as connection:
        total = connection.execute('SELECT COUNT(*)' + source + where, values).fetchone()[0]
        rows = connection.execute(f"SELECT e.*, {PEOPLE_SQL} AS measured_people, r.state, r.note, r.reviewed_at" + source + where + ' ORDER BY e.created_at DESC, e.id DESC LIMIT ? OFFSET ?', (*values, page_size, (page - 1) * page_size)).fetchall()
    items = []
    for row in rows:
        data = dict(json.loads(row['data']), recorded_at=row['created_at'])
        data['people_visible'] = row['measured_people']
        data['review'] = {'state': row['state'] or 'candidate', 'note': row['note'] or '', 'reviewed_at': row['reviewed_at'], 'by': 'Local owner' if row['state'] else None}
        items.append(data)
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'timezone': timezone, 'generated_at': time.time()}


def review_incident(store, event_id: str, state: str, note: str) -> None:
    with store.lock, store.connect() as connection:
        if not connection.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone():
            raise LookupError('Saved incident was not found')
        now = time.time()
        connection.execute('INSERT INTO incident_reviews VALUES (?, ?, ?, ?) ON CONFLICT(event_id) DO UPDATE SET state=excluded.state,note=excluded.note,reviewed_at=excluded.reviewed_at', (event_id, state, note.strip(), now))
        connection.execute('INSERT INTO audit(created_at, action) VALUES (?, ?)', (now, f'Incident review: {event_id} -> {state}; local owner'))
