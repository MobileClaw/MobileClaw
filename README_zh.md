# MobileClaw - 全自主移动智能体

<div align="center">

![中文文档](https://img.shields.io/badge/中文文档-当前版本-0f766e?style=flat-square)
[![English](https://img.shields.io/badge/English-README.md-2563eb?style=flat-square)](README.md)
[![Website](https://img.shields.io/badge/Website-mobileclaw.cc-7c3aed?style=flat-square)](https://mobileclaw.cc/)
[![Android App](https://img.shields.io/badge/Android%20App-下载-16a34a?style=flat-square)](https://mobileclaw.cc/files/MobileClaw.apk)
[![X](https://img.shields.io/badge/X-@MobileClawX-111111?style=flat-square)](https://x.com/MobileClawX)
[![News](https://img.shields.io/badge/News-最新动态-f59e0b?style=flat-square)](#动态)

</div>

<div align="center">
  <img src="_res/brand.png" alt="mobileclaw" width="600">
</div>

<div align="center">
  <img src="_res/mobileclaw_demo_5x.gif" alt="mobileclaw_demo" width="100%">
</div>

<div align="center">

### 面向所有人的类人移动端自动化

</div>

---

MobileClaw 的使命是在移动设备（例如你的备用手机）上实现类似 openclaw 的智能体能力。

与基于底层系统命令、第三方 API 和 MCP 服务的现有编程智能体不同，MobileClaw 主要通过类似人类的 GUI 交互方式执行任务，这意味着对所有人（包括非专业人士）在日常使用中具有更高的可用性和可靠性。

## 亮点

- 专为移动设备（如 Android）原生构建。
- 通过视觉/GUI 实现类人交互。
- 轻量化设计，最小化第三方服务集成。
- 使用 `.md` 文件组织记忆。
- 通过日常消息应用与用户沟通。

> [!IMPORTANT]
> - 为避免安全风险，请**不要**使用 MobileClaw 控制你的主力设备。
> - 我们强烈建议在 MobileClaw 控制的设备上使用**独立的应用账号**，且**不要**滥用互联网服务。

## 动态

- 2026.03.27 MobileClaw app v0.3.3 发布。
- 2026.03.26 新增对 Weixin 聊天通道的支持。
- 2026.02.08 项目启动。

## 安装方法

### 面向普通用户

- 下载并安装 [MobileClaw Android app](https://mobileclaw.cc/files/MobileClaw.apk)。
- 完成模型与聊天通道配置。
- 点击启动按钮即可开始使用。

更多说明请访问我们的[项目网站](https://mobileclaw.cc/)。

### 面向开发者

1. 克隆本项目。
2. 运行 `cd MobileClaw` 和 `pip install -e .`

## 使用方法

1. 设置你的 Android 设备。详见 [Android 设备设置](#android-设备设置)。
2. 将 `config.yaml.example` 复制为 `config.yaml` 并填写配置信息。
   1. 参见[模型配置](#模型配置)了解如何配置模型提供商。
   2. 参见[聊天应用配置](#聊天应用配置)了解如何连接聊天应用。
3. 使用 `mobileclaw config.yaml` 启动你的智能体。
4. 向智能体发送消息或修改其 `profile.md` 进行个性化定制。

## Android 设备设置

1. 通过 ADB 连接你的 Android 设备。启用开发者模式。（[如何启用开发者模式？](https://www.android.com/intl/en_uk/articles/enable-android-developer-settings/)）
2. 运行 `adb install mobileclaw/resources/apk/MobileClaw.apk` 将客户端应用安装到你的手机。
3. 授予**无障碍服务权限**和**通知权限**；WebSocket 服务将在 Android 设备上自动启动。
4. 在 `config.yaml` 中设置 PC 端转发端口。在 `phone_port_mappings` 中为每台设备配置独立端口，如下所示：
   ```yaml
   phone_port_mappings:
       phone1: 51825
       phone2: 51826
   ```
5. 在你的电脑上运行 `adb forward tcp:<device_port> tcp:6666` 将 Android WebSocket 服务转发到 PC。`<device_port>` 是你在配置中设置的端口。

## 模型配置

MobileClaw 需要两个模型才能工作。一个用于通用任务控制（规划、记忆管理等），另一个用于计算机使用（GUI 定位、应用相关任务自动化等）。

每个模型需要三个配置值：`url`、`key` 和 `name`。它们应支持 OpenAI 兼容的 API。

例如，以下 `config.yaml` 中的配置将基础模型设置为 `gpt-5.2-chat`：

```yaml
custom_fm_url: "https://api.openai.com/v1/chat/completions"
custom_fm_key: "sk-xxx"
custom_fm_name: "gpt-5.2-chat"
tavily_api_key: "tvly-xxx"  # 可选，用于启用 Tavily 联网搜索
```

## 聊天应用配置

<div align="center">

| 平台 | 状态 |
| --- | --- |
| `telegram` | 支持 |
| `lark` | 支持 |
| `qq` | 支持 |
| `zulip` | 支持 |
| `discord` | 支持 |
| `whatsapp` | 支持 |
| `slack` | 支持 |
| `weixin` | 支持 |

</div>

MobileClaw 支持 `telegram`、`lark`、`qq`、`zulip`、`discord`、`whatsapp`、`slack` 和 `weixin`。你可以在 `config.yaml` 中通过逗号分隔的 `chat_channels` 同时启用多个平台：

```yaml
chat_channels: zulip,lark
default_chat_channel: zulip
```

<details>
<summary>Telegram</summary>

**1. 创建机器人**
- 打开 Telegram，搜索 `@BotFather`
- 发送 `/newbot`，按提示操作
- 复制机器人 token

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: telegram
chat_telegram_token: YOUR_BOT_TOKEN
chat_telegram_org_manager: YOUR_USER_ID  # 可选；留空则将第一个发消息的人视为org_manager
chat_telegram_proxy: http://proxy:port  # 可选；如果需要代理
```
</details>

<details>
<summary>Weixin</summary>

**1. 准备 iLink bot API**
- 确保你的微信机器人账号可以访问 iLink HTTP API
- 如果已经拿到 bot token，可直接填写配置
- 如果还没有 token，MobileClaw 启动后可以自动走扫码登录流程

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: weixin
chat_weixin_base_url: YOUR_BOT_BASE_URL  # 可选；留空则走扫码登录
chat_weixin_bot_token: YOUR_BOT_TOKEN  # 可选；留空则走扫码登录
```

**3. 说明**
- 当前实现支持文本消息接收与回复
- 如果未填写 `chat_weixin_bot_token`，程序启动时会通过日志输出QR Code URL（字段为qrcode_url=xxx），扫码即可绑定
- 用户首次给 bot 发消息后，会建立后续回复所需的会话上下文
</details>

<details>
<summary>Lark/飞书</summary>

**1. 创建飞书机器人**
- 访问[飞书开放平台](https://open.feishu.cn/app)
- 创建新应用 -> 启用**机器人**能力
- 从"凭证与基础信息"获取 **App ID** 和 **App Secret**
- 为机器人授予以下权限：
  - im:message.group_msg
  - contact:contact.base:readonly
  - im:chat
  - im:chat:read
  - im:message
  - im:message.reactions:write_only
  - im:message:send_as_bot
  - im:resource
- 启用**长连接**模式（需要先用 lark 启动一次 mobileclaw 以建立连接）

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: lark
chat_lark_app_id: cli_xxx
chat_lark_app_secret: xxx
chat_lark_org_manager: ou_xxx  # 可选，你的飞书 open_id 或手机号，留空则将第一个发消息的人视为org_manager
```
</details>

<details>
<summary>QQ</summary>

**1. 创建 QQ 机器人**
- 访问 [QQ 开放平台](https://q.qq.com)
- 创建新的机器人应用
- 从"开发者设置"获取 **AppID** 和 **Secret**

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: qq
chat_qq_app_id: YOUR_APP_ID
chat_qq_secret: YOUR_APP_SECRET
chat_qq_org_manager: YOUR_USER_OPENID  # 你的 QQ 用户 openid
```
</details>

<details>
<summary>Zulip</summary>

**1. 创建 Zulip 机器人**
- 进入你的 Zulip 组织设置
- 创建新机器人
- 复制机器人邮箱和 API 密钥（在 zuliprc 文件中）

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: zulip
chat_zulip_email: bot@example.zulipchat.com
chat_zulip_key: YOUR_API_KEY
chat_zulip_site: YOUR_ZULIP_ORG_URL
chat_zulip_org_manager: manager@example.com  # 组织管理员的 zulip 邮箱。默认格式：user{6位zulip-id}@{组织名}.zulipchat.com
```

</details>

<details>
<summary>Discord</summary>

**1. 创建 Discord 机器人**
- 访问 [Discord Developer Portal](https://discord.com/developers/applications)
- 创建新应用 -> 添加机器人
- 复制机器人 token
- 启用消息相关 intents，尤其是 **Message Content Intent**
- 将机器人邀请到你的服务器，或直接给它发私信

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: discord
chat_discord_token: YOUR_BOT_TOKEN
chat_discord_org_manager: YOUR_USER_ID  # 你的 Discord 用户 ID
```
</details>

<details>
<summary>WhatsApp</summary>

**1. 启动 WhatsApp bridge**
- MobileClaw 的 WhatsApp 客户端通过本地 Node.js WebSocket bridge 工作
- 本仓库中的 bridge 入口在 `nanobot/bridge/src/index.ts`
- 启动 bridge 后，在其终端中扫描二维码登录 WhatsApp

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: whatsapp
chat_whatsapp_bridge_url: ws://localhost:18790
chat_whatsapp_org_manager: YOUR_PHONE_OR_SENDER_ID  # 通常为不带 @ 后缀的手机号
```
</details>

<details>
<summary>Slack</summary>

**1. 创建 Slack 应用**
- 访问 [Slack API Apps](https://api.slack.com/apps)
- 创建新应用 -> 启用 **Socket Mode**
- 创建带有 `connections:write` 权限的 app-level token
- 为 bot token 配置所需消息权限
- 将应用安装到工作区，并复制两个 token

**2. 在 `config.yaml` 中配置**
```yaml
chat_channels: slack
chat_slack_bot_token: xoxb-...
chat_slack_app_token: xapp-...
chat_slack_org_manager: U01234567  # 你的 Slack 用户 ID
```
</details>

我们推荐使用 `zulip` 或 `Lark/飞书`，因为它们支持丰富的群组功能。如果你更依赖现有生态，也可以使用 `discord`、`whatsapp` 或 `slack`。

## 致谢

- [THU-AIR](https://air.tsinghua.edu.cn/en/) 团队成员。
- [Mind Lab](https://macaron.im/mindlab/) 提供支持。
- [openclaw](https://github.com/openclaw/openclaw)、[ClawPhone](https://www.clawphone.app/)、[nanobot](https://github.com/HKUDS/nanobot) 提供灵感。
- [OmniMind team](https://omnimind.com.cn/)（万象智维）提供灵感和支持。
- [zulip](https://mobilellm.zulip.com/) 和[飞书](https://www.feishu.cn/) 赞助的团队账号。
