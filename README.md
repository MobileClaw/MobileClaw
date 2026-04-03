# MobileClaw - Fully Autonomous Mobile Agent

<div align="center">

[![中文文档](https://img.shields.io/badge/中文文档-README__zh.md-0f766e?style=flat-square)](README_zh.md)
![English](https://img.shields.io/badge/English-Current-2563eb?style=flat-square)
[![Website](https://img.shields.io/badge/Website-mobileclaw.cc-7c3aed?style=flat-square)](https://mobileclaw.cc/)
[![Android App](https://img.shields.io/badge/Android%20App-Download-16a34a?style=flat-square)](https://mobileclaw.cc/files/MobileClaw.apk)
[![X](https://img.shields.io/badge/X-@MobileClawX-111111?style=flat-square)](https://x.com/MobileClawX)
[![News](https://img.shields.io/badge/News-Latest-f59e0b?style=flat-square)](#news)

</div>

<div align="center">
  <img src="_res/brand.png" alt="mobileclaw" width="600">
</div>

<div align="center">
  <img src="_res/mobileclaw_demo_5x.gif" alt="mobileclaw_demo" width="100%">
</div>

<div align="center">

### Open, human-like mobile automation for everyone

</div>

---

MobileClaw's mission is to enable openclaw-style agents on mobile devices (e.g. your spare Android phone).

Unlike existing coding agents based on low-level system commands, third-party APIs and/or MCP services, MobileClaw executes tasks mostly through GUI like human, which means higher usability and reliability for everyone (including non-experts) in daily use.

## Highlights

- Natively built for mobile devices (e.g. Android).
- Human-like interaction with apps via vision/GUI.
- Lightweight design with minimal third-party service integration.
- Memory and skills organized as `.md` files, like other *claw*s.
- Communication with users via daily messaging apps (Telegram, Weixin, etc.).

> [!IMPORTANT]
> - To avoid security risks, please **DO NOT** use MobileClaw to control your main device.
> - We strongly suggest using **seperated app accounts** on MobileClaw-controlled devices and **DO NOT** spam the Internet.

## News

- 2026.03.27 MobileClaw app v0.3.3 released.
- 2026.03.26 Added support for Weixin chat channel.
- 2026.02.08 Project kick-off.

## Getting Started

### For users

- Download and install the [MobileClaw Android app](https://mobileclaw.cc/files/MobileClaw.apk).
- Complete the model/chat configurations.
- Click the start button and enjoy.

Visit our [project website](https://mobileclaw.cc/) for details.

### For developers

1. Clone this project into your development environment.
2. Run `cd MobileClaw` and `pip install -e .`

## How to Use

1. Set up your Android device. See [Android Device Set Up](#android-device-set-up) for details.
2. Copy `config.yaml.example` to `config.yaml` and fill in information.
   1. See [Model Configuration](#model-configuration) for how to config model providers.
   2. See [Chat App Configuration](#chat-app-configuration) for how to connect chat apps.
3. Start your agent with `mobileclaw config.yaml`.
4. Send messages to the agent or modify its `profile.md` to customize.

## Android Device Set Up

1. Connect your Android device via ADB. Enable developer mode. ([How to enable developer mode?](https://www.android.com/intl/en_uk/articles/enable-android-developer-settings/))
2. Run `adb install mobileclaw/resources/apk/MobileClaw.apk` to install the Client App to your phone.
3. Grant **Accessibility Service permission** and **Notification permission**; the WebSocket service will start automatically on the Android device.
4. In `config.yaml`, set the port for PC-side forwarding. Configure separate ports for each device in `phone_port_mappings`, like this:
   ```yaml
   phone_port_mappings:
       phone1: 51825
       phone2: 51826
   ```
5. On your computer, run `adb forward tcp:<device_port> tcp:6666` to forward the Android WebSocket service to your PC. `<device_port>` is the port you set in the config.

## Model Configuration

MobileClaw requires two models to work. One for general task control (planning, memory management, etc.). Another for computer use (GUI grounding, app-related task automation, etc.).

Each model requires three values for configuration, including `url`, `key` and `name`. They should support OpenAI-compatible APIs.

For example, the following lines in `config.yaml` set the foundation model to `gpt-5.2-chat`.

```yaml
custom_fm_url: "https://api.openai.com/v1/chat/completions"
custom_fm_key: "sk-xxx"
custom_fm_name: "gpt-5.2-chat"
tavily_api_key: "tvly-xxx"  # optional, enables Tavily web search
```

## Chat App Configuration

<div align="center">

| Platform | Status |
| --- | --- |
| `telegram` | Supported |
| `lark` | Supported |
| `qq` | Supported |
| `zulip` | Supported |
| `discord` | Supported |
| `whatsapp` | Supported |
| `slack` | Supported |
| `weixin` | Supported |

</div>

MobileClaw supports `telegram`, `lark`, `qq`, `zulip`, `discord`, `whatsapp`, `slack`, and `weixin`. Configure one or more platforms in `config.yaml` with a comma-separated `chat_channels` value:

```yaml
chat_channels: zulip,lark
default_chat_channel: zulip
```

<details>
<summary>Telegram</summary>

**1. Create a bot**
- Open Telegram, search `@BotFather`
- Send `/newbot`, follow prompts
- Copy the bot token

**2. Configure in `config.yaml`**
```yaml
chat_channels: telegram
chat_telegram_token: YOUR_BOT_TOKEN
chat_telegram_org_manager: YOUR_USER_ID  # Optional; if omitted, the first sender becomes org_manager
chat_telegram_proxy: http://proxy:port  # Optional; if you need a proxy
```
</details>

<details>
<summary>Weixin</summary>

**1. Prepare the iLink bot API**
- Make sure your Weixin bot account can access the iLink HTTP API
- If you already have a bot token, configure it directly
- If not, MobileClaw can start a QR login flow and wait for confirmation

**2. Configure in `config.yaml`**
```yaml
chat_channels: weixin
chat_weixin_base_url: YOUR_BOT_BASE_URL  # Optional; omit to use QR login
chat_weixin_bot_token: YOUR_BOT_TOKEN  # Optional; omit to use QR login
```

**3. Notes**
- Current implementation supports text message receive/reply
- If `chat_weixin_bot_token` is omitted, startup logs will print a QR Code URL (`qrcode_url=...`) for login
- The first incoming message from a user establishes the reply context for later responses
</details>

<details>
<summary>Lark/Feishu</summary>

**1. Create a Lark bot**
- Visit [Feishu Open Platform](https://open.feishu.cn/app)
- Create a new app -> Enable **Bot** capability
- Get **App ID** and **App Secret** from "Credentials & Basic Info"
- Grant following permissions to the bot:
  - im:message.group_msg
  - contact:contact.base:readonly
  - im:chat
  - im:chat:read
  - im:message
  - im:message.reactions:write_only
  - im:message:send_as_bot
  - im:resource
- Enable **Long Connection** mode (requires starting mobileclaw once with lark to establish connection)

**2. Configure in `config.yaml`**
```yaml
chat_channels: lark
chat_lark_app_id: cli_xxx
chat_lark_app_secret: xxx
chat_lark_org_manager: ou_xxx  # Optional; your Lark open_id or phone number. If omitted, the first sender becomes org_manager
```
</details>

<details>
<summary>QQ</summary>

**1. Create a QQ bot**
- Visit [QQ Open Platform](https://q.qq.com)
- Create a new bot application
- Get **AppID** and **Secret** from "Developer Settings"

**2. Configure in `config.yaml`**
```yaml
chat_channels: qq
chat_qq_app_id: YOUR_APP_ID
chat_qq_secret: YOUR_APP_SECRET
chat_qq_org_manager: YOUR_USER_OPENID  # Your QQ user openid
```
</details>

<details>
<summary>Zulip</summary>

**1. Create a Zulip bot**
- Go to your Zulip organization settings
- Create a new bot
- Copy the bot email and API key (in zuliprc file)

**2. Configure in `config.yaml`**
```yaml
chat_channels: zulip
chat_zulip_email: bot@example.zulipchat.com
chat_zulip_key: YOUR_API_KEY
chat_zulip_site: YOUR_ZULIP_ORG_URL
chat_zulip_org_manager: manager@example.com  # Org manager's zulip email. Default format: user{6-digit-zulip-id}@{org-name}.zulipchat.com
```

</details>

<details>
<summary>Discord</summary>

**1. Create a Discord bot**
- Visit the [Discord Developer Portal](https://discord.com/developers/applications)
- Create a new application -> Add a bot
- Copy the bot token
- Enable the bot intents needed for messages, especially **Message Content Intent**
- Invite the bot to your server or DM it directly

**2. Configure in `config.yaml`**
```yaml
chat_channels: discord
chat_discord_token: YOUR_BOT_TOKEN
chat_discord_org_manager: YOUR_USER_ID  # Your Discord user ID
```
</details>

<details>
<summary>WhatsApp</summary>

**1. Start the WhatsApp bridge**
- MobileClaw's WhatsApp client connects to a local Node.js WebSocket bridge
- In this repo, the bridge entry point is `nanobot/bridge/src/index.ts`
- Start the bridge and scan the QR code shown in the bridge terminal to log in

**2. Configure in `config.yaml`**
```yaml
chat_channels: whatsapp
chat_whatsapp_bridge_url: ws://localhost:18790
chat_whatsapp_org_manager: YOUR_PHONE_OR_SENDER_ID  # Usually phone number without the @suffix
```
</details>

<details>
<summary>Slack</summary>

**1. Create a Slack app**
- Visit [Slack API Apps](https://api.slack.com/apps)
- Create a new app -> Enable **Socket Mode**
- Create an app-level token with `connections:write`
- Add a bot token with the permissions your workspace needs for messaging
- Install the app to your workspace and copy both tokens

**2. Configure in `config.yaml`**
```yaml
chat_channels: slack
chat_slack_bot_token: xoxb-...
chat_slack_app_token: xapp-...
chat_slack_org_manager: U01234567  # Your Slack user ID
```
</details>

We have tested `zulip`, `Lark/Feishu`, `telegram` and `wechat` and they work well. Other channels are also available but are not well tested.

## Acknowledgments

- Incubated by [THU-AIR](https://air.tsinghua.edu.cn/en/) team.
- Powered by [Mind Lab](https://macaron.im/mindlab/).
- Inspired by [openclaw](https://github.com/openclaw/openclaw), [ClawPhone](https://www.clawphone.app/) and [nanobot](https://github.com/HKUDS/nanobot) .
- Inspired and supported by [OmniMind team](https://omnimind.com.cn/).
- Team accounts sponsored [zulip](https://mobilellm.zulip.com/) and [Feishu](https://www.feishu.cn/).
