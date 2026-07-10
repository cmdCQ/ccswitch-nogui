from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from .manager import ProviderManager, format_json
from .models import Provider, mask_secret, unique_id
from .paths import claude_settings_path, store_path
from .presets import load_presets, preset_to_provider, template_prompts


def ask(prompt: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    if secret:
        try:
            import getpass

            value = getpass.getpass(f"{prompt}{suffix}: ").strip()
        except Exception:
            value = input(f"{prompt}{suffix}: ").strip()
    else:
        value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def choose_number(prompt: str, minimum: int, maximum: int) -> int | None:
    value = ask(prompt)
    if not value.isdigit():
        print("[X] 请输入数字")
        return None
    number = int(value)
    if minimum <= number <= maximum:
        return number
    print("[X] 编号无效")
    return None


def clip(value: object, width: int) -> str:
    text = str(value or "-")
    if display_width(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    result = ""
    for ch in text:
        if display_width(result + ch + "...") > width:
            break
        result += ch
    return result + "..."


def display_width(text: str) -> int:
    width = 0
    for ch in text:
        width += 2 if ord(ch) > 127 else 1
    return width


def cell(value: object, width: int, align: str = "<") -> str:
    text = clip(value, width)
    padding = max(width - display_width(text), 0)
    if align == ">":
        return " " * padding + text
    return text + " " * padding


def category_label(category: str | None) -> str:
    labels = {
        "official": "官方",
        "custom": "自定义",
        "aggregator": "聚合",
        "third_party": "第三方",
        "cn_official": "国内官方",
        "cloud_provider": "云厂商",
    }
    return labels.get(category or "custom", category or "自定义")


def provider_key_label(provider: Provider) -> str:
    if provider.meta.get("requiresOAuth"):
        return "OAuth"
    if provider.is_official():
        return "官方登录"
    return mask_secret(provider.api_key())


def provider_model_label(provider: Provider) -> str:
    return provider.model() or ("官方登录" if provider.is_official() else "-")


def print_current_summary(manager: ProviderManager) -> None:
    provider = manager.current_provider()
    if provider is None:
        print(" 当前配置: (无)")
        return
    print(
        " 当前配置: "
        f"{provider.name} ({provider.id})  "
        f"模型={provider_model_label(provider)}  "
        f"密钥={provider_key_label(provider)}"
    )


def print_providers(manager: ProviderManager) -> None:
    providers = manager.list_providers()
    current = manager.store.current
    if not providers:
        print("  还没有保存任何供应商。可新增供应商，或从当前 ~/.claude/settings.json 导入。")
        return

    print("配置列表：")
    for index, provider in enumerate(providers, 1):
        mark = "*" if provider.id == current else " "
        print(
            f"  {mark} {index:>2}. "
            f"{cell(provider.name, 16)} "
            f"{cell(category_label(provider.category), 8)} "
            f"{cell(provider_model_label(provider), 18)} "
            f"key={provider_key_label(provider)}"
        )
        print(f"       id={provider.id}  url={provider.base_url() or '官方登录'}")


def provider_by_number(manager: ProviderManager, number: int) -> Provider:
    providers = manager.list_providers()
    if number < 1 or number > len(providers):
        raise ValueError("编号无效")
    return providers[number - 1]


def pick_preset() -> dict[str, Any] | None:
    presets = load_presets()
    if not presets:
        print("[X] presets.json 为空")
        return None
    print("\n" + "-" * 72)
    print("选择供应商预设")
    print("-" * 72)
    for index, preset in enumerate(presets, 1):
        settings = preset.get("settingsConfig") if isinstance(preset.get("settingsConfig"), dict) else {}
        env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        base_url = env.get("ANTHROPIC_BASE_URL") or preset.get("base_url") or "官方登录"
        category = preset.get("category") or ("official" if preset.get("isOfficial") else "custom")
        print(f" {index:2d}) {preset.get('name', 'Custom'):<28} {category:<12} {base_url}")
    print("  0) 手动创建")
    number = choose_number("请输入预设编号", 0, len(presets))
    if number is None:
        return None
    if number == 0:
        return {}
    return presets[number - 1]


def build_provider_interactive(manager: ProviderManager, old: Provider | None = None) -> Provider | None:
    if old:
        provider = old.copy()
    else:
        preset = pick_preset()
        if preset is None:
            return None
        if preset:
            template_values: dict[str, str] = {}
            for key, label, default in template_prompts(preset):
                template_values[key] = ask(label, default)
            api_key = ""
            if not preset.get("isOfficial") and not preset.get("requiresOAuth"):
                api_key = ask("API Key", secret=True)
            try:
                provider = preset_to_provider(
                    preset,
                    manager.store.ids(),
                    api_key=api_key,
                    template_values=template_values,
                )
            except ValueError as exc:
                print(f"[X] {exc}")
                return None
        else:
            provider = Provider(
                id=unique_id("custom", manager.store.ids()),
                name="Custom",
                settings_config={"env": {"ANTHROPIC_AUTH_TOKEN": ""}},
                category="custom",
            )

    print("\n填写配置（回车使用默认值）")
    provider.name = ask("名称", provider.name)
    provider.id = ask("ID", provider.id)
    provider.website_url = ask("网站", provider.website_url or "") or None
    provider.category = ask("分类", provider.category or "custom") or "custom"

    env = provider.settings_config.setdefault("env", {})
    if not isinstance(env, dict):
        print("[X] settingsConfig.env 不是对象")
        return None

    if provider.category != "official":
        env["ANTHROPIC_BASE_URL"] = ask("ANTHROPIC_BASE_URL", str(env.get("ANTHROPIC_BASE_URL") or ""))
        current_key = provider.api_key()
        new_key = ask("API Key", current_key, secret=True)
        provider.set_api_key(new_key, provider.meta.get("apiKeyField"))
        model = ask("ANTHROPIC_MODEL", str(env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") or ""))
        if model:
            env["ANTHROPIC_MODEL"] = model
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = ask("Sonnet 模型", str(env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") or model))
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = ask("Opus 模型", str(env.get("ANTHROPIC_DEFAULT_OPUS_MODEL") or model))
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = ask("Haiku 模型", str(env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") or model))
        effort = ask("CLAUDE_CODE_EFFORT_LEVEL", str(env.get("CLAUDE_CODE_EFFORT_LEVEL") or ""))
        if effort:
            env["CLAUDE_CODE_EFFORT_LEVEL"] = effort
        else:
            env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)

    notes = ask("备注", provider.notes or "")
    provider.notes = notes or None
    try:
        provider.validate_for_claude()
    except ValueError as exc:
        print(f"[X] {exc}")
        return None
    return provider


def interactive_menu() -> int:
    manager = ProviderManager()
    while True:
        providers = manager.list_providers()
        n = len(providers)
        print("\n" + "=" * 72)
        print(" Claude Code 供应商切换  ccswitch-nogui")
        print("=" * 72)
        print_current_summary(manager)
        print(f" 数据文件: {store_path()}")
        print(f" Live配置: {claude_settings_path()}")
        print("-" * 72)
        print_providers(manager)
        print("-" * 72)
        print("操作：")
        if n == 1:
            print("  1    切换到该供应商")
        elif n > 1:
            print(f"  1-{n:<2} 切换到对应供应商")
        print(f"  {n + 1:<4} 新增供应商")
        print(f"  {n + 2:<4} 修改供应商")
        print(f"  {n + 3:<4} 删除供应商")
        print(f"  {n + 4:<4} 从当前 ~/.claude/settings.json 导入")
        print(f"  {n + 5:<4} 添加 Claude 官方登录预设")
        print(f"  {n + 6:<4} 提取当前供应商的通用配置片段")
        print("  0    退出")
        choice = choose_number("请选择", 0, n + 6)
        if choice is None:
            continue
        try:
            if choice == 0:
                return 0
            if 1 <= choice <= n:
                provider = provider_by_number(manager, choice)
                manager.switch(provider.id)
                print(f"[OK] 已切换到 {provider.name} ({provider.id})")
                print("[!] 如当前 Claude Code 进程未热读 env，请重启/新开会话。")
            elif choice == n + 1:
                provider = build_provider_interactive(manager)
                if provider:
                    manager.add_provider(provider, switch=ask("现在切换到它吗? (1=是 / 回车=否)") == "1")
                    print(f"[OK] 已新增 {provider.name} ({provider.id})")
            elif choice == n + 2:
                if not providers:
                    print("[X] 没有可修改的供应商")
                    continue
                number = choose_number("修改哪个编号", 1, n)
                if number is None:
                    continue
                old = provider_by_number(manager, number)
                provider = build_provider_interactive(manager, old)
                if provider:
                    manager.update_provider(old.id, provider)
                    print(f"[OK] 已更新 {provider.name} ({provider.id})")
            elif choice == n + 3:
                if not providers:
                    print("[X] 没有可删除的供应商")
                    continue
                number = choose_number("删除哪个编号", 1, n)
                if number is None:
                    continue
                provider = provider_by_number(manager, number)
                confirm = ask(f"确认删除 {provider.name}? 输入 delete 确认")
                if confirm == "delete":
                    manager.delete_provider(provider.id)
                    print(f"[OK] 已删除 {provider.name} ({provider.id})")
            elif choice == n + 4:
                name = ask("导入名称", "default")
                provider = manager.import_live(name=name)
                print(f"[OK] 已导入并切换到 {provider.name} ({provider.id})")
            elif choice == n + 5:
                provider = manager.seed_official()
                print(f"[OK] 已存在/新增 {provider.name} ({provider.id})")
            elif choice == n + 6:
                common = manager.extract_common_config()
                print(format_json(common))
        except Exception as exc:
            print(f"[X] {exc}")


def cmd_list(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    if args.json:
        print(format_json(manager.store.to_dict()))
    else:
        print_providers(manager)
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    provider = manager.switch(args.provider)
    print(f"[OK] 已切换到 {provider.name}")
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    provider = manager.current_provider()
    if not provider:
        print("(无当前供应商)")
        return 1
    if args.json:
        print(format_json(provider.to_dict()))
    else:
        print(f"{provider.id}: {provider.summary()}")
    return 0


def cmd_presets(args: argparse.Namespace) -> int:
    presets = load_presets()
    if args.json:
        print(format_json({"presets": presets}))
        return 0
    print("预设列表：")
    for index, preset in enumerate(presets, 1):
        settings = preset.get("settingsConfig") if isinstance(preset.get("settingsConfig"), dict) else {}
        env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        base_url = env.get("ANTHROPIC_BASE_URL") or preset.get("base_url") or "官方登录"
        model = env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") or "-"
        category = preset.get("category") or ("official" if preset.get("isOfficial") else "custom")
        print(
            f"  {index:>2}. "
            f"{cell(preset.get('name', 'Custom'), 24)} "
            f"{cell(category_label(category), 8)} "
            f"{cell(model, 22)} "
            f"{base_url}"
        )
    return 0


def find_preset(name: str) -> dict[str, Any]:
    for preset in load_presets():
        if str(preset.get("name", "")).lower() == name.lower():
            return preset
    raise ValueError(f"预设不存在: {name}")


def cmd_add(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    preset = find_preset(args.preset) if args.preset else {}
    if preset:
        provider = manager.add_from_preset(preset, api_key=args.api_key or "", name=args.name, switch=args.switch)
    else:
        env: dict[str, Any] = {"ANTHROPIC_BASE_URL": args.base_url or "", "ANTHROPIC_AUTH_TOKEN": args.api_key or ""}
        if args.model:
            env.update(
                {
                    "ANTHROPIC_MODEL": args.model,
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": args.haiku_model or args.model,
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": args.sonnet_model or args.model,
                    "ANTHROPIC_DEFAULT_OPUS_MODEL": args.opus_model or args.model,
                }
            )
        provider = Provider(
            id=unique_id(args.id or args.name or "custom", manager.store.ids()),
            name=args.name or "Custom",
            settings_config={"env": env},
            category=args.category or "custom",
        )
        manager.add_provider(provider, switch=args.switch)
    print(f"[OK] 已新增 {provider.id}: {provider.name}")
    return 0


def cmd_import_live(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    provider = manager.import_live(name=args.name, make_current=not args.no_switch)
    print(f"[OK] 已导入 {provider.id}: {provider.name}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    manager.export_config(Path(args.path).expanduser())
    print(f"[OK] 已导出到 {args.path}（密钥已置空）")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    count = manager.import_config(Path(args.path).expanduser(), merge=not args.replace)
    print(f"[OK] 已导入 {count} 个供应商")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    provider = manager.store.get(args.provider)
    if provider is None:
        raise ValueError(f"供应商不存在: {args.provider}")
    data = provider.to_dict()
    if args.redact:
        data = copy.deepcopy(data)
        settings = data.get("settingsConfig")
        if isinstance(settings, dict):
            for key in list(settings.get("env", {})) if isinstance(settings.get("env"), dict) else []:
                if any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                    settings["env"][key] = mask_secret(settings["env"].get(key))
    print(format_json(data))
    return 0


def cmd_common(args: argparse.Namespace) -> int:
    manager = ProviderManager()
    if args.provider:
        common = manager.extract_common_config(args.provider)
    else:
        common = manager.extract_common_config()
    print(format_json(common))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Claude Code 供应商切换工具（无 GUI）")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list", help="列出供应商")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("current", help="显示当前供应商")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_current)

    p = sub.add_parser("switch", help="切换供应商")
    p.add_argument("provider")
    p.set_defaults(func=cmd_switch)

    p = sub.add_parser("presets", help="列出预设")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("add", help="新增供应商")
    p.add_argument("--preset")
    p.add_argument("--name")
    p.add_argument("--id")
    p.add_argument("--base-url")
    p.add_argument("--api-key")
    p.add_argument("--model")
    p.add_argument("--haiku-model")
    p.add_argument("--sonnet-model")
    p.add_argument("--opus-model")
    p.add_argument("--category")
    p.add_argument("--switch", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("import-live", help="从当前 ~/.claude/settings.json 导入")
    p.add_argument("--name", default="default")
    p.add_argument("--no-switch", action="store_true")
    p.set_defaults(func=cmd_import_live)

    p = sub.add_parser("export", help="导出供应商配置（密钥置空）")
    p.add_argument("path")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="导入供应商配置")
    p.add_argument("path")
    p.add_argument("--replace", action="store_true")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("show", help="显示供应商 JSON")
    p.add_argument("provider")
    p.add_argument("--redact", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("common", help="提取通用配置片段")
    p.add_argument("provider", nargs="?")
    p.set_defaults(func=cmd_common)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not args.command:
            return interactive_menu()
        return args.func(args)
    except (KeyboardInterrupt, EOFError):
        print("\n已取消")
        return 130
    except Exception as exc:
        print(f"[X] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
