from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from app.core.models import LagResult, PriceLeadLagDetail


@dataclass(slots=True)
class LagModuleConfig:
    module_id: str
    display_name: str
    description: str
    enabled: bool = True
    default_sort_score: str = "stability_pct"


@dataclass(slots=True)
class LagModuleResult:
    module_id: str
    rows: list[LagResult] = field(default_factory=list)
    enabled: bool = True


DetailT = TypeVar("DetailT", bound=PriceLeadLagDetail)


class LagModuleBase(Generic[DetailT]):
    config: LagModuleConfig

    @property
    def module_id(self) -> str:
        return self.config.module_id

    @property
    def display_name(self) -> str:
        return self.config.display_name

    @property
    def description(self) -> str:
        return self.config.description

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.config.enabled = value

    @property
    def default_sort_score(self) -> str:
        return self.config.default_sort_score

    def analyze(self, history_snapshot, latest_quotes, data_metrics) -> list[LagResult]:
        raise NotImplementedError

    def get_details(self, lag_ms: int) -> list[DetailT]:
        raise NotImplementedError
