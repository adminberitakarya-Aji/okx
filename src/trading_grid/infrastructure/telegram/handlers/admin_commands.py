"""
[Phase 12] Admin Telegram commands.

Provides the /admin command with sub-commands for system administration:
- /admin ml_status    → ML model registry status
- /admin training     → Last training run status
- /admin performance  → Grid P&L summary
- /admin retrain      → Trigger retraining
- /admin alerts       → Recent alerts
- /admin ingestion    → Data freshness per market

Authorization: SYSTEM_ADMIN (Level 5) only.
Admin access is checked via check_admin_authorization() which requires
either TELEGRAM_ADMIN_USER_ID config or DB authorization_level >= 5.
Open access mode does NOT grant admin access.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from trading_grid.infrastructure.telegram.handlers._auth import check_admin_authorization
from trading_grid.infrastructure.telegram.handlers._state import get_service_container

if TYPE_CHECKING:
    from aiogram.types import Message

logger = structlog.get_logger()

# Path to the ML pipeline state file (written by run_ml_training.py)
_PIPELINE_STATE_PATH = Path("data/pipeline_state.json")

# Background training task registry (prevents concurrent runs)
_training_tasks: dict[str, asyncio.Task[None]] = {}

ADMIN_HELP_TEXT = (
    "🛠 <b>Admin Dashboard</b>\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "Available sub-commands:\n\n"
    "• <code>/admin ml_status</code> — ML model registry status\n"
    "• <code>/admin training</code> — Last training run\n"
    "• <code>/admin performance</code> — Grid P&L summary\n"
    "• <code>/admin retrain</code> — Trigger retraining\n"
    "• <code>/admin alerts</code> — Recent alerts\n"
    "• <code>/admin ingestion</code> — Data freshness per market\n\n"
    "🔒 Requires SYSTEM_ADMIN (Level 5) authorization."
)


def _load_pipeline_state() -> dict[str, object] | None:
    """Load pipeline state from disk. Returns None if unavailable."""
    try:
        if _PIPELINE_STATE_PATH.exists():
            with _PIPELINE_STATE_PATH.open(encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
                return None
    except Exception as e:
        logger.warning("pipeline_state_load_failed", error=str(e))
    return None


def _fmt_dt(value: str | None) -> str:
    """Format an ISO datetime string for display."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


async def cmd_admin(message: Message) -> None:
    """
    Handle /admin command with sub-command dispatch.

    Usage: /admin <sub_command>
    """
    if not await check_admin_authorization(message):
        return

    # Parse sub-command from message text
    text = message.text or ""
    parts = text.split(maxsplit=1)
    sub_command = parts[1].strip().lower() if len(parts) > 1 else ""

    if sub_command == "ml_status":
        await _admin_ml_status(message)
    elif sub_command == "training":
        await _admin_training(message)
    elif sub_command == "performance":
        await _admin_performance(message)
    elif sub_command == "retrain":
        await _admin_retrain(message)
    elif sub_command == "alerts":
        await _admin_alerts(message)
    elif sub_command == "ingestion":
        await _admin_ingestion(message)
    else:
        await message.answer(ADMIN_HELP_TEXT, parse_mode="HTML")


async def _admin_ml_status(message: Message) -> None:
    """Display ML model registry status."""
    container = get_service_container()
    if container is None:
        await message.answer("⚠️ Service container not initialized.")
        return

    service = container.research_service
    status = service.get_service_status()

    ml_available = status.get("ml_available", False)
    models_loaded = status.get("ml_models_loaded", 0)
    ranking_mode = status.get("last_ranking_mode") or ("ml" if ml_available else "heuristic")

    lines = [
        "🤖 <b>ML Model Status</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"Mode: <b>{ranking_mode.upper()}</b>",
        f"ML Available: {'✅' if ml_available else '❌'}",
        f"Models Loaded: {models_loaded}",
        f"Blueprints: {status.get('blueprints_generated', 0)}",
        f"Simulations: {status.get('simulations_run', 0)}",
        f"Adapter: {'✅' if status.get('adapter_connected') else '❌'}",
    ]

    # List deployed models from registry
    try:
        from trading_grid.research.models.trainer import ModelStatus

        deployed = service.registry.list_models(status=ModelStatus.DEPLOYED)
        if deployed:
            lines.append("")
            lines.append("<b>Deployed Models:</b>")
            for entry in deployed[:10]:  # Limit to 10
                promoted = entry.promoted_at or entry.registered_at
                date_str = promoted.strftime("%Y-%m-%d") if promoted else "?"
                lines.append(f"• {entry.model_type.value} — {date_str}")
    except Exception as e:
        logger.warning("admin_ml_registry_read_failed", error=str(e))

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _admin_training(message: Message) -> None:
    """Display last training run status."""
    state = await asyncio.to_thread(_load_pipeline_state)

    if state is None:
        await message.answer(
            "📊 <b>Training Pipeline</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ No pipeline state found.\n"
            "Run <code>scripts/run_ml_training.py</code> first.",
            parse_mode="HTML",
        )
        return

    last_training: str | None = state.get("last_training")  # type: ignore[assignment]
    last_ingest_train: str | None = state.get("last_ingest")  # type: ignore[assignment]
    last_promotion: str | None = state.get("last_promotion")  # type: ignore[assignment]
    trained_models: list[object] = state.get("trained_models", [])  # type: ignore[assignment]
    val_auc = state.get("val_roc_auc")
    wf_auc = state.get("walk_forward_mean_roc_auc")

    lines = [
        "📊 <b>Training Pipeline</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"Last Training: {_fmt_dt(last_training)}",
        f"Last Ingest: {_fmt_dt(last_ingest_train)}",
        f"Last Promotion: {_fmt_dt(last_promotion)}",
        "",
        f"Dataset: {state.get('dataset_observations', 0)} observations",
        f"Val ROC-AUC: {val_auc:.4f}" if val_auc else "Val ROC-AUC: —",
        f"Walk-Forward: {wf_auc:.4f}" if wf_auc else "Walk-Forward: —",
        f"Models Trained: {len(trained_models)}",
        f"Promoted: {state.get('promoted_model', '—')}",
    ]

    notes_raw = state.get("notes")
    if notes_raw:
        notes: str = str(notes_raw)
        # Truncate long notes
        notes_short = notes[:200] + "..." if len(notes) > 200 else notes
        lines.append("")
        lines.append(f"📝 {notes_short}")

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _admin_performance(message: Message) -> None:
    """Display grid performance summary."""
    container = get_service_container()
    if container is None:
        await message.answer("⚠️ Service container not initialized.")
        return

    demo_service = container.demo_service
    sessions = demo_service.get_all_sessions()
    total_metrics = demo_service.get_all_metrics()

    # Aggregate P&L from grid runtimes
    total_realized = Decimal("0")
    total_unrealized = Decimal("0")
    total_deployed = Decimal("0")
    active_count = 0

    for session in sessions:
        grid = session.grid_runtime
        total_realized += grid.realized_pnl
        total_unrealized += grid.unrealized_pnl
        total_deployed += grid.deployed_capital
        if session.status in ("CREATED", "RUNNING", "PAUSED"):
            active_count += 1

    lines = [
        "📈 <b>Grid Performance</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"Total Sessions: {len(sessions)}",
        f"Active: {active_count}",
        "",
        f"Orders: {total_metrics.orders_filled}/{total_metrics.orders_submitted} filled",
        f"Fill Rate: {total_metrics.fill_rate:.1f}%",
        f"Avg Latency: {total_metrics.avg_order_latency_ms:.0f}ms",
        "",
        f"Realized P&L: {total_realized:+.2f} USDT",
        f"Unrealized P&L: {total_unrealized:+.2f} USDT",
        f"Deployed: {total_deployed:.2f} USDT",
        "",
        f"Errors: {total_metrics.error_count}",
        f"Emergency Stops: {total_metrics.emergency_stops}",
    ]

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _admin_retrain(message: Message) -> None:
    """Trigger a background ML training run."""
    # Prevent concurrent training runs
    running = [t for t in _training_tasks.values() if not t.done()]
    if running:
        await message.answer(
            "⚠️ A training run is already in progress.\nPlease wait for it to complete.",
        )
        return

    task_id = f"TRAIN-{datetime.now(UTC).strftime('%H%M%S')}"
    cmd = [sys.executable, "scripts/run_ml_training.py"]

    async def _run_training() -> None:
        """Run training as a subprocess."""
        logger.info("admin_training_started", task_id=task_id, cmd=cmd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await proc.wait()
            if proc.returncode == 0:
                logger.info("admin_training_completed", task_id=task_id)
            else:
                logger.error(
                    "admin_training_failed",
                    task_id=task_id,
                    returncode=proc.returncode,
                )
        except Exception as e:
            logger.error("admin_training_error", task_id=task_id, error=str(e))

    task = asyncio.create_task(_run_training())
    _training_tasks[task_id] = task
    task.add_done_callback(lambda _t: _training_tasks.pop(task_id, None))

    # Audit log for sensitive operation
    user_id = message.from_user.id if message.from_user else None
    logger.info(
        "admin_training_triggered",
        task_id=task_id,
        triggered_by=user_id,
    )

    await message.answer(
        f"🔄 <b>Training Started</b>\n\n"
        f"Task: <code>{task_id}</code>\n"
        f"Running: <code>scripts/run_ml_training.py</code>\n\n"
        f"Check status with <code>/admin training</code> after completion.",
        parse_mode="HTML",
    )


async def _admin_alerts(message: Message) -> None:
    """Display recent monitoring alerts."""
    container = get_service_container()
    if container is None:
        await message.answer("⚠️ Service container not initialized.")
        return

    monitoring = container.monitoring_service
    dashboard = monitoring.get_dashboard_data()

    system_healthy = dashboard.get("system_healthy", True)
    active_alerts = dashboard.get("active_alerts", [])
    critical_count = dashboard.get("critical_alerts", 0)

    lines = [
        "🔔 <b>Monitoring Alerts</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"System: {'✅ Healthy' if system_healthy else '🔴 UNHEALTHY'}",
        f"Active Alerts: {len(active_alerts)}",
        f"Critical: {critical_count}",
    ]

    if active_alerts:
        lines.append("")
        lines.append("<b>Recent Alerts:</b>")
        for alert in active_alerts[:5]:  # Show last 5
            severity = alert.get("severity", "INFO")
            msg = alert.get("message", "Unknown")[:80]
            lines.append(f"• [{severity}] {msg}")
    else:
        lines.append("")
        lines.append("✅ No active alerts.")

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _admin_ingestion(message: Message) -> None:
    """Display data ingestion status and freshness."""
    state = await asyncio.to_thread(_load_pipeline_state)

    if state is None:
        await message.answer(
            "📥 <b>Data Ingestion</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ No pipeline state found.\n"
            "Run <code>scripts/run_ml_training.py</code> first.",
            parse_mode="HTML",
        )
        return

    last_ingest: str | None = state.get("last_ingest")  # type: ignore[assignment]
    markets: list[str] = state.get("ingested_markets", [])  # type: ignore[assignment]
    total_candles = state.get("total_candles", 0)
    candles_per_market = state.get("candles_per_market", 0)
    exchange = state.get("exchange", "—")
    interval = state.get("interval", "—")

    # Calculate freshness
    freshness_str = "—"
    if last_ingest:
        try:
            ingest_dt = datetime.fromisoformat(last_ingest)
            delta = datetime.now(UTC) - ingest_dt
            hours = delta.total_seconds() / 3600
            if hours < 1:
                freshness_str = f"{hours * 60:.0f} minutes ago"
            elif hours < 24:
                freshness_str = f"{hours:.1f} hours ago"
            else:
                freshness_str = f"{hours / 24:.1f} days ago"
        except ValueError:
            freshness_str = last_ingest

    lines = [
        "📥 <b>Data Ingestion</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"Last Ingest: {_fmt_dt(last_ingest)}",
        f"Freshness: {freshness_str}",
        f"Exchange: {exchange}",
        f"Interval: {interval}",
        "",
        f"Markets: {len(markets)}",
        f"Total Candles: {total_candles:,}",
        f"Candles/Market: {candles_per_market:,}",
    ]

    if markets:
        lines.append("")
        lines.append("<b>Markets:</b>")
        for m in markets[:10]:  # Limit to 10
            lines.append(f"• {m}")
        if len(markets) > 10:
            lines.append(f"… and {len(markets) - 10} more")

    await message.answer("\n".join(lines), parse_mode="HTML")
