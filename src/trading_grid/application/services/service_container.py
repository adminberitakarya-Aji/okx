"""
Service Container — Central wiring point for application services.

This module instantiates and wires all application services together:
- ExchangeAdapter (from settings)
- RiskValidationService
- TenantLimitsService
- ExecutionEngine
- GridEngine
- DemoTradingService
- PriceMonitorService

This is the single place where services are created and connected,
resolving the "orphan service" problem identified in the audit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import structlog

from trading_grid.application.services.approval import ApprovalService
from trading_grid.application.services.demo_trading import DemoTradingService
from trading_grid.application.services.exchange_factory import ExchangeAdapterFactory
from trading_grid.application.services.execution_engine import ExecutionEngine
from trading_grid.application.services.grid_engine import GridEngine
from trading_grid.application.services.price_monitor import PriceMonitorService
from trading_grid.application.services.research_service import ResearchService
from trading_grid.application.services.risk_validation import RiskValidationService
from trading_grid.application.services.tenant_limits import TenantLimitsService

if TYPE_CHECKING:
    from trading_grid.config.settings import Settings
    from trading_grid.domain.exchange.interface import ExchangeAdapter
    from trading_grid.domain.shared.types import ExchangeId

logger = structlog.get_logger()


class ServiceContainer:
    """Composition root for application services."""

    def __init__(self, settings: Settings, exchange_id: ExchangeId | str = "OKX") -> None:
        """
        Initialize the service container.

        Args:
            settings: Application settings
            exchange_id: Default exchange for this container ("OKX", "BINANCE", "BYBIT")
        """
        self._settings = settings
        self._exchange_id: ExchangeId = cast("ExchangeId", exchange_id.upper())
        self._adapter: ExchangeAdapter | None = None
        self._grid_engine: GridEngine | None = None
        self._execution_engine: ExecutionEngine | None = None
        self._demo_service: DemoTradingService | None = None
        self._price_monitor: PriceMonitorService | None = None
        self._research_service: ResearchService | None = None
        self._approval_service: ApprovalService | None = None

    @property
    def exchange_id(self) -> str:
        """Get the exchange ID for this container."""
        return self._exchange_id

    @property
    def adapter(self) -> ExchangeAdapter:
        """Get the exchange adapter (lazy init)."""
        if self._adapter is None:
            self._adapter = ExchangeAdapterFactory.create(self._exchange_id, self._settings)
        return self._adapter

    @property
    def grid_engine(self) -> GridEngine:
        """Get the grid engine (lazy init)."""
        if self._grid_engine is None:
            self._grid_engine = GridEngine()
        return self._grid_engine

    @property
    def execution_engine(self) -> ExecutionEngine:
        """Get the execution engine (lazy init)."""
        if self._execution_engine is None:
            risk_validator = RiskValidationService.from_risk_settings(self._settings.risk)
            tenant_limits = TenantLimitsService(self._settings)
            self._execution_engine = ExecutionEngine(
                adapter=self.adapter,
                risk_validator=risk_validator,
                tenant_limits=tenant_limits,
            )
        return self._execution_engine

    @property
    def demo_service(self) -> DemoTradingService:
        """Get the demo trading service (lazy init)."""
        if self._demo_service is None:
            self._demo_service = DemoTradingService(
                grid_engine=self.grid_engine,
                execution_engine=self.execution_engine,
                price_monitor=self.price_monitor,
            )
        return self._demo_service

    @property
    def price_monitor(self) -> PriceMonitorService:
        """Get the price monitor service (lazy init)."""
        if self._price_monitor is None:
            self._price_monitor = PriceMonitorService(
                adapter=self.adapter,
                grid_engine=self.grid_engine,
                execution_engine=self.execution_engine,
            )
        return self._price_monitor

    @property
    def research_service(self) -> ResearchService:
        """Get the research service (lazy init)."""
        if self._research_service is None:
            self._research_service = ResearchService(
                adapter=self.adapter,
            )
        return self._research_service

    @property
    def approval_service(self) -> ApprovalService:
        """Get the approval service (lazy init)."""
        if self._approval_service is None:
            self._approval_service = ApprovalService()
        return self._approval_service

    async def start(self) -> None:
        """Start all background services."""
        try:
            await self.price_monitor.start()
            logger.info("service_container_started")
        except Exception as e:
            logger.warning(
                "service_container_start_failed",
                error=str(e),
                message="Price monitor could not start (exchange may not be configured)",
            )

    async def stop(self) -> None:
        """Stop all background services."""
        if self._price_monitor is not None:
            await self._price_monitor.stop()
        logger.info("service_container_stopped")


class MultiExchangeContainer:
    """
    Registry of ServiceContainers for multiple exchanges.

    This enables the Telegram bot to trade on OKX, Binance, and Bybit
    simultaneously. Each exchange gets its own isolated ServiceContainer
    with its own adapter, execution engine, and demo service.

    Usage:
        multi = MultiExchangeContainer(settings)
        okx_container = multi.get_container("OKX")
        binance_container = multi.get_container("BINANCE")
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the multi-exchange registry."""
        self._settings = settings
        self._containers: dict[str, ServiceContainer] = {}

    def get_container(self, exchange_id: str) -> ServiceContainer:
        """
        Get or create a ServiceContainer for the given exchange.

        Args:
            exchange_id: Exchange ID ("OKX", "BINANCE", "BYBIT")

        Returns:
            ServiceContainer for the exchange

        Raises:
            ValueError: If exchange_id is not supported
        """
        exchange_id_upper = exchange_id.upper()
        if exchange_id_upper not in ("OKX", "BINANCE", "BYBIT"):
            raise ValueError(
                f"Unsupported exchange: {exchange_id!r}. Supported: OKX, BINANCE, BYBIT"
            )

        if exchange_id_upper not in self._containers:
            self._containers[exchange_id_upper] = ServiceContainer(
                self._settings, exchange_id=cast("ExchangeId", exchange_id_upper)
            )
            logger.info("exchange_container_created", exchange=exchange_id_upper)

        return self._containers[exchange_id_upper]

    def get_configured_exchanges(self) -> list[ExchangeId]:
        """Get list of exchanges that have credentials configured."""
        return ExchangeAdapterFactory.get_configured_exchanges(self._settings)

    @property
    def default_container(self) -> ServiceContainer:
        """Get the default (OKX) container for backward compatibility."""
        return self.get_container("OKX")

    async def start_all(self) -> None:
        """Start all created containers."""
        for exchange_id, container in self._containers.items():
            try:
                await container.start()
            except Exception as e:
                logger.warning(
                    "container_start_failed",
                    exchange=exchange_id,
                    error=str(e),
                )

    async def stop_all(self) -> None:
        """Stop all created containers."""
        for _exchange_id, container in self._containers.items():
            await container.stop()
        logger.info("multi_exchange_container_stopped")
