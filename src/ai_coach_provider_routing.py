"""Explicit jurisdiction-to-provider routing for future deployments.

Routing is configuration-driven and opt-in.  It never infers a user's country
from IP, locale, or billing data, and it never falls back to another route.
Each route must point at its own approval record so policy evidence remains
scoped to the exact provider, model, endpoint, and processing region.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class ProviderRoutingError(ValueError):
    """Raised when an explicit jurisdiction route is missing or invalid."""


@dataclass(frozen=True)
class ProviderRoute:
    jurisdiction: str
    provider_id: str
    processing_region: str
    approval_path: Path
    credential_env: str


class ProviderRouteTable:
    """Strict exact-match route table; wildcard and implicit fallbacks are banned."""

    def __init__(self, routes: tuple[ProviderRoute, ...] | list[ProviderRoute]):
        normalized: dict[str, ProviderRoute] = {}
        for route in routes:
            if not isinstance(route, ProviderRoute):
                raise ProviderRoutingError("AI provider route is invalid")
            key = self._normalize(route.jurisdiction)
            if key in normalized or key in {"*", "default", "auto"}:
                raise ProviderRoutingError("AI provider jurisdiction route is ambiguous")
            if not route.provider_id or not route.processing_region:
                raise ProviderRoutingError("AI provider route identity is incomplete")
            if not isinstance(route.approval_path, Path) or not route.approval_path.is_absolute():
                raise ProviderRoutingError("AI provider approval path must be absolute")
            if (
                not isinstance(route.credential_env, str)
                or not route.credential_env
                or not route.credential_env.isidentifier()
            ):
                raise ProviderRoutingError("AI provider credential mapping is invalid")
            normalized[key] = route
        self._routes = normalized

    @staticmethod
    def _normalize(jurisdiction: str) -> str:
        if not isinstance(jurisdiction, str) or not jurisdiction.strip():
            raise ProviderRoutingError("AI provider jurisdiction is required")
        return jurisdiction.strip().casefold()

    def resolve(self, jurisdiction: str) -> ProviderRoute:
        """Resolve only an explicitly supplied jurisdiction."""

        key = self._normalize(jurisdiction)
        try:
            return self._routes[key]
        except KeyError as exc:
            raise ProviderRoutingError("AI provider route is not approved for jurisdiction") from exc

    @property
    def jurisdictions(self) -> tuple[str, ...]:
        return tuple(sorted(self._routes))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Mapping[str, Any]]) -> "ProviderRouteTable":
        """Build a route table from trusted configuration without accepting wildcards."""

        if not isinstance(mapping, Mapping):
            raise ProviderRoutingError("AI provider route configuration is invalid")
        routes: list[ProviderRoute] = []
        for jurisdiction, value in mapping.items():
            if not isinstance(value, Mapping):
                raise ProviderRoutingError("AI provider route configuration is invalid")
            required = {"provider_id", "processing_region", "approval_path", "credential_env"}
            if set(value) != required:
                raise ProviderRoutingError("AI provider route fields are invalid")
            routes.append(
                ProviderRoute(
                    jurisdiction=jurisdiction,
                    provider_id=value["provider_id"],
                    processing_region=value["processing_region"],
                    approval_path=Path(value["approval_path"]),
                    credential_env=value["credential_env"],
                )
            )
        return cls(routes)
