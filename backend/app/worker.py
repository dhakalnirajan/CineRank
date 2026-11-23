"""UTC scheduler for catalogue synchronization and maintenance."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.session import SessionLocal, engine
from app.db.schema_guard import validate_database_schema
from app.models.entities import JobLease, JobRun
from app.services.catalogue_service import rebuild_catalogue_sort_index
from app.services.recommendation_service import recommendation_service
from crawler.movie_crawler import MovieCrawler

configure_logging()
logger = logging.getLogger("cinerank.worker")
DAILY_JOB = "daily_catalogue_sync"
REFRESH_JOB = "model_refresh_60d"
ROOT = Path(__file__).resolve().parents[1]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_lease(db, job_name: str, owner: str) -> bool:
    now = _now()
    expires = now + timedelta(seconds=settings.JOB_LEASE_SECONDS)
    try:
        lease = db.query(JobLease).filter_by(job_name=job_name).with_for_update().first()
        if lease is None:
            db.add(JobLease(job_name=job_name, owner_token=owner, lease_expires_at=expires))
            db.commit()
            return True
        lease_expiry = lease.lease_expires_at
        if lease_expiry.tzinfo is None:
            lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)
        if lease_expiry > now:
            db.rollback()
            return False
        lease.owner_token = owner
        lease.lease_expires_at = expires
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def owns_lease(db, job_name: str, owner: str) -> bool:
    lease = db.query(JobLease).filter_by(job_name=job_name, owner_token=owner).first()
    if not lease:
        return False
    expires = lease.lease_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > _now()


class LeaseHeartbeat:
    """Renew a running job lease using its own DB session until the job finishes."""
    def __init__(self, job_name: str, owner: str):
        self.job_name = job_name
        self.owner = owner
        self.stop_event = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"lease-{job_name}", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self):
        interval = max(5, settings.JOB_LEASE_SECONDS // 3)
        while not self.stop_event.wait(interval):
            db = SessionLocal()
            try:
                now = _now()
                result = db.execute(update(JobLease).where(
                    JobLease.job_name == self.job_name,
                    JobLease.owner_token == self.owner,
                    JobLease.lease_expires_at > now,
                ).values(lease_expires_at=now + timedelta(seconds=settings.JOB_LEASE_SECONDS)))
                db.commit()
                if result.rowcount != 1:
                    self.lost.set()
                    return
            except Exception:
                db.rollback()
                logger.exception("Lease heartbeat failed for %s", self.job_name)
                self.lost.set()
                return
            finally:
                db.close()


def _run_record(db, job_name: str) -> JobRun:
    run = db.query(JobRun).filter_by(job_name=job_name).first()
    if run is None:
        run = JobRun(job_name=job_name)
        db.add(run)
        db.flush()
    run.last_attempt_date = _now().date()
    run.last_status = "running"
    run.last_error = None
    db.commit()
    return run


def _finish_job(job_name: str, owner: str, success: bool, detail: str | None = None) -> None:
    db = SessionLocal()
    try:
        lease = db.query(JobLease).filter_by(
            job_name=job_name, owner_token=owner
        ).with_for_update().first()
        if lease is None:
            logger.error("Cannot finalize %s: lease ownership was lost", job_name)
            db.rollback()
            return
        lease_expiry = lease.lease_expires_at
        if lease_expiry.tzinfo is None:
            lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)
        if lease_expiry <= _now():
            logger.error("Cannot finalize %s: lease expired before finalization", job_name)
            db.rollback()
            return
        run = db.query(JobRun).filter_by(job_name=job_name).first()
        if run is None:
            run = JobRun(job_name=job_name)
            db.add(run)
        if success:
            now = _now()
            run.last_success_date = now.date()
            run.last_success_at = now
            run.last_status = "success"
            run.last_error = detail
        else:
            run.last_status = "failed"
            run.last_error = (detail or "unknown error")[:4000]
        # Update the job record and release only this owner's lease atomically.
        db.delete(lease)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not finalize scheduled job %s", job_name)
        raise
    finally:
        db.close()


def run_daily_job() -> bool:
    owner = uuid.uuid4().hex
    db = SessionLocal()
    try:
        if not claim_lease(db, DAILY_JOB, owner):
            logger.info("Another worker owns %s", DAILY_JOB)
            return False
        _run_record(db, DAILY_JOB)
    finally:
        db.close()
    heartbeat = LeaseHeartbeat(DAILY_JOB, owner)
    heartbeat.start()
    try:
        db = SessionLocal()
        try:
            crawl_result = MovieCrawler().sync_latest(db)
        finally:
            db.close()
        db = SessionLocal()
        try:
            sort_result = rebuild_catalogue_sort_index(db)
            if heartbeat.lost.is_set() or not owns_lease(db, DAILY_JOB, owner):
                raise RuntimeError("Daily worker lease expired; rerun is idempotent")
            detail = (
                f"crawl={crawl_result}; sort={sort_result}; "
                "model_evaluation=skipped_v2_release_requires_offline_validation"
            )
        finally:
            db.close()
        if heartbeat.lost.is_set():
            raise RuntimeError("Daily worker lost its lease before finalization")
        _finish_job(DAILY_JOB, owner, True, detail)
        logger.info("Daily job complete: %s", detail)
        return True
    except Exception as exc:
        logger.exception("Daily catalogue job failed")
        _finish_job(DAILY_JOB, owner, False, str(exc))
        return False
    finally:
        heartbeat.stop()


def run_model_refresh_job() -> bool:
    """Do not run the legacy v1 trainer against a v2 production release.

    Model refresh is an offline release-engineering workflow: train, evaluate on
    temporal holdouts, verify parity and hashes, then deploy a new immutable v2
    release. This worker must never promote a legacy bundle over the active release.
    """
    logger.warning(
        "Automatic model refresh is disabled: serving uses immutable v2 releases; "
        "use the documented offline validation and release activation workflow"
    )
    return False



def run_scheduler() -> None:
    validate_database_schema(engine)
    logger.info("Scheduler active: daily catalogue sync at 12:00 UTC; model releases are managed offline")
    while True:
        now = _now()
        db = SessionLocal()
        try:
            daily = db.query(JobRun).filter_by(job_name=DAILY_JOB).first()
            daily_ran_today = bool(daily and daily.last_success_date == now.date())
            daily_failed_today = bool(daily and daily.last_attempt_date == now.date() and daily.last_status == "failed")
            refresh_due = False  # v2 releases are deployed through offline validation.
        finally:
            db.close()

        daily_is_due = now.hour > 12 or (now.hour == 12 and now.minute >= 0)
        if daily_is_due and not daily_ran_today and not daily_failed_today:
            run_daily_job()
        if refresh_due:
            run_model_refresh_job()
        time.sleep(max(5, settings.SCHEDULER_POLL_SECONDS))


if __name__ == "__main__":
    run_scheduler()
