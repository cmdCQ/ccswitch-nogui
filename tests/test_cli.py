from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cc-switch.py"


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CCSWITCH_NOGUI_HOME"] = str(home)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class CliTests(unittest.TestCase):
    def make_home(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        return tmp, Path(tmp.name) / "home"

    def test_add_switch_and_backup(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            claude = home / ".claude"
            claude.mkdir(parents=True)
            settings = claude / "settings.json"
            settings.write_text(
                json.dumps({"permissions": {"allow": ["Read"]}, "env": {"KEEP": "1"}}),
                encoding="utf-8",
            )

            add = run_cli(
                home,
                "add",
                "--name",
                "DeepSeek Test",
                "--base-url",
                "https://api.deepseek.com/anthropic",
                "--api-key",
                "sk-test",
                "--model",
                "deepseek-v4-pro",
                "--switch",
            )
            self.assertEqual(add.returncode, 0, add.stderr)

            live = read_json(settings)
            self.assertEqual(live["env"]["ANTHROPIC_BASE_URL"], "https://api.deepseek.com/anthropic")
            self.assertEqual(live["env"]["ANTHROPIC_AUTH_TOKEN"], "sk-test")
            self.assertEqual(live["env"]["ANTHROPIC_MODEL"], "deepseek-v4-pro")
            self.assertNotIn("permissions", live)
            self.assertTrue(list((home / ".ccswitch-nogui" / "backups").glob("claude-settings.*.json")))

    def test_legacy_profiles_are_migrated(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            claude = home / ".claude"
            claude.mkdir(parents=True)
            (claude / "cc-profiles.json").write_text(
                json.dumps(
                    {
                        "profiles": [
                            {
                                "name": "Legacy",
                                "base_url": "https://legacy.example/anthropic",
                                "auth_token": "sk-legacy",
                                "big": "legacy-big",
                                "small": "legacy-small",
                                "effort": "high",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = run_cli(home, "list", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            provider = data["providers"][0]
            env = provider["settingsConfig"]["env"]
            self.assertEqual(provider["name"], "Legacy")
            self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "sk-legacy")
            self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "legacy-small")
            self.assertEqual(env["CLAUDE_CODE_EFFORT_LEVEL"], "high")

    def test_official_preset_writes_empty_env(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            result = run_cli(home, "add", "--preset", "Claude Official", "--switch")
            self.assertEqual(result.returncode, 0, result.stderr)
            live = read_json(home / ".claude" / "settings.json")
            self.assertEqual(live, {"env": {}})

    def test_export_redacts_secrets(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            add = run_cli(
                home,
                "add",
                "--name",
                "Redact",
                "--base-url",
                "https://example.com",
                "--api-key",
                "sk-secret-value",
                "--model",
                "model-x",
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            export_path = Path(tmp.name) / "export.json"
            result = run_cli(home, "export", str(export_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            text = export_path.read_text(encoding="utf-8")
            self.assertNotIn("sk-secret-value", text)
            data = json.loads(text)
            env = data["providers"][0]["settingsConfig"]["env"]
            self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "")
            mode = stat.S_IMODE(export_path.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_presets_include_upstream_shape(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            result = run_cli(home, "presets", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            names = {preset["name"] for preset in data["presets"]}
            self.assertIn("Claude Official", names)
            self.assertIn("DeepSeek", names)
            self.assertIn("AWS Bedrock (AKSK)", names)
            self.assertGreaterEqual(len(data["presets"]), 50)
    def test_list_uses_table_layout(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            add = run_cli(
                home,
                "add",
                "--name",
                "DeepSeek Test",
                "--base-url",
                "https://api.deepseek.com/anthropic",
                "--api-key",
                "sk-test",
                "--model",
                "deepseek-v4-pro",
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            result = run_cli(home, "list")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("* = 当前使用", result.stdout)
            self.assertIn("分类", result.stdout)
            self.assertIn("模型", result.stdout)
            self.assertIn("DeepSeek Test", result.stdout)

    def test_presets_uses_table_layout(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            result = run_cli(home, "presets")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("分类", result.stdout)
            self.assertIn("地址", result.stdout)
            self.assertIn("Claude Official", result.stdout)
    def test_interactive_ctrl_c_exits_without_traceback(self) -> None:
        tmp, home = self.make_home()
        with tmp:
            env = os.environ.copy()
            env["CCSWITCH_NOGUI_HOME"] = str(home)
            env["PYTHONPATH"] = str(ROOT)
            script = """
import os
import signal
import sys
sys.path.insert(0, os.environ['PYTHONPATH'])
from ccswitch.cli import main

def stop(*_args):
    raise KeyboardInterrupt
signal.signal(signal.SIGALRM, stop)
signal.alarm(1)
raise SystemExit(main([]))
"""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=str(ROOT),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=5,
            )
            self.assertEqual(result.returncode, 130)
            self.assertIn("已取消", result.stdout)
            self.assertNotIn("Traceback", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
