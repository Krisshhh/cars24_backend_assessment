from __future__ import annotations

from collections.abc import Iterable

from app.rules.definitions import REGISTRY
from app.rules.types import SEVERITY_ORDER, Discrepancy, OrderSnapshot, Rule


def run_rules(
    snapshot: OrderSnapshot, registry: Iterable[Rule] = REGISTRY
) -> list[Discrepancy]:
    registry_list = list(registry)
    found: list[tuple[int, int, Discrepancy]] = []

    for position, rule in enumerate(registry_list):
        result = rule(snapshot)
        if result is not None:
            found.append((SEVERITY_ORDER[result.severity], position, result))

    found.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in found]
