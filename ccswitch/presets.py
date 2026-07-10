from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .models import Provider, apply_template_values, now_ms, set_api_key, unique_id
from .paths import read_json


DEFAULT_PRESETS_FILE = Path(__file__).resolve().parent.parent / "presets.json"


class PresetError(ValueError):
    pass


def load_presets(path: Path = DEFAULT_PRESETS_FILE) -> list[dict[str, Any]]:
    data = read_json(path, {"presets": []})
    presets = data.get("presets", []) if isinstance(data, dict) else []
    if not isinstance(presets, list):
        raise PresetError("presets.json 中 presets 必须是数组")
    return [preset for preset in presets if isinstance(preset, dict)]


def preset_to_provider(
    preset: dict[str, Any],
    existing_ids: set[str],
    api_key: str = "",
    template_values: dict[str, str] | None = None,
    name: str | None = None,
) -> Provider:
    display_name = name or str(preset.get("name") or "Custom")
    raw_settings = preset.get("settingsConfig")
    if isinstance(raw_settings, dict):
        settings = copy.deepcopy(raw_settings)
    else:
        env: dict[str, Any] = {}
        base_url = preset.get("base_url") or preset.get("baseUrl") or ""
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
        api_field = preset.get("apiKeyField") or "ANTHROPIC_AUTH_TOKEN"
        if api_field and not preset.get("isOfficial"):
            env[str(api_field)] = ""
        big = preset.get("big") or preset.get("model") or ""
        small = preset.get("small") or preset.get("haiku") or big
        if big:
            env["ANTHROPIC_MODEL"] = big
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = big
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = preset.get("opus") or big
        if small:
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = small
        settings = {"env": env}

    merged_templates = copy.deepcopy(preset.get("templateValues") or {})
    for key, value in (template_values or {}).items():
        existing = merged_templates.get(key)
        if isinstance(existing, dict):
            existing["editorValue"] = value
        else:
            merged_templates[key] = {"editorValue": value}
    settings = apply_template_values(settings, merged_templates)

    if api_key:
        set_api_key(settings, api_key, preset.get("apiKeyField"))

    meta: dict[str, Any] = {}
    for src, dst in (
        ("apiFormat", "apiFormat"),
        ("providerType", "providerType"),
        ("requiresOAuth", "requiresOAuth"),
        ("apiKeyField", "apiKeyField"),
        ("isPartner", "isPartner"),
        ("partnerPromotionKey", "partnerPromotionKey"),
        ("endpointCandidates", "endpointCandidates"),
        ("modelsUrl", "modelsUrl"),
    ):
        if src in preset:
            meta[dst] = copy.deepcopy(preset[src])
    if preset.get("isOfficial"):
        meta["isOfficial"] = True

    provider = Provider(
        id=unique_id(display_name, existing_ids),
        name=display_name,
        settings_config=settings,
        website_url=preset.get("websiteUrl") or preset.get("website") or preset.get("website_url"),
        category=preset.get("category") or ("official" if preset.get("isOfficial") else "custom"),
        created_at=now_ms(),
        meta=meta,
        icon=preset.get("icon"),
        icon_color=preset.get("iconColor"),
    )
    provider.validate_for_claude()
    return provider


def template_prompts(preset: dict[str, Any]) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    values = preset.get("templateValues")
    if not isinstance(values, dict):
        return result
    for key, config in values.items():
        if not isinstance(config, dict):
            continue
        label = str(config.get("label") or key)
        default = str(config.get("editorValue", config.get("defaultValue", "")) or "")
        result.append((key, label, default))
    return result
