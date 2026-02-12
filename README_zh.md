# MobileClaw - 全自主移动智能体

[[English](README.md)] | [中文文档]

<div align="center">
  <img src="_res/brand.png" alt="mobileclaw" width="600">
</div>

<div align="center">
  <img src="_res/mobileclaw_demo_5x.gif" alt="mobileclaw_demo" width="100%">
</div>

----

MobileClaw 的使命是在移动设备（例如你的备用手机）上实现类似 openclaw 的智能体能力。

与基于底层系统命令、第三方 API 和 MCP 服务的现有编程智能体不同，MobileClaw 主要通过类似人类的 GUI 交互方式执行任务，这意味着对所有人（包括非专业人士）在日常使用中具有更高的可用性和可靠性。

**核心特性**：
- 专为移动设备（如 Android）原生构建。
- 通过视觉/GUI 实现类人交互。
- 轻量化设计，最小化第三方服务集成。
- 使用 .md 文件组织记忆。
- 通过日常消息应用与用户沟通。

**重要提示：** 
- 为避免安全风险，请**不要**使用 MobileClaw 控制你的主力设备。
- 我们强烈建议在 MobileClaw 控制的设备上使用**独立的应用账号**，且**不要**滥用互联网服务。

## 安装方法

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
```

## 聊天应用配置

MobileClaw 支持多个聊天平台。在 `config.yaml` 中配置你偏好的平台：

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
chat_telegram_org_manager: YOUR_USER_ID  # 你的 Telegram 用户 ID
chat_telegram_proxy: http://proxy:port  # 可选，如果需要代理
```
</details>

<details>
<summary>Lark/飞书</summary>

**1. 创建飞书机器人**
- 访问[飞书开放平台](https://open.feishu.cn/app)
- 创建新应用 → 启用**机器人**能力
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
chat_lark_org_manager: ou_xxx  # 你的飞书 open_id 或手机号
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

我们推荐使用 `zulip` 或 `Lark/飞书`，因为它们支持丰富的群组功能。

## 致谢

- [THU-AIR](https://air.tsinghua.edu.cn/en/) 团队成员。
- [openclaw](https://github.com/openclaw/openclaw) 提供的灵感。
- [nanobot](https://github.com/HKUDS/nanobot) 提供的聊天频道集成示例代码。
- [zulip](https://mobilellm.zulip.com/) 和[飞书](https://www.feishu.cn/) 赞助的团队账号。
