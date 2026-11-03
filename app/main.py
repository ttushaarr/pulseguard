import asyncio
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import CheckResult, Incident, Service
from app.monitor import background_monitoring_loop, perform_service_check
from app.schemas import (
    CheckResultResponse,
    IncidentResponse,
    ServiceCreate,
    ServiceDetail,
    ServiceUpdate,
    SystemStats,
)

# Initialize database schema
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed default demonstration services if table is empty
    db = next(get_db())
    if db.query(Service).count() == 0:
        demo_services = [
            Service(name="GitHub API", url="https://api.github.com", interval_seconds=30),
            Service(name="Cloudflare DNS", url="https://1.1.1.1", interval_seconds=30),
            Service(name="Hacker News API", url="https://hacker-news.firebaseio.com/v0/topstories.json", interval_seconds=30),
            Service(name="HTTPBin Status 200", url="https://httpbin.org/status/200", interval_seconds=30),
        ]
        db.add_all(demo_services)
        db.commit()
    db.close()

    # Launch background monitor task
    monitor_task = asyncio.create_task(background_monitoring_loop(settings.DEFAULT_CHECK_INTERVAL))
    yield
    monitor_task.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Real-Time Service Health & API Monitoring Engine with Live Visual Dashboard",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    return FileResponse("app/static/index.html")


@app.get("/health", tags=["System"])
def system_health():
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/api/stats", response_model=SystemStats, tags=["Metrics"])
def get_system_stats(db: Session = Depends(get_db)):
    services = db.query(Service).all()
    total_services = len(services)

    if total_services == 0:
        return SystemStats(
            total_services=0,
            services_up=0,
            services_down=0,
            overall_uptime_pct=100.0,
            avg_response_time_ms=0.0,
            active_incidents=0,
        )

    services_up = 0
    services_down = 0
    latencies = []

    for s in services:
        latest = (
            db.query(CheckResult)
            .filter(CheckResult.service_id == s.id)
            .order_by(CheckResult.checked_at.desc())
            .first()
        )
        if latest:
            if latest.is_up:
                services_up += 1
            else:
                services_down += 1
            if latest.response_time_ms is not None:
                latencies.append(latest.response_time_ms)

    active_incidents = (
        db.query(Incident).filter(Incident.is_resolved.is_(False)).count()
    )

    all_checks = db.query(CheckResult).all()
    if all_checks:
        uptime_pct = round((sum(1 for c in all_checks if c.is_up) / len(all_checks)) * 100, 2)
    else:
        uptime_pct = 100.0

    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    return SystemStats(
        total_services=total_services,
        services_up=services_up,
        services_down=services_down,
        overall_uptime_pct=uptime_pct,
        avg_response_time_ms=avg_latency,
        active_incidents=active_incidents,
    )


@app.post("/api/services", response_model=ServiceDetail, status_code=status.HTTP_201_CREATED, tags=["Services"])
def create_service(service_in: ServiceCreate, db: Session = Depends(get_db)):
    service = Service(**service_in.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@app.get("/api/services", response_model=List[ServiceDetail], tags=["Services"])
def list_services(db: Session = Depends(get_db)):
    services = db.query(Service).all()
    result = []
    for s in services:
        checks = (
            db.query(CheckResult)
            .filter(CheckResult.service_id == s.id)
            .order_by(CheckResult.checked_at.desc())
            .limit(50)
            .all()
        )
        latest = checks[0] if checks else None
        uptime = 100.0
        if checks:
            uptime = round((sum(1 for c in checks if c.is_up) / len(checks)) * 100, 1)

        result.append(
            ServiceDetail(
                id=s.id,
                name=s.name,
                url=s.url,
                method=s.method,
                interval_seconds=s.interval_seconds,
                timeout_seconds=s.timeout_seconds,
                expected_status=s.expected_status,
                is_active=s.is_active,
                created_at=s.created_at,
                is_up=latest.is_up if latest else None,
                last_checked_at=latest.checked_at if latest else None,
                last_response_time_ms=latest.response_time_ms if latest else None,
                uptime_percentage=uptime,
            )
        )
    return result


@app.get("/api/services/{service_id}", response_model=ServiceDetail, tags=["Services"])
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    checks = (
        db.query(CheckResult)
        .filter(CheckResult.service_id == service.id)
        .order_by(CheckResult.checked_at.desc())
        .limit(50)
        .all()
    )
    latest = checks[0] if checks else None
    uptime = 100.0
    if checks:
        uptime = round((sum(1 for c in checks if c.is_up) / len(checks)) * 100, 1)

    return ServiceDetail(
        id=service.id,
        name=service.name,
        url=service.url,
        method=service.method,
        interval_seconds=service.interval_seconds,
        timeout_seconds=service.timeout_seconds,
        expected_status=service.expected_status,
        is_active=service.is_active,
        created_at=service.created_at,
        is_up=latest.is_up if latest else None,
        last_checked_at=latest.checked_at if latest else None,
        last_response_time_ms=latest.response_time_ms if latest else None,
        uptime_percentage=uptime,
    )


@app.patch("/api/services/{service_id}", response_model=ServiceDetail, tags=["Services"])
def update_service(service_id: int, service_update: ServiceUpdate, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for key, value in service_update.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    db.commit()
    db.refresh(service)
    return service


@app.delete("/api/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Services"])
def delete_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()


@app.post("/api/services/{service_id}/check", response_model=CheckResultResponse, tags=["Services"])
async def trigger_manual_check(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    check = await perform_service_check(service, db)
    return check


@app.get("/api/services/{service_id}/history", response_model=List[CheckResultResponse], tags=["Services"])
def get_service_history(service_id: int, limit: int = 30, db: Session = Depends(get_db)):
    checks = (
        db.query(CheckResult)
        .filter(CheckResult.service_id == service_id)
        .order_by(CheckResult.checked_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(checks))


@app.get("/api/incidents", response_model=List[IncidentResponse], tags=["Incidents"])
def list_incidents(db: Session = Depends(get_db)):
    return db.query(Incident).order_by(Incident.started_at.desc()).limit(20).all()
