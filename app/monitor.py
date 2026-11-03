import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import CheckResult, Incident, Service

logger = logging.getLogger("pulseguard.monitor")


async def ping_service(
    url: str, method: str = "GET", timeout_seconds: int = 10, expected_status: int = 200
) -> Tuple[bool, Optional[int], Optional[float], Optional[str]]:
    """Pings a service endpoint and returns (is_up, status_code, latency_ms, error)."""
    start_time = time.perf_counter()
    try:
        async with httpx.AsyncClient(verify=False, timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.request(method, url)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            is_up = resp.status_code == expected_status
            error = None if is_up else f"Expected {expected_status}, received {resp.status_code}"
            return is_up, resp.status_code, latency_ms, error
    except httpx.TimeoutException:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return False, None, latency_ms, f"Request timed out after {timeout_seconds}s"
    except httpx.ConnectError:
        return False, None, None, "Connection refused / Host unreachable"
    except Exception as e:
        return False, None, None, f"Network error: {str(e)}"


async def perform_service_check(service: Service, db: Session) -> CheckResult:
    """Executes a check for a service and updates incidents."""
    is_up, status_code, latency_ms, error = await ping_service(
        url=service.url,
        method=service.method,
        timeout_seconds=service.timeout_seconds,
        expected_status=service.expected_status,
    )

    check = CheckResult(
        service_id=service.id,
        status_code=status_code,
        response_time_ms=latency_ms,
        is_up=is_up,
        error_message=error,
        checked_at=datetime.utcnow(),
    )
    db.add(check)

    # Incident Management
    unresolved_incident = (
        db.query(Incident)
        .filter(Incident.service_id == service.id, Incident.is_resolved.is_(False))
        .first()
    )

    if not is_up:
        if not unresolved_incident:
            new_incident = Incident(
                service_id=service.id,
                cause=error or "Service unhealthy",
                is_resolved=False,
                started_at=datetime.utcnow(),
            )
            db.add(new_incident)
            logger.warning("INCIDENT OPENED for %s: %s", service.name, error)
    else:
        if unresolved_incident:
            unresolved_incident.is_resolved = True
            unresolved_incident.resolved_at = datetime.utcnow()
            logger.info("INCIDENT RESOLVED for %s", service.name)

    db.commit()
    db.refresh(check)
    return check


async def check_all_active_services():
    """Runs a check cycle across all active services."""
    db = SessionLocal()
    try:
        services = db.query(Service).filter(Service.is_active.is_(True)).all()
        if not services:
            return
        tasks = [perform_service_check(s, db) for s in services]
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        db.close()


async def background_monitoring_loop(interval_seconds: int = 30):
    """Continuous background loop executing health checks."""
    logger.info("Background monitoring worker started (interval: %ss)", interval_seconds)
    while True:
        try:
            await check_all_active_services()
        except Exception as e:
            logger.error("Error in monitoring loop: %s", e)
        await asyncio.sleep(interval_seconds)
