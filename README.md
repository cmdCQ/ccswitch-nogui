# ccswitch-nogui

**命令行版 Claude Code 供应商切换工具** —— 无需桌面 GUI，在纯终端 / 无头服务器上即可使用。

思路参考 [cc-switch](https://github.com/farion1231/cc-switch)（一个跨平台桌面 GUI 应用）：内置常见供应商预设，一键在多个 API 供应商之间切换。区别是本工具是纯 Python 脚本，**跑在没有图形界面的服务器上**。

## 它做什么

Claude Code 的供应商配置存放在 `~/.claude/settings.json` 的 `env` 块里（`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / 各模型名）。切换供应商本质上就是改这几个键。本工具帮你：

- 📋 用内置预设快速新增配置（自动带好 base_url 和模型名，**你只需填 API Key**）
- 🔀 在保存好的多个配置之间一键切换
- ✏️ 新增 / 修改 / 删除配置
- 💾 每次改动前**自动备份** `settings.json` 到 `~/.claude/backups/`
- 🛡 只改 `env` 里供应商相关的键，你的**权限、主题等其它配置原样保留**

## 使用

```bash
python3 cc-switch.py
```

菜单示例：

```
====================================================
 Claude Code 供应商切换  (ccswitch-nogui)
====================================================
 你的配置：
  1) DeepSeek           deepseek-v4-pro   key=sk-xxxx…abcd
  2) Kimi (Moonshot)    kimi-k2.7-code    key=sk-yyyy…efgh
----------------------------------------------------
 请输入数字：
  1-2  = 切换到对应配置
  3)  ➕ 新增配置
  4)  ✏️  修改配置
  5)  🗑  删除配置
  0)  退出
```

全程用**数字**操作：

- **1 ~ N** → 切换到对应配置
- **新增** → 分两步：① 先从预设列表选一个供应商（自动带好地址和模型）② 只需补填 API Key
- **修改 / 删除** → 输入对应数字后再选要操作的编号
- **0** → 退出

> ⚠ 改完配置需要 **重启 Claude Code / 新开会话** 才生效（`env` 只在启动时读取）。

## 内置预设

`presets.json` 收录了常见供应商（数据来源 cc-switch 的 `claudeProviderPresets.ts`）：
DeepSeek、Kimi(Moonshot)、Zhipu GLM、MiniMax、Longcat、StepFun、ModelScope、阿里百炼、七牛、AiHubMix、Claude 官方，以及「自定义」。

**所有预设的 API Key 字段一律为空**，需要你自己在对应平台申请后填入。可自行编辑 `presets.json` 增删。

## 文件说明

| 文件 | 说明 |
|------|------|
| `cc-switch.py` | 主脚本（交互式切换） |
| `presets.json` | 供应商预设 |
| `~/.claude/cc-profiles.json` | 你保存的配置（**含 API Key，权限 600，不进 git**）|

## 安全

- 你的 API Key 只存在本机 `~/.claude/cc-profiles.json`（权限 600），**不会被提交到 git**。
- 本仓库不包含任何真实密钥。

## License

MIT
