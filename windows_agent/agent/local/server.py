from __future__ import annotations

import csv
import io
import ipaddress
import json
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    start: str = Field(default="00:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="00:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class AutoDetectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rtsp_url: str = Field(min_length=1, max_length=2048)
    channel: int = Field(default=1, ge=1, le=256, strict=True)


class OnvifInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rtsp_url: str = Field(min_length=1, max_length=2048)
    onvif_port: int = Field(default=0, ge=0, le=65535, strict=True)
    media_endpoint: str = Field(default="", max_length=2048)
    profile_token: str = Field(default="", max_length=200)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal['candidate', 'confirmed', 'dismissed']
    note: str = Field(default='', max_length=2000)


class PersonQualityInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['precision', 'balanced'] = 'balanced'
    confidence: float = Field(default=0.6, ge=0.4, le=0.95)
    confirmation_frames: int = Field(default=3, ge=2, le=10)


class PeopleSettingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    capture_enabled: bool = False
    recognition_enabled: bool = False
    retention_days: int = Field(default=7, ge=1, le=30)
    authorised: bool = False


class StaffInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    staff_code: str = Field(min_length=1, max_length=80, pattern=r'\S')
    name: str = Field(min_length=1, max_length=200, pattern=r'\S')
    consent: bool
    consent_note: str = Field(min_length=10, max_length=1000)
    photos: list[str] = Field(min_length=3, max_length=5)


class LinkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_id: str = Field(min_length=1, max_length=64)
    state: Literal['confirmed', 'rejected']


class CameraInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    rtsp_url: str = Field(default="", max_length=2048)
    enabled: bool = True
    detections: dict[str, bool] = Field(default_factory=dict)
    detection_schedule: ScheduleInput = Field(default_factory=ScheduleInput)
    person_quality: PersonQualityInput = Field(default_factory=PersonQualityInput)
    people_count_zones: list[dict] = Field(default_factory=list, max_length=20)
    inventory_zones: list[dict] = Field(default_factory=list, max_length=20)
    restricted_zones: list[dict] = Field(default_factory=list, max_length=20)
    exclusion_zones: list[dict] = Field(default_factory=list, max_length=20)


def validate_stream(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "rtsp" or parts.fragment or not parts.path.startswith("/"):
        raise ValueError("Use an RTSP URL with an encoded password and stream path")
    address = ipaddress.ip_address(parts.hostname or "")
    allowed = (ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"))
    if not any(address in network for network in allowed) or not 1 <= (parts.port or 554) <= 65535:
        raise ValueError("Offline cameras must use a private LAN IPv4 address")


def create_app(store, licence, runtime, assets: Path | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = {}
    attempts = {}
    auth_lock = threading.Lock()
    detection_lock = threading.Lock()
    detection_retry_after = {}
    assets = assets or Path(__file__).parent / "ui"

    @app.middleware("http")
    async def protect_request(request: Request, call_next):
        if request.url.hostname not in {"127.0.0.1", "localhost"}:
            return Response(status_code=400)
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return Response(status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return Response(status_code=403)
        if request.method not in {"GET", "HEAD"} and request.url.path != "/api/restore":
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return Response(status_code=415)
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 8 * 1024 * 1024:
                    return Response(status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        if request.url.path.startswith("/api/") and request.url.path not in {"/api/setup", "/api/login", "/api/bootstrap"}:
            token = request.cookies.get("vantag_local", "")
            with auth_lock:
                now = time.monotonic()
                for old in [key for key, expires in sessions.items() if expires <= now]:
                    sessions.pop(old, None)
                authorized = token in sessions
            if not authorized:
                return Response(status_code=401)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    def require_processing():
        status = licence.status() if licence else None
        if not status or not status.can_process:
            raise HTTPException(403, "A valid signed offline entitlement is required")
        return status

    def login_response():
        token = secrets.token_urlsafe(32)
        with auth_lock:
            sessions.clear()
            sessions[token] = time.monotonic() + 8 * 3600
        response = Response(content='{"ok":true}', media_type="application/json")
        response.set_cookie("vantag_local", token, httponly=True, samesite="strict", max_age=8 * 3600, path="/api/")
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(request, error):
        return Response(content=json.dumps({"detail": str(error)}), status_code=400, media_type="application/json")

    @app.get("/api/bootstrap")
    def bootstrap():
        return {"setup_required": not store.has_owner()}

    @app.post("/api/setup")
    def setup(body: LoginInput):
        store.create_owner(body.username, body.password)
        return login_response()

    @app.post("/api/login")
    def login(body: LoginInput):
        with auth_lock:
            now = time.monotonic()
            history = [stamp for stamp in attempts.get("owner", []) if stamp > now - 300]
            if len(history) >= 5:
                raise HTTPException(429, "Wait five minutes before retrying login")
            attempts["owner"] = history + [now]
        if not store.authenticate(body.username, body.password):
            raise HTTPException(401, "Invalid local credentials")
        with auth_lock:
            attempts.clear()
        return login_response()

    @app.post("/api/logout")
    def logout(request: Request):
        with auth_lock:
            sessions.pop(request.cookies.get("vantag_local"), None)
        response = Response(content='{"ok":true}', media_type="application/json")
        response.delete_cookie("vantag_local", path="/api/")
        return response

    @app.get("/api/status")
    def status():
        return {"mode": "offline", "licence": licence.status().as_dict() if licence else {"state": "missing", "can_process": False}, "site": store.get("site", {"name": "My site", "timezone": "UTC"}), "runtime": runtime.status() if runtime else {}, "delivery": "Local PC only; cloud email and remote dashboards are not connected"}

    @app.post("/api/site")
    def save_site(body: dict):
        name = str(body.get("name", "")).strip()
        timezone = str(body.get("timezone", "UTC"))
        if not name or len(name) > 200:
            raise ValueError("Enter a site name up to 200 characters")
        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a valid IANA timezone") from None
        store.set("site", {"name": name, "timezone": timezone})
        return {"ok": True}

    @app.get("/api/cameras")
    def cameras():
        return store.cameras()

    @app.post("/api/cameras")
    def save_camera(body: CameraInput):
        entitlement = require_processing()
        data = body.model_dump(exclude_none=True)
        if data["rtsp_url"]:
            validate_stream(data["rtsp_url"])
        if any(enabled and feature not in entitlement.claims["features"] for feature, enabled in data["detections"].items()):
            raise HTTPException(403, "A selected AI function is not included in this entitlement")
        for key in ("people_count_zones", "inventory_zones", "exclusion_zones", "restricted_zones"):
            for zone in data[key]:
                box = zone.get("bbox", [])
                if len(box) != 4 or not all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in box) or box[0] >= box[2] or box[1] >= box[3]:
                    raise ValueError("Zones require a normalized [left, top, right, bottom] rectangle")
                zone.update(normalized=True, id=zone.get("id") or secrets.token_hex(8))
        camera_id = store.save_camera(data)
        try:
            applied = runtime.apply_camera(camera_id) if runtime else False
        except Exception as exc:
            return {"id": camera_id, "applied": False, "application_error": True, "message": f"Configuration saved, but could not be applied ({type(exc).__name__}). Check Licence & health and retry Start / apply configuration."}
        return {"id": camera_id, "applied": applied, "application_error": False, "message": "Saved and applied to monitoring. This camera may briefly reconnect; other cameras remain running." if applied else "Saved. Monitoring is stopped; start it on Overview when ready."}

    @app.delete("/api/cameras/{camera_id}")
    def delete_camera(camera_id: str):
        if runtime:
            runtime.remove_camera(camera_id)
        store.delete_camera(camera_id)
        return {"ok": True}

    @app.post("/api/probe")
    def probe(body: dict):
        require_processing()
        url = str(body.get("rtsp_url", ""))
        validate_stream(url)
        import base64
        frame = runtime.frame_for_stream(url) if runtime else None
        if frame:
            return {"success": True, "thumbnail": base64.b64encode(frame[0]).decode("ascii"), "message": "Video frame decoded by the running camera; no extra NVR connection opened"}
        from ..discovery import _try_rtsp, diagnose_rtsp
        from urllib.parse import unquote
        parts = urlsplit(url)
        result = _try_rtsp(parts.hostname, parts.port or 554, parts.path + ("?" + parts.query if parts.query else ""), unquote(parts.username or ""), unquote(parts.password or ""))
        message = "Video frame decoded" if result else f"No video frame received from {parts.hostname}:{parts.port or 554}{parts.path}. {diagnose_rtsp(url, authenticate=True)}"
        return {"success": bool(result), "thumbnail": result.get("thumbnail") if result else None, "message": message}

    @app.post("/api/cameras/{camera_id}/test")
    def test_saved_camera(camera_id: str):
        require_processing()
        camera = next((item for item in store.cameras(include_secrets=True) if item["id"] == camera_id), None)
        if camera is None:
            raise HTTPException(404, "Saved camera was not found")
        return probe({"rtsp_url": camera["rtsp_url"]})

    @app.post("/api/auto-detect")
    def auto_detect(body: AutoDetectInput):
        require_processing()
        validate_stream(body.rtsp_url)
        if not detection_lock.acquire(blocking=False):
            raise HTTPException(409, "Another camera detection is running. Wait for its result.")
        try:
            host = urlsplit(body.rtsp_url).hostname
            now = time.monotonic()
            for previous in [key for key, until in detection_retry_after.items() if until <= now]:
                detection_retry_after.pop(previous, None)
            if detection_retry_after.get(host, 0) > now:
                raise HTTPException(429, "Wait one minute before detecting this device again to reduce account-lockout risk. Check the device permissions/password first.")
            detection_retry_after[host] = now + 60
            from ..discovery import auto_diagnose_stream
            return auto_diagnose_stream(body.rtsp_url, channel=body.channel)
        finally:
            detection_lock.release()

    @app.post("/api/onvif/{operation}")
    def onvif(operation: str, body: OnvifInput):
        require_processing()
        validate_stream(body.rtsp_url)
        if operation not in {"profiles", "test-profile"}:
            raise HTTPException(404)
        if operation == "test-profile" and (not body.media_endpoint or not body.profile_token):
            raise ValueError("Read device profiles and select a profile first")
        if not detection_lock.acquire(blocking=False):
            raise HTTPException(409, "Another camera test is running. Wait for its result.")
        try:
            host = urlsplit(body.rtsp_url).hostname
            key = (host, operation)
            now = time.monotonic()
            if detection_retry_after.get(key, 0) > now:
                raise HTTPException(429, "Wait one minute before repeating this ONVIF action to reduce device account-lockout risk.")
            detection_retry_after[key] = now + 60
            from .onvif import OnvifReader
            reader = OnvifReader(body.rtsp_url, body.onvif_port)
            try:
                if operation == "profiles":
                    return reader.profiles()
                url = reader.stream(body.media_endpoint, body.profile_token)
                validate_stream(url)
                from ..discovery import _try_rtsp
                from urllib.parse import unquote
                parts = urlsplit(url)
                path = parts.path + ("?" + parts.query if parts.query else "")
                result = _try_rtsp(parts.hostname, parts.port or 554, path, unquote(parts.username or ""), unquote(parts.password or ""))
                return {"success": bool(result), "path": path if result else None, "port": parts.port or 554, "thumbnail": result.get("thumbnail") if result else None, "message": "Device-reported profile decoded successfully. Review the picture to identify the camera/channel, then save. No configuration was saved automatically." if result else "ONVIF supplied a real stream URI, but no video frame decoded. The path has not been applied. Verify the account's RTSP/media permission, codec, stream encryption and session limits. ONVIF profile access alone does not confirm video."}
            finally:
                reader.close()
        finally:
            detection_lock.release()

    @app.get("/api/frame/{camera_id}")
    def frame(camera_id: str):
        require_processing()
        result = runtime.sink.frame(camera_id) if runtime else None
        if not result:
            raise HTTPException(404, "No recent video frame")
        return Response(result[0], media_type="image/jpeg", headers={"X-Frame-Timestamp": str(result[1])})

    @app.post("/api/monitoring/{action}")
    def monitoring(action: str):
        if not runtime:
            raise HTTPException(503, "Local runtime unavailable")
        if action == "start":
            require_processing()
            runtime.start()
        elif action == "stop":
            runtime.stop()
        else:
            raise HTTPException(404)
        return runtime.status()

    @app.get("/api/evidence/{digest}")
    def evidence(digest: str):
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise HTTPException(404)
        path = store.directory / "evidence" / digest
        if not path.is_file():
            raise HTTPException(404, "Evidence file is missing")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/events")
    def events():
        return store.events()

    @app.get("/api/incidents")
    def incident_report(q: str = Query('', max_length=200), camera_id: str = Query('', max_length=64), event_type: str = Query('', max_length=80), start_day: str = '', end_day: str = '', min_people: int | None = Query(None, ge=0, le=10000), review_state: Literal['', 'candidate', 'confirmed', 'dismissed'] = '', page: int = Query(1, ge=1, le=1000000), page_size: int = Query(50, ge=1, le=1000)):
        return store.incident_search(q=q, camera_id=camera_id, event_type=event_type, start_day=start_day, end_day=end_day, min_people=min_people, review_state=review_state, page=page, page_size=page_size)

    @app.post("/api/incidents/{event_id}/review")
    def review_saved_incident(event_id: str, body: ReviewInput):
        from .reports import review_incident
        try:
            review_incident(store, event_id, body.state, body.note)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    def people_tools():
        tools = getattr(runtime, 'people', None)
        if tools is None:
            raise HTTPException(503, 'Local people tools unavailable in this build')
        return tools

    @app.exception_handler(LookupError)
    async def missing_record(request, error):
        return Response(content=json.dumps({'detail': str(error)}), status_code=404, media_type='application/json')

    @app.get('/api/people/settings')
    def people_settings():
        tools = people_tools()
        return {'settings': tools.settings(), 'status': dict(tools.status), 'faces': dict(tools.faces.status)}

    @app.post('/api/people/settings')
    def save_people_settings(body: PeopleSettingsInput):
        return people_tools().configure(body.model_dump())

    @app.get('/api/people/staff')
    def staff_directory():
        return people_tools().staff()

    @app.post('/api/people/staff')
    def enrol_staff(body: StaffInput):
        return people_tools().enrol(body.model_dump())

    @app.delete('/api/people/staff/{staff_id}')
    def delete_staff(staff_id: str):
        people_tools().delete_staff(staff_id)
        return {'ok': True}

    @app.get('/api/people/observations')
    def people_observations(camera_id: str = Query('', max_length=64), page: int = Query(1, ge=1, le=1000000)):
        return people_tools().observations(camera_id=camera_id, page=page)

    @app.delete('/api/people/observations')
    def clear_people_observations():
        people_tools().clear_observations()
        return {'ok': True}

    @app.get('/api/people/observations/{identifier}/thumbnail')
    def people_thumbnail(identifier: str):
        tools = people_tools()
        tools.prune()
        return Response(tools.thumbnail(identifier), media_type='image/jpeg')

    @app.get('/api/people/observations/{identifier}/candidates')
    def people_candidates(identifier: str, minutes: int = Query(30, ge=1, le=1440)):
        return people_tools().candidates(identifier, minutes=minutes)

    @app.post('/api/people/observations/{identifier}/links')
    def review_person_link(identifier: str, body: LinkInput):
        tools = people_tools()
        tools.prune()
        tools.review_link(identifier, body.target_id, body.state)
        return tools.timeline(identifier)

    @app.get('/api/people/observations/{identifier}/timeline')
    def person_timeline(identifier: str):
        tools = people_tools()
        tools.prune()
        return tools.timeline(identifier)

    @app.get("/api/counts")
    def counts(day: str):
        from datetime import date
        date.fromisoformat(day)
        return store.counts(day)

    @app.get("/api/counts.csv")
    def count_export(day: str):
        rows = counts(day)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Date", "Camera ID", "People visible at last sample", "Track observations (not unique visitors)", "Sample time (UTC epoch)"])
        for row in rows:
            writer.writerow([day, row["camera_id"], row["people_visible"], row["entries"], row["updated_at"]])
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="people-count.csv"'})

    @app.get("/api/storage")
    def storage():
        from .storage import storage_status
        return storage_status(store)

    @app.post("/api/storage")
    def save_storage(body: dict):
        quota = body.get("quota_mb")
        if not isinstance(quota, int) or isinstance(quota, bool) or not 256 <= quota <= 1048576:
            raise ValueError("Choose a local storage quota from 256 MB to 1 TB")
        store.set("storage", {"quota_mb": quota})
        store.audit("Local storage quota changed")
        return storage()

    @app.get("/api/backup")
    def backup():
        from .storage import export_backup
        temporary = tempfile.NamedTemporaryFile(prefix="vantag-private-backup-", suffix=".zip", delete=False)
        path = Path(temporary.name)
        temporary.close()
        try:
            export_backup(store, path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return FileResponse(path, media_type="application/zip", filename="vantag-private-site-backup.zip", background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post("/api/restore")
    async def restore(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/zip":
            raise HTTPException(415, "Upload a private site backup ZIP")
        if request.headers.get("x-vantag-restore") != "replace-site-data":
            raise HTTPException(403, "Explicit local restore confirmation is required")
        from .storage import restore_backup
        import zipfile
        with tempfile.TemporaryDirectory(prefix="vantag-upload-") as directory:
            path = Path(directory) / "backup.zip"
            total = 0
            with path.open("wb") as output:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > 2 * 1024 * 1024 * 1024:
                        raise HTTPException(413, "Console restore is limited to 2 GB; use a stopped-site filesystem backup for larger sites")
                    output.write(chunk)
            if runtime:
                await run_in_threadpool(runtime.stop)
            try:
                await run_in_threadpool(restore_backup, store, path)
            except (zipfile.BadZipFile, OSError) as exc:
                raise HTTPException(400, "Backup could not be restored; check integrity, free space and the original Windows account") from exc
        return {"ok": True, "message": "Site restored. Current local owner and entitlement were preserved. Restart monitoring when ready."}

    @app.post("/api/licence")
    def import_licence(body: dict):
        if not licence:
            raise HTTPException(503, "No trusted licence keys installed")
        result = licence.install(body)
        return result.as_dict()

    @app.get("/api/renewal-request")
    def renewal_request():
        if not licence:
            raise HTTPException(503, "No licence manager")
        return Response(json.dumps(licence.request(), indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="vantag-renewal-request.json"'})

    @app.get("/")
    def index():
        page = assets / "offline.html"
        return FileResponse(page) if page.is_file() else HTMLResponse("Local console assets are missing", status_code=503)

    app.mount("/assets", StaticFiles(directory=assets / "assets", check_dir=False), name="offline-assets")
    return app
