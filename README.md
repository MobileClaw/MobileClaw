# MobileClaw - Fully Autonomous Mobile Agent

[[中文文档](README_zh.md)] | [English]

<div align="center">
  <img src="_res/brand.png" alt="mobileclaw" width="600">
</div>

<div align="center">
  <img src="_res/mobileclaw_demo_5x.gif" alt="mobileclaw_demo" width="100%">
</div>

----

MobileClaw's mission is to enable openclaw-style agents on mobile devices (e.g. your secondary phone).

Unlike existing coding agents based on low-level system commands, third-party APIs and MCP services, MobileClaw executes tasks mostly through GUI like human, which means higher usability and reliability for everyone (including non-experts) in daily use.

**Features**:
- Natively built for mobile devices (e.g. Android).
- Human-like interaction with apps via vision/GUI.
- Lightweight design with minimal third-party service integration.
- Memory organized as .md files.
- Communication with users via daily messaging apps.

**Important Notice:** 
- To avoid security risks, please **DO NOT** use MobileClaw to control your main device.
- We strongly suggest using **seperated app accounts** on MobileClaw-controlled devices and **DO NOT** spam the Internet.

## How to Install

1. Clone this project.
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
```

## Chat App Configuration

MobileClaw supports multiple chat platforms. Configure your preferred platform in `config.yaml`:

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
chat_telegram_org_manager: YOUR_USER_ID  # Your Telegram user ID
chat_telegram_proxy: http://proxy:port  # Optional, if you need a proxy
```
</details>

<details>
<summary>Lark/Feishu</summary>

**1. Create a Lark bot**
- Visit [Feishu Open Platform](https://open.feishu.cn/app)
- Create a new app → Enable **Bot** capability
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
chat_lark_org_manager: ou_xxx  # Your Lark open_id or phone number
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

We recommend `zulip` or `Lark/Feishu` since they support rich group features.

## Acknowledgments

- [THU-AIR](https://air.tsinghua.edu.cn/en/) team members.
- [openclaw](https://github.com/openclaw/openclaw) for the inspiration.
- [nanobot](https://github.com/HKUDS/nanobot) for sample code of chat channel integration.
- [zulip](https://mobilellm.zulip.com/) and [Feishu](https://www.feishu.cn/) for sponsored team account.

