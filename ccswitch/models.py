from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any


API_KEY_FIELDS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")
MODEL_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
)
LEGACY_SMALL_MODEL_KEY = "ANTHROPIC_SMALL_FAST_MODEL"
PROVIDER_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_REASONING_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_USE_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
)
INTERNAL_TOP_LEVEL_KEYS = (
    "api_format",
    "apiFormat",
    "openrouter_compat_mode",
    "openrouterCompatMode",
)
SENSITIVE_SUFFIXES = (
    "_API_KEY",
    "_APIKEY",
    "_AUTH_TOKEN",
    "_TOKEN",
    "_ACCESS_KEY",
    "_ACCESS_KEY_ID",
    "_KEY_ID",
    "_PRIVATE_KEY",
)
SENSITIVE_EXACT = {"APIKEY", "API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIALS"}
SENSITIVE_CONTAINS = ("SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "PRIVATE_KEY", "BEARER_TOKEN")
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def now_ms() -> int:
    return int(time.time() * 1000)


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return slug or "provider"


def unique_id(base: str, existing: set[str]) -> str:
    candidate = slugify(base)
    if candidate not in existing:
        return candidate
    index = 2
    while f"{candidate}-{index}" in existing:
        index += 1
    return f"{candidate}-{index}"


def mask_secret(value: str | None) -> str:
    if not value:
        return "(空)"
    if len(value) <= 14:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"


def is_sensitive_key(name: str) -> bool:
    upper = name.upper()
    if upper in SENSITIVE_EXACT:
        return True
    if any(upper.endswith(suffix) for suffix in SENSITIVE_SUFFIXES):
        return True
    return any(token in upper for token in SENSITIVE_CONTAINS)


def apply_template_values(value: Any, template_values: dict[str, Any] | None) -> Any:
    if not template_values:
        return copy.deepcopy(value)

    resolved: dict[str, str] = {}
    for key, config in template_values.items():
        if isinstance(config, dict):
            raw = config.get("editorValue", config.get("defaultValue", ""))
        else:
            raw = config
        resolved[key] = "" if raw is None else str(raw)

    def replace_string(text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            return resolved.get(match.group(1), match.group(0))
        return PLACEHOLDER_RE.sub(repl, text)

    def walk(item: Any) -> Any:
        if isinstance(item, str):
            return replace_string(item)
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, dict):
            return {key: walk(child) for key, child in item.items()}
        return copy.deepcopy(item)

    return walk(value)


def normalize_claude_models(settings: dict[str, Any]) -> None:
    env = settings.get("env")
    if not isinstance(env, dict):
        return
    model = env.get("ANTHROPIC_MODEL")
    small = env.get(LEGACY_SMALL_MODEL_KEY)
    if "ANTHROPIC_DEFAULT_HAIKU_MODEL" not in env and isinstance(small or model, str):
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = small or model
    if "ANTHROPIC_DEFAULT_SONNET_MODEL" not in env and isinstance(model or small, str):
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model or small
    if "ANTHROPIC_DEFAULT_OPUS_MODEL" not in env and isinstance(model or small, str):
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model or small
    env.pop(LEGACY_SMALL_MODEL_KEY, None)


def sanitize_for_live(settings: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(settings)
    for key in INTERNAL_TOP_LEVEL_KEYS:
        result.pop(key, None)
    normalize_claude_models(result)
    return result


def provider_key_field(settings: dict[str, Any], preferred: str | None = None) -> str:
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    if preferred in API_KEY_FIELDS:
        return preferred
    for field_name in API_KEY_FIELDS:
        if field_name in env:
            return field_name
    return "ANTHROPIC_AUTH_TOKEN"


def get_api_key(settings: dict[str, Any]) -> str:
    if isinstance(settings.get("apiKey"), str):
        return settings["apiKey"]
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    for key in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY"):
        value = env.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def set_api_key(settings: dict[str, Any], api_key: str, preferred_field: str | None = None) -> None:
    if "apiKey" in settings:
        settings["apiKey"] = api_key
        return
    env = settings.setdefault("env", {})
    if not isinstance(env, dict):
        raise ValueError("settingsConfig.env 必须是 JSON 对象")
    env[provider_key_field(settings, preferred_field)] = api_key


def extract_common_config(settings: dict[str, Any]) -> dict[str, Any]:
    config = copy.deepcopy(settings)
    env = config.get("env")
    if isinstance(env, dict):
        for key in list(env):
            if key in PROVIDER_ENV_KEYS or is_sensitive_key(key):
                env.pop(key, None)
        if not env:
            config.pop("env", None)
    for key in list(config):
        if key in ("apiBaseUrl", "primaryModel", "smallFastModel") or is_sensitive_key(key):
            config.pop(key, None)
    return config


@dataclass
class Provider:
    id: str
    name: str
    settings_config: dict[str, Any]
    website_url: str | None = None
    category: str | None = None
    created_at: int | None = None
    sort_index: int | None = None
    notes: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    icon: str | None = None
    icon_color: str | None = None
    in_failover_queue: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Provider":
        settings = raw.get("settingsConfig", raw.get("settings_config", raw.get("settings", {})))
        if not isinstance(settings, dict):
            settings = {}
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        provider = cls(
            id=str(raw.get("id") or slugify(str(raw.get("name") or "provider"))),
            name=str(raw.get("name") or raw.get("id") or "provider"),
            settings_config=copy.deepcopy(settings),
            website_url=raw.get("websiteUrl") or raw.get("website_url"),
            category=raw.get("category"),
            created_at=raw.get("createdAt") or raw.get("created_at"),
            sort_index=raw.get("sortIndex") if raw.get("sortIndex") is not None else raw.get("sort_index"),
            notes=raw.get("notes"),
            meta=copy.deepcopy(meta),
            icon=raw.get("icon"),
            icon_color=raw.get("iconColor") or raw.get("icon_color"),
            in_failover_queue=bool(raw.get("inFailoverQueue", raw.get("in_failover_queue", False))),
        )
        normalize_claude_models(provider.settings_config)
        return provider

    @classmethod
    def from_legacy_profile(cls, raw: dict[str, Any], existing: set[str]) -> "Provider":
        name = str(raw.get("name") or "provider")
        big = str(raw.get("big") or "")
        small = str(raw.get("small") or big)
        settings = {
            "env": {
                "ANTHROPIC_BASE_URL": str(raw.get("base_url") or ""),
                "ANTHROPIC_AUTH_TOKEN": str(raw.get("auth_token") or ""),
                "ANTHROPIC_MODEL": big,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": small,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": big,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": big,
            }
        }
        effort = raw.get("effort")
        if effort:
            settings["env"]["CLAUDE_CODE_EFFORT_LEVEL"] = str(effort)
        return cls(
            id=unique_id(name, existing),
            name=name,
            settings_config=settings,
            category="custom",
            created_at=now_ms(),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "settingsConfig": self.settings_config,
        }
        optional = {
            "websiteUrl": self.website_url,
            "category": self.category,
            "createdAt": self.created_at,
            "sortIndex": self.sort_index,
            "notes": self.notes,
            "meta": self.meta or None,
            "icon": self.icon,
            "iconColor": self.icon_color,
        }
        for key, value in optional.items():
            if value is not None:
                result[key] = value
        if self.in_failover_queue:
            result["inFailoverQueue"] = True
        return result

    def copy(self) -> "Provider":
        return Provider.from_dict(self.to_dict())

    def api_key(self) -> str:
        return get_api_key(self.settings_config)

    def base_url(self) -> str:
        env = self.settings_config.get("env") if isinstance(self.settings_config.get("env"), dict) else {}
        value = env.get("ANTHROPIC_BASE_URL")
        return value if isinstance(value, str) else ""

    def model(self) -> str:
        env = self.settings_config.get("env") if isinstance(self.settings_config.get("env"), dict) else {}
        value = env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
        return value if isinstance(value, str) else ""

    def is_official(self) -> bool:
        return self.category == "official" or self.meta.get("isOfficial") is True

    def set_api_key(self, api_key: str, preferred_field: str | None = None) -> None:
        set_api_key(self.settings_config, api_key, preferred_field)

    def validate_for_claude(self) -> None:
        if not isinstance(self.settings_config, dict):
            raise ValueError("settingsConfig 必须是 JSON 对象")
        env = self.settings_config.get("env")
        if env is not None and not isinstance(env, dict):
            raise ValueError("settingsConfig.env 必须是 JSON 对象")
        if not self.is_official():
            env = env if isinstance(env, dict) else {}
            if not env.get("ANTHROPIC_BASE_URL"):
                raise ValueError("非官方供应商缺少 ANTHROPIC_BASE_URL")
            if not self.api_key() and not self.meta.get("requiresOAuth"):
                raise ValueError("非官方供应商缺少 API Key")

    def live_settings(self) -> dict[str, Any]:
        return sanitize_for_live(self.settings_config)

    def common_config(self) -> dict[str, Any]:
        return extract_common_config(self.settings_config)

    def summary(self) -> str:
        label = self.model() or "(无模型)"
        base = self.base_url() or "official-login"
        return f"{self.name}  {label}  {base}  key={mask_secret(self.api_key())}"
