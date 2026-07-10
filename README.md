# ccswitch-nogui

`ccswitch-nogui` 是一个纯终端版 Claude Code 供应商切换工具，用 Python 复刻 [farion1231/cc-switch](https://github.com/farion1231/cc-switch/) 的 Claude Code Provider 管理主链路。

它适合没有桌面环境的服务器、SSH 会话、容器和远程开发机：不需要 Tauri GUI，不需要数据库，也不需要常驻后台进程。

## 它解决什么问题

Claude Code 的供应商配置最终会落到 `~/.claude/settings.json`。如果你经常在 DeepSeek、Kimi、GLM、MiniMax、OpenRouter、Bedrock、Claude 官方登录等配置之间切换，手改 JSON 很容易出错，也容易把 API Key 误提交。

`ccswitch-nogui` 做三件事：

- 管理多个 Claude Code provider 配置
- 从上游 `cc-switch` 同步 Claude Code 供应商预设
- 安全地把选中的 provider 写入 `~/.claude/settings.json`

## 特性

- 纯 Python，无第三方运行时依赖
- 数字菜单，适合 SSH / 无头服务器
- 支持脚本化子命令，例如 `list`、`switch`、`add`、`import-live`
- 预设格式对齐上游 `claudeProviderPresets.ts`
- 当前内置 71 个 Claude Code provider 预设
- 支持上游字段：`settingsConfig`、`category`、`apiKeyField`、`templateValues`、`apiFormat`、`providerType`
- 支持 `ANTHROPIC_AUTH_TOKEN` 和 `ANTHROPIC_API_KEY`
- 支持 `${VAR}` 模板变量，例如 AWS Bedrock 的 region / AK / SK
- 切换前自动备份 live 配置
- 切换前回填当前 live 配置到旧 provider，避免直接在 Claude Code 里改过的设置丢失
- JSON 原子写入，降低半写损坏风险
- 首次运行自动迁移旧版 `~/.claude/cc-profiles.json`
- 导出时自动清空 key/token/secret/password/credential 类字段

## 安装

克隆仓库后直接运行：

```bash
git clone https://github.com/cmdCQ/ccswitch-nogui.git
cd ccswitch-nogui
python3 cc-switch.py
```

也可以把脚本目录加入 PATH，或自己加一个 shell alias：

```bash
alias ccswitch='python3 /path/to/ccswitch-nogui/cc-switch.py'
```

## 快速开始

查看预设：

```bash
python3 cc-switch.py presets
```

从预设新增 DeepSeek 并立即切换：

```bash
python3 cc-switch.py add --preset DeepSeek --api-key sk-xxx --switch
```

查看当前 provider：

```bash
python3 cc-switch.py current
```

列出所有 provider：

```bash
python3 cc-switch.py list
```

切换到指定 provider：

```bash
python3 cc-switch.py switch deepseek
```

从当前 Claude Code live 配置导入：

```bash
python3 cc-switch.py import-live --name default
```

进入交互式菜单：

```bash
python3 cc-switch.py
```

## 交互式菜单

菜单全程使用数字操作：

```text
1-N  切换到对应供应商
N+1  新增供应商
N+2  修改供应商
N+3  删除供应商
N+4  从当前 ~/.claude/settings.json 导入
N+5  添加 Claude 官方登录预设
N+6  提取当前供应商的通用配置片段
0    退出
```

新增 provider 时可以选择上游预设，也可以手动填写 `ANTHROPIC_BASE_URL`、API Key 和模型名。

## 子命令

列出 provider：

```bash
python3 cc-switch.py list
python3 cc-switch.py list --json
```

查看当前 provider：

```bash
python3 cc-switch.py current
python3 cc-switch.py current --json
```

切换 provider：

```bash
python3 cc-switch.py switch <provider-id>
```

列出预设：

```bash
python3 cc-switch.py presets
python3 cc-switch.py presets --json
```

从预设新增：

```bash
python3 cc-switch.py add --preset DeepSeek --api-key sk-xxx --switch
```

手动新增：

```bash
python3 cc-switch.py add \
  --name MyProvider \
  --base-url https://api.example.com/anthropic \
  --api-key sk-xxx \
  --model claude-sonnet-compatible \
  --switch
```

导入当前 live 配置：

```bash
python3 cc-switch.py import-live --name default
python3 cc-switch.py import-live --name default --no-switch
```

导出 provider 配置，密钥会自动置空：

```bash
python3 cc-switch.py export ./providers.redacted.json
```

导入 provider 配置：

```bash
python3 cc-switch.py import ./providers.redacted.json
python3 cc-switch.py import ./providers.redacted.json --replace
```

查看 provider JSON：

```bash
python3 cc-switch.py show deepseek
python3 cc-switch.py show deepseek --redact
```

提取通用配置片段：

```bash
python3 cc-switch.py common
python3 cc-switch.py common deepseek
```

## 数据位置

| 路径 | 说明 |
| --- | --- |
| `~/.ccswitch-nogui/providers.json` | 新版 provider 数据，包含 API Key，权限 600 |
| `~/.ccswitch-nogui/backups/` | 写入 live 配置前自动备份，默认保留最近 10 份 |
| `~/.claude/settings.json` | Claude Code live 配置 |
| `~/.claude/cc-profiles.json` | 旧版数据源，仅首次自动迁移读取 |

临时测试时可以隔离真实 HOME：

```bash
CCSWITCH_NOGUI_HOME=/tmp/ccswitch-test python3 cc-switch.py list
```

如果你的 Claude Code 配置目录不是默认 `~/.claude`，可以指定：

```bash
CCSWITCH_NOGUI_CLAUDE_DIR=/path/to/.claude python3 cc-switch.py list
```

## 与上游 cc-switch 的关系

本项目严格复刻的是上游的 Claude Code provider 管理主路径：

- provider 使用 `settingsConfig` 作为配置快照
- 官方 provider 写入空 `env`，由 Claude Code 官方登录/OAuth 接管
- 第三方 provider 支持 `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY`
- 预设保留上游 `category`、`apiKeyField`、`templateValues`、`apiFormat`、`providerType`
- 写 live 前剥离 `apiFormat` 等管理器内部字段
- 旧 `ANTHROPIC_SMALL_FAST_MODEL` 会规范化为 `ANTHROPIC_DEFAULT_*_MODEL`
- 导出和通用配置提取会剥离凭据字段

没有复刻上游桌面端的这些能力：

- Tauri 图形界面、系统托盘、自动更新
- SQLite 数据库和云同步
- Codex / Gemini / OpenCode / OpenClaw / Hermes 多应用管理
- 本地代理接管、协议转换、故障转移、健康检查
- MCP、Prompts、Skills、Session、Usage dashboard

这些能力依赖大量 Rust、Tauri、SQLite 和前端状态管理。`ccswitch-nogui` 的定位是服务器上的 Claude Code provider switcher，而不是完整桌面应用替代品。

## 项目结构

```text
cc-switch.py          兼容入口
ccswitch/cli.py       交互菜单和子命令
ccswitch/manager.py   provider 增删改查、切换、导入导出
ccswitch/models.py    provider 数据模型、脱敏、模板变量、live 写入清洗
ccswitch/paths.py     路径、备份、原子写入
ccswitch/presets.py   上游预设加载和转换
ccswitch/store.py     providers.json 存储和旧配置迁移
presets.json          Claude Code provider 预设
tests/test_cli.py     CLI 级回归测试
```

## 安全

- 不要提交 `~/.ccswitch-nogui/providers.json`
- 不要把真实 GitHub token、Claude/Anthropic token 或第三方 API Key 写入 README、issue、commit message
- `export` 默认会清空凭据字段，但导入前仍应人工确认导出文件内容
- 如果密钥已经在聊天、日志或终端记录里明文出现，建议立即去对应平台轮换

## 开发验证

本项目测试只依赖 Python 标准库：

```bash
python3 -m compileall cc-switch.py ccswitch tests
python3 -m unittest discover -s tests -v
```

推送前建议再做一次密钥扫描：

```bash
rg -n 'github_[p]at_|g[h]p_|g[h]o_|g[h]u_|g[h]s_|g[h]r_' . --glob '!.git/**' --glob '!__pycache__/**'
rg -n 's[k]-' . --glob '!.git/**' --glob '!__pycache__/**'
```

## Contributors

- [farion1231](https://github.com/farion1231) / Jason Young - author of [CC Switch](https://github.com/farion1231/cc-switch/), the upstream project whose Claude Code provider presets and provider-management model this project follows.

## License

MIT
