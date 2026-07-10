from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .models import Provider, sanitize_for_live, unique_id
from .paths import backup_file, claude_settings_path, read_json, write_json
from .presets import load_presets, preset_to_provider
from .store import ProviderStore


class ProviderManager:
    def __init__(self, store: ProviderStore | None = None) -> None:
        self.store = store or ProviderStore.load()

    def list_providers(self) -> list[Provider]:
        return self.store.sorted_providers()

    def current_provider(self) -> Provider | None:
        return self.store.current_provider()

    def add_provider(self, provider: Provider, switch: bool = False) -> Provider:
        provider.validate_for_claude()
        self.store.add(provider)
        if switch or self.store.current == provider.id:
            self.switch(provider.id, save_store=False)
        self.store.save()
        return provider

    def add_from_preset(
        self,
        preset: dict[str, Any],
        api_key: str = "",
        template_values: dict[str, str] | None = None,
        name: str | None = None,
        switch: bool = False,
    ) -> Provider:
        provider = preset_to_provider(
            preset,
            self.store.ids(),
            api_key=api_key,
            template_values=template_values,
            name=name,
        )
        return self.add_provider(provider, switch=switch)

    def update_provider(self, provider_id: str, provider: Provider) -> Provider:
        provider.validate_for_claude()
        self.store.update(provider_id, provider)
        if self.store.current == provider.id:
            self.write_live(provider)
        self.store.save()
        return provider

    def delete_provider(self, provider_id: str) -> Provider:
        provider = self.store.delete(provider_id)
        self.store.save()
        return provider

    def switch(self, provider_id: str, save_store: bool = True) -> Provider:
        outgoing = self.store.current_provider()
        incoming = self.store.set_current(provider_id)
        if outgoing and outgoing.id != incoming.id:
            self.backfill_current_from_live(outgoing)
        self.write_live(incoming)
        if save_store:
            self.store.save()
        return incoming

    def write_live(self, provider: Provider) -> Path | None:
        settings_path = claude_settings_path()
        backup = backup_file(settings_path, "claude-settings")
        write_json(settings_path, provider.live_settings())
        return backup

    def backfill_current_from_live(self, provider: Provider) -> bool:
        settings_path = claude_settings_path()
        if not settings_path.exists():
            return False
        live = read_json(settings_path, None)
        if not isinstance(live, dict):
            return False
        provider.settings_config = sanitize_for_live(live)
        return True

    def import_live(self, name: str = "default", make_current: bool = True) -> Provider:
        settings_path = claude_settings_path()
        if not settings_path.exists():
            raise ValueError(f"Claude Code 配置文件不存在: {settings_path}")
        live = read_json(settings_path, None)
        if not isinstance(live, dict):
            raise ValueError(f"Claude Code 配置必须是 JSON 对象: {settings_path}")
        provider = Provider(
            id=unique_id(name, self.store.ids()),
            name=name,
            settings_config=sanitize_for_live(live),
            category="custom",
        )
        provider.validate_for_claude()
        return self.add_provider(provider, switch=make_current)

    def export_config(self, path: Path) -> None:
        export = copy.deepcopy(self.store.to_dict())
        for provider in export.get("providers", []):
            if isinstance(provider, dict):
                provider["settingsConfig"] = self._redact_settings(provider.get("settingsConfig"))
        write_json(path, export, mode=0o600)

    def import_config(self, path: Path, merge: bool = True) -> int:
        data = read_json(path, None)
        if not isinstance(data, dict) or not isinstance(data.get("providers"), list):
            raise ValueError("导入文件格式错误：缺少 providers 数组")
        imported = 0
        existing = self.store.ids()
        if not merge:
            self.store.providers = []
            self.store.current = None
            existing = set()
        for item in data["providers"]:
            if not isinstance(item, dict):
                continue
            provider = Provider.from_dict(item)
            if provider.id in existing:
                provider.id = unique_id(provider.id, existing)
            provider.validate_for_claude()
            existing.add(provider.id)
            self.store.add(provider)
            imported += 1
        if isinstance(data.get("commonConfig"), dict):
            self.store.common_config.update(data["commonConfig"])
        self.store.ensure_current_valid()
        self.store.save()
        return imported

    def extract_common_config(self, provider_id: str | None = None) -> dict[str, Any]:
        provider = self.store.get(provider_id) if provider_id else self.store.current_provider()
        if provider is None:
            raise ValueError("没有可提取的供应商")
        common = provider.common_config()
        self.store.common_config = common
        self.store.save()
        return common

    def apply_common_config(self, provider_id: str) -> Provider:
        provider = self.store.get(provider_id)
        if provider is None:
            raise ValueError(f"供应商不存在: {provider_id}")
        provider.settings_config = self._deep_merge(copy.deepcopy(provider.settings_config), self.store.common_config)
        provider.validate_for_claude()
        if self.store.current == provider.id:
            self.write_live(provider)
        self.store.save()
        return provider

    def seed_official(self) -> Provider:
        for provider in self.store.providers:
            if provider.is_official():
                return provider
        presets = load_presets()
        for preset in presets:
            if preset.get("isOfficial") or preset.get("category") == "official":
                return self.add_from_preset(preset, switch=not bool(self.store.current))
        provider = Provider(
            id=unique_id("claude-official", self.store.ids()),
            name="Claude Official",
            settings_config={"env": {}},
            website_url="https://www.anthropic.com/claude-code",
            category="official",
            meta={"isOfficial": True},
        )
        return self.add_provider(provider, switch=not bool(self.store.current))

    @staticmethod
    def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                ProviderManager._deep_merge(target[key], value)
            else:
                target[key] = copy.deepcopy(value)
        return target

    @staticmethod
    def _redact_settings(value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                upper = key.upper()
                if any(token in upper for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                    result[key] = ""
                else:
                    result[key] = ProviderManager._redact_settings(child)
            return result
        if isinstance(value, list):
            return [ProviderManager._redact_settings(child) for child in value]
        return value


def format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
