#!/usr/bin/env python3
"""
ML Training Scheduler.

This script schedules automated ML training pipeline runs:
- Weekly data refresh (ingest new candles)
- Monthly full retraining (full pipeline)
- Model comparison before promotion
- Admin notification on completion

Usage:
    uv run python scripts/run_ml_scheduler.py              # Start scheduler
    uv run python scripts/run_ml_scheduler.py --once       # Run once and exit
    uv run python scripts/run_ml_scheduler.py --dry-run    # Show scheduled jobs without running

Schedule (default):
    - Data refresh: Every Sunday at 02:00 UTC
    - Full retraining: 1st of every month at 03:00 UTC

Reference: docs/ML_TRAINING_PIPELINE_SPEC.md §10
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logger = structlog.get_logger()

# Configuration
SCRIPT_DIR = Path(__file__).parent
ML_TRAINING_SCRIPT = SCRIPT_DIR / "run_ml_training.py"
DEFAULT_MARKETS = "BTC-USDT,ETH-USDT,SOL-USDT,XRP-USDT,DOGE-USDT"
DEFAULT_MONTHS = 6


def run_pipeline_command(args: list[str]) -> tuple[bool, str]:
    """Run ML training pipeline command synchronously."""
    cmd = [sys.executable, str(ML_TRAINING_SCRIPT)] + args
    logger.info("pipeline_command_started", command=" ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
            cwd=SCRIPT_DIR.parent,
        )

        success = result.returncode == 0
        output = result.stdout + result.stderr

        logger.info(
            "pipeline_command_completed",
            success=success,
            return_code=result.returncode,
        )

        return success, output

    except subprocess.TimeoutExpired:
        logger.error("pipeline_command_timeout", command=" ".join(cmd))
        return False, "Command timed out after 1 hour"
    except Exception as e:
        logger.error("pipeline_command_failed", error=str(e))
        return False, str(e)


def job_weekly_data_refresh() -> None:
    """
    Weekly data refresh job.

    Fetches new candles for all markets and updates Parquet storage.
    Runs every Sunday at 02:00 UTC.
    """
    logger.info("job_weekly_data_refresh_started")

    success, output = run_pipeline_command(
        [
            "--ingest",
            "--markets",
            DEFAULT_MARKETS,
            "--months",
            "1",  # Only fetch last month for refresh
        ]
    )

    if success:
        logger.info("job_weekly_data_refresh_completed")
        # TODO: Send Telegram notification to admin
    else:
        logger.error("job_weekly_data_refresh_failed", output=output[:500])
        # TODO: Send Telegram alert to admin


def job_monthly_retraining() -> None:
    """
    Monthly full retraining job.

    Runs the complete ML training pipeline:
    1. Data ingestion (6 months)
    2. Feature engineering
    3. Simulation & labels
    4. Model training
    5. Model evaluation
    6. Model promotion (if quality thresholds pass)

    Runs 1st of every month at 03:00 UTC.
    """
    logger.info("job_monthly_retraining_started")

    success, output = run_pipeline_command(
        [
            "--full",
            "--markets",
            DEFAULT_MARKETS,
            "--months",
            str(DEFAULT_MONTHS),
        ]
    )

    if success:
        logger.info("job_monthly_retraining_completed")
        # TODO: Send Telegram notification to admin with training results
    else:
        logger.error("job_monthly_retraining_failed", output=output[:500])
        # TODO: Send Telegram alert to admin


def job_model_evaluation_report() -> None:
    """
    Weekly model evaluation report.

    Generates model performance report for admin review.
    Runs every Monday at 08:00 UTC.
    """
    logger.info("job_model_evaluation_report_started")

    success, output = run_pipeline_command(["--status"])

    if success:
        logger.info("job_model_evaluation_report_completed")
        # TODO: Parse output and send formatted report to admin via Telegram
    else:
        logger.error("job_model_evaluation_report_failed", output=output[:500])


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Weekly data refresh: Every Sunday at 02:00 UTC
    scheduler.add_job(
        job_weekly_data_refresh,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_data_refresh",
        name="Weekly Data Refresh",
        replace_existing=True,
    )

    # Monthly retraining: 1st of every month at 03:00 UTC
    scheduler.add_job(
        job_monthly_retraining,
        trigger=CronTrigger(day=1, hour=3, minute=0),
        id="monthly_retraining",
        name="Monthly Model Retraining",
        replace_existing=True,
    )

    # Weekly evaluation report: Every Monday at 08:00 UTC
    scheduler.add_job(
        job_model_evaluation_report,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_evaluation_report",
        name="Weekly Model Evaluation Report",
        replace_existing=True,
    )

    return scheduler


def print_schedule(scheduler: AsyncIOScheduler) -> None:
    """Print scheduled jobs."""
    print("\n" + "=" * 60)
    print("ML TRAINING SCHEDULER - SCHEDULED JOBS")
    print("=" * 60)

    for job in scheduler.get_jobs():
        print(f"\n  Job: {job.name}")
        print(f"  ID: {job.id}")
        print(f"  Trigger: {job.trigger}")
        # next_run_time only available after scheduler starts
        next_run = getattr(job, "next_run_time", None)
        if next_run:
            print(f"  Next run: {next_run}")

    print("\n" + "=" * 60)


async def run_scheduler() -> None:
    """Run the scheduler indefinitely."""
    scheduler = create_scheduler()
    scheduler.start()

    print_schedule(scheduler)

    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))
    print("\nScheduler started. Press Ctrl+C to stop.\n")

    try:
        # Keep the scheduler running
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("scheduler_stopped")
        print("\nScheduler stopped.")


def run_once() -> None:
    """Run all jobs once (for testing)."""
    print("\n[1/3] Running weekly data refresh...")
    job_weekly_data_refresh()

    print("\n[2/3] Running monthly retraining...")
    job_monthly_retraining()

    print("\n[3/3] Running model evaluation report...")
    job_model_evaluation_report()

    print("\nAll jobs completed.")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ML Training Scheduler")
    parser.add_argument("--once", action="store_true", help="Run all jobs once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Show scheduled jobs without running")
    args = parser.parse_args()

    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    )

    if args.dry_run:
        scheduler = create_scheduler()
        print_schedule(scheduler)
        return 0

    if args.once:
        run_once()
        return 0

    # Run scheduler indefinitely
    try:
        asyncio.run(run_scheduler())
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())