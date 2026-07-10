#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ccswitch-nogui —— Claude Code 供应商切换工具（命令行版，无需桌面 GUI）

思路对齐 cc-switch (github.com/farion1231/cc-switch)：
用内置供应商预设(presets.json)快速新增配置，只改 ~/.claude/settings.json 的 env 块，
其余配置(权限/主题等)原样保留，改动前自动备份。

你的配置档案存在 ~/.claude/cc-profiles.json（含 API Key，权限 600，绝不进 git）。
"""
import json, os, sys, shutil, time

HOME = os.path.expanduser("~")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")
PROFILES = os.path.join(HOME, ".claude", "cc-profiles.json")
BACKUP_DIR = os.path.join(HOME, ".claude", "backups")
PRESETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets.json")

# ---- 一个档案 -> settings.json env 的 8 个键 ----
def profile_to_env(p):
    return {
        "ANTHROPIC_BASE_URL": p["base_url"],
        "ANTHROPIC_AUTH_TOKEN": p["auth_token"],
        "ANTHROPIC_MODEL": p["big"],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": p["big"],
        "ANTHROPIC_DEFAULT_SONNET_MODEL": p["big"],
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": p["small"],
        "CLAUDE_CODE_SUBAGENT_MODEL": p["small"],
        "CLAUDE_CODE_EFFORT_LEVEL": p.get("effort", "max"),
    }

def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            print("⚠ %s 解析失败，已忽略" % path)
    return default

def load_profiles():
    return load_json(PROFILES, {"profiles": []}).get("profiles", [])

def save_profiles(profiles):
    json.dump({"profiles": profiles}, open(PROFILES, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    os.chmod(PROFILES, 0o600)

def load_presets():
    return load_json(PRESETS_FILE, {"presets": []}).get("presets", [])

def backup_settings():
    if os.path.exists(SETTINGS):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        dst = os.path.join(BACKUP_DIR, "settings.%s.json" % time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(SETTINGS, dst)
        return dst
    return None

def apply_profile(p):
    settings = load_json(SETTINGS, {})
    b = backup_settings()
    env = settings.get("env", {})
    env.update(profile_to_env(p))   # 只更新供应商相关键，保留其它 env
    settings["env"] = env
    json.dump(settings, open(SETTINGS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n✅ 已切换到【%s】" % p["name"])
    print("   BASE_URL = %s" % p["base_url"])
    print("   大模型 = %s   小模型 = %s   effort = %s" % (p["big"], p["small"], p.get("effort", "max")))
    if b: print("   (原配置已备份到 %s)" % b)
    print("\n⚠ 需要【重启 Claude Code / 新开会话】才会生效（env 在启动时读取）。")

def mask(tok):
    return (tok[:8] + "…" + tok[-4:]) if tok and len(tok) > 14 else (tok or "(空)")

def ask(prompt, default=None):
    s = input(prompt + (" [%s]" % default if default else "") + ": ").strip()
    return s or (default or "")

def pick_preset():
    presets = load_presets()
    if not presets:
        return {}
    print("\n" + "-" * 52)
    print(" 第 1 步：选择供应商预设")
    print(" （选中后会自动填好 地址 和 模型，你只需再填 API Key）")
    print("-" * 52)
    for i, p in enumerate(presets, 1):
        tag = p["base_url"] or "（全部手动填写）"
        print("  %2d) %-24s %s" % (i, p["name"], tag))
    print("   0) 不用预设，全部手动填写")
    idx = ask("\n 请输入预设编号")
    if idx.isdigit() and 1 <= int(idx) <= len(presets):
        chosen = presets[int(idx) - 1]
        print(" → 已选【%s】" % chosen["name"])
        return chosen
    return {}

def input_profile(old=None):
    # 修改已有配置时不再选预设；新增时先选预设
    if old:
        base = old
    else:
        base = pick_preset()
    old = old or {}
    print("\n 第 2 步：填写配置（直接回车 = 使用中括号里的默认值）")
    name = ask("档案名称", base.get("name") or old.get("name"))
    base_url = ask("BASE_URL", base.get("base_url") or "https://api.deepseek.com/anthropic")
    auth = ask("API Key", old.get("auth_token"))
    big = ask("大模型 (opus/sonnet 用)", base.get("big") or old.get("big") or "")
    small = ask("小模型 (haiku/子agent，回车=同大模型)", base.get("small") or old.get("small") or "")
    if not small:
        small = big
    effort = ask("effort (low/medium/high/max)", old.get("effort", "max"))
    if not (name and base_url and auth and big):
        print("✖ 名称/BASE_URL/Key/大模型 均不能为空，已取消")
        return None
    return {"name": name, "base_url": base_url, "auth_token": auth,
            "big": big, "small": small, "effort": effort}

def menu():
    profiles = load_profiles()
    n = len(profiles)
    print("\n" + "=" * 52)
    print(" Claude Code 供应商切换  (ccswitch-nogui)")
    print("=" * 52)
    if profiles:
        print(" 你的配置：")
        for i, p in enumerate(profiles, 1):
            print("  %d) %-18s %-16s key=%s" % (i, p["name"], p["big"], mask(p["auth_token"])))
    else:
        print(" (还没有任何配置)")
    print("-" * 52)
    print(" 请输入数字：")
    if profiles:
        print("  1-%d  = 切换到对应配置" % n)
    print("  %d)  ➕ 新增配置" % (n + 1))
    if profiles:
        print("  %d)  ✏️  修改配置" % (n + 2))
        print("  %d)  🗑  删除配置" % (n + 3))
    print("  0)  退出")
    choice = input(" 请选择: ").strip()

    if not choice.isdigit():
        print("✖ 请输入数字")
        return menu()
    c = int(choice)

    if c == 0:
        return
    # 切换
    if 1 <= c <= n:
        apply_profile(profiles[c - 1])
        return
    # 新增
    if c == n + 1:
        p = input_profile()
        if p:
            profiles.append(p); save_profiles(profiles)
            print("✅ 已保存【%s】" % p["name"])
            if ask("现在就切换到它吗? (1=是 / 回车=否)") == "1":
                apply_profile(p)
        return menu()
    # 修改
    if c == n + 2 and profiles:
        idx = ask("修改哪个编号")
        if idx.isdigit() and 1 <= int(idx) <= n:
            p = input_profile(profiles[int(idx) - 1])
            if p:
                profiles[int(idx) - 1] = p; save_profiles(profiles); print("✅ 已更新")
        else:
            print("✖ 编号无效")
        return menu()
    # 删除
    if c == n + 3 and profiles:
        idx = ask("删除哪个编号")
        if idx.isdigit() and 1 <= int(idx) <= n:
            gone = profiles.pop(int(idx) - 1); save_profiles(profiles)
            print("🗑 已删除【%s】" % gone["name"])
        else:
            print("✖ 编号无效")
        return menu()
    print("✖ 输入无效")
    return menu()

if __name__ == "__main__":
    try:
        menu()
    except (KeyboardInterrupt, EOFError):
        print("\n已取消")
