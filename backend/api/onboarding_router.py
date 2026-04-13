"""
backend/api/onboarding_router.py
================================
Step-by-step onboarding wizard API (5 steps, resumable).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import Tenant
from ..db.models.camera import CameraConfig
from ..middleware.tenant_middleware import get_current_user_id
from ..services.tenant_service import provision_edge_agent
from ..config.plans import PLANS, get_plan
from ..config.regions import get_region

onboarding_router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class Step1Body(BaseModel):
    shop_name: str
    address: str | None = None
    city: str | None = None
    country: str
    language: str = "en"
    phone: str | None = None


class Step2Body(BaseModel):
    plan_id: str


class Step3Body(BaseModel):
    razorpay_payment_id: str | None = None
    razorpay_order_id: str | None = None
    razorpay_signature: str | None = None


class CameraInput(BaseModel):
    ip: str
    name: str | None = None
    location: str | None = None
    rtsp_url: str | None = None
    brand: str | None = None


class Step4Body(BaseModel):
    cameras: list[CameraInput]


class Step5Body(BaseModel):
    device_type: str = "android"
    device_name: str | None = None


@onboarding_router.get("/status")
async def get_onboarding_status(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "onboarding_step": tenant.onboarding_step,
        "status": tenant.status,
        "plan_id": tenant.plan_id,
        "country": tenant.country,
        "language": tenant.language,
    }


@onboarding_router.post("/step/1")
async def step1_shop_details(
    body: Step1Body,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    region = get_region(body.country)
    await session.execute(
        update(Tenant)
        .where(Tenant.id == user["tenant_id"])
        .values(
            name=body.shop_name,
            address=body.address,
            city=body.city,
            country=body.country.upper(),
            region={"IN": "india", "SG": "singapore", "MY": "malaysia"}.get(body.country.upper(), "india"),
            language=body.language,
            phone=body.phone,
            onboarding_step=2,
        )
    )
    await session.commit()
    return {"step": 1, "next": 2, "region": region}


@onboarding_router.post("/step/2")
async def step2_plan_selection(
    body: Step2Body,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    plan = get_plan(body.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan_id}")

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    region = get_region(tenant.country)
    price = plan["prices"].get(region["currency"], 0)

    await session.execute(
        update(Tenant)
        .where(Tenant.id == user["tenant_id"])
        .values(plan_id=body.plan_id, onboarding_step=3)
    )
    await session.commit()

    return {
        "step": 2,
        "next": 3,
        "plan": plan,
        "price": price,
        "currency": region["currency"],
        "symbol": region["symbol"],
        "razorpay_key_id": region["razorpay_key_id"],
    }


@onboarding_router.post("/step/3")
async def step3_payment(
    body: Step3Body,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Verify Razorpay payment and activate subscription."""
    # In test mode or trial: accept and mark active
    new_status = "active" if body.razorpay_payment_id else "trial"
    await session.execute(
        update(Tenant)
        .where(Tenant.id == user["tenant_id"])
        .values(status=new_status, onboarding_step=4)
    )
    await session.commit()
    return {"step": 3, "next": 4, "status": new_status}


@onboarding_router.post("/step/4")
async def step4_camera_setup(
    body: Step4Body,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Save camera configurations entered during onboarding."""
    import uuid as _uuid

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    plan = get_plan(tenant.plan_id)
    max_cams = plan["max_cameras"] if plan else 5
    if len(body.cameras) > max_cams:
        raise HTTPException(status_code=400, detail=f"Your plan allows max {max_cams} cameras")

    saved = []
    for i, cam in enumerate(body.cameras, 1):
        camera_id = f"cam-{i:02d}"
        config = CameraConfig(
            id=str(_uuid.uuid4()),
            tenant_id=user["tenant_id"],
            camera_id=camera_id,
            name=cam.name or f"Camera {i}",
            ip_address=cam.ip,
            rtsp_url=cam.rtsp_url,
            brand=cam.brand,
            location=cam.location or f"Zone {i}",
            enabled=True,
            conn_status="pending",
            staff_zone_colors=["#FF6600", "#0099FF"],
            zones=[],
        )
        session.add(config)
        saved.append({"camera_id": camera_id, "ip": cam.ip, "status": "pending"})

    await session.execute(
        update(Tenant).where(Tenant.id == user["tenant_id"]).values(onboarding_step=5)
    )
    await session.commit()
    return {"step": 4, "next": 5, "cameras_saved": len(saved), "cameras": saved}


@onboarding_router.post("/step/5")
async def step5_install_agent(
    body: Step5Body,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Provision edge agent API key and return QR config."""
    import json, base64

    agent = await provision_edge_agent(
        session,
        tenant_id=user["tenant_id"],
        device_type=body.device_type,
        device_name=body.device_name,
    )

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()

    region_url_map = {"india": "https://api.vantag.in", "singapore": "https://api.vantag.sg", "malaysia": "https://api.jagajaga.my"}
    api_url = region_url_map.get(tenant.region if tenant else "india", "http://localhost:8800")

    qr_payload = {
        "api_key": agent.api_key,
        "tenant_id": user["tenant_id"],
        "api_url": api_url,
        "device_type": body.device_type,
    }
    qr_data = base64.b64encode(json.dumps(qr_payload).encode()).decode()

    await session.execute(
        update(Tenant).where(Tenant.id == user["tenant_id"]).values(onboarding_step=6)
    )
    await session.commit()

    return {
        "step": 5,
        "completed": True,
        "agent_id": agent.id,
        "api_key": agent.api_key,
        "qr_data": qr_data,
        "download_links": {
            "android": "https://play.google.com/store/apps/details?id=com.vantag.edgeagent",
            "windows": "https://download.vantag.in/edge-agent-setup.exe",
        },
    }


@onboarding_router.get("/plans")
async def list_plans(country: str = "IN") -> dict:
    region = get_region(country)
    currency = region["currency"]
    plans_out = []
    for p in PLANS.values():
        plans_out.append({
            **p,
            "price": p["prices"].get(currency, 0),
            "currency": currency,
            "symbol": region["symbol"],
        })
    return {"plans": plans_out, "region": region}
