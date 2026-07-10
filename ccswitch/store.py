from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Provider, now_ms
from .paths import legacy_profiles_path, read_json, store_path, write_json


STORE_VERSION = 2


@dataclass
class ProviderStore:
    providers: list[Provider] = field(default_factory=list)
    current: str | None = None
    common_config: dict[str, Any] = field(default_factory=dict)
    migrated_from_legacy: bool = False

    @classmethod
    def load(cls) -> "ProviderStore":
        path = store_path()
        data = read_json(path, None)
        if isinstance(data, dict) and data.get("version") == STORE_VERSION:
            providers = [Provider.from_dict(item) for item in data.get("providers", []) if isinstance(item, dict)]
            current = data.get("current") if isinstance(data.get("current"), str) else None
            common = data.get("commonConfig") if isinstance(data.get("commonConfig"), dict) else {}
            store = cls(providers=providers, current=current, common_config=common)
            store.ensure_current_valid()
            return store

        if isinstance(data, dict) and isinstance(data.get("providers"), list):
            providers = [Provider.from_dict(item) for item in data.get("providers", []) if isinstance(item, dict)]
            store = cls(providers=providers, current=data.get("current"), migrated_from_legacy=True)
            store.ensure_current_valid()
            store.save()
            return store

        store = cls()
        store.import_legacy_profiles()
        store.ensure_current_valid()
        if store.providers:
            store.save()
        return store

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STORE_VERSION,
            "app": "claude",
            "current": self.current,
            "commonConfig": self.common_config,
            "providers": [provider.to_dict() for provider in self.sorted_providers()],
            "updatedAt": now_ms(),
        }

    def save(self) -> None:
        write_json(store_path(), self.to_dict(), mode=0o600)

    def import_legacy_profiles(self) -> int:
        legacy = read_json(legacy_profiles_path(), {})
        raw_profiles = legacy.get("profiles", []) if isinstance(legacy, dict) else []
        if not isinstance(raw_profiles, list):
            return 0
        existing = {provider.id for provider in self.providers}
        count = 0
        for raw in raw_profiles:
            if not isinstance(raw, dict):
                continue
            provider = Provider.from_legacy_profile(raw, existing)
            existing.add(provider.id)
            self.providers.append(provider)
            count += 1
        if count:
            self.migrated_from_legacy = True
        return count

    def sorted_providers(self) -> list[Provider]:
        return sorted(
            self.providers,
            key=lambda provider: (
                provider.sort_index if provider.sort_index is not None else 10_000,
                provider.created_at or 0,
                provider.name.lower(),
            ),
        )

    def ids(self) -> set[str]:
        return {provider.id for provider in self.providers}

    def get(self, provider_id: str) -> Provider | None:
        for provider in self.providers:
            if provider.id == provider_id:
                return provider
        return None

    def index_of(self, provider_id: str) -> int | None:
        for index, provider in enumerate(self.providers):
            if provider.id == provider_id:
                return index
        return None

    def add(self, provider: Provider) -> None:
        if provider.id in self.ids():
            raise ValueError(f"供应商 ID 已存在: {provider.id}")
        provider.sort_index = len(self.providers)
        self.providers.append(provider)
        if not self.current:
            self.current = provider.id

    def update(self, provider_id: str, provider: Provider) -> None:
        index = self.index_of(provider_id)
        if index is None:
            raise ValueError(f"供应商不存在: {provider_id}")
        if provider.id != provider_id and provider.id in self.ids():
            raise ValueError(f"供应商 ID 已存在: {provider.id}")
        provider.sort_index = self.providers[index].sort_index
        provider.created_at = provider.created_at or self.providers[index].created_at
        self.providers[index] = provider
        if self.current == provider_id:
            self.current = provider.id

    def delete(self, provider_id: str) -> Provider:
        if self.current == provider_id:
            raise ValueError("不能删除当前正在使用的供应商，请先切换到其它供应商")
        index = self.index_of(provider_id)
        if index is None:
            raise ValueError(f"供应商不存在: {provider_id}")
        return self.providers.pop(index)

    def set_current(self, provider_id: str) -> Provider:
        provider = self.get(provider_id)
        if provider is None:
            raise ValueError(f"供应商不存在: {provider_id}")
        self.current = provider.id
        return provider

    def current_provider(self) -> Provider | None:
        if not self.current:
            return None
        return self.get(self.current)

    def ensure_current_valid(self) -> None:
        if self.current and self.get(self.current):
            return
        self.current = self.providers[0].id if self.providers else None
