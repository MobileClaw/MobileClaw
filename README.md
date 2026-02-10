# MobileClaw

MobileClaw is a **Fully Autonomous Mobile Agent**.

Our mission is to create low-barrier openclaw-style agents for everyone in daily use, not just for programmers!

Features:
- Natively built for mobile devices (e.g. Android).
- Human-like interaction with apps via vision/GUI.
- Memory organized as .md files.
- Communication with users via daily messaging apps.

## How to Install

1. Clone this project.
2. Run `cd MobileClaw` and `pip install -e .`

## How to Use

1. Connect your Android device via ADB.
2. Copy `config.yaml.example` to `config.yaml` and fill in information.
   1. See [Chat App Configuration](#chat-app-configuration) for how to connect chat apps.
3. Start your agent with `mobileclaw config.yaml`.
4. Send message to the agent or modify its `profile.md` to customize.

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

