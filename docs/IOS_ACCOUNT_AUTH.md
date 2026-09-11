# iOS 账号会话（闭测）

## 产品行为

RHYTHMOS 不向用户显示同步服务地址、共享 API 密钥或“立即同步”。iPhone 首次进入“我的”时提供两种等价的用户建立方式：

1. **RHYTHMOS 账号**：用户自选账号名和密码。密码只以带随机盐的 scrypt 哈希保存在服务端私有文档中，原文不落盘、不写日志，也不进入 iPhone 偏好设置。
2. **Apple 登录**：服务端验证 Apple 身份令牌后，直接创建或恢复相同的 RHYTHMOS 用户。Apple 的用户稳定标识只以 SHA-256 摘要作为私有身份索引。

首次选择的方式就是该用户的登录方式；当前闭测版不提供把两个已存在账号合并的入口，因此不要在同一人的两台设备上分别创建两个账号。访问令牌有效期为一小时；续期令牌只存于该 iPhone 的 Keychain，云端只保存其 SHA-256 摘要并在每次续期时轮换。

Mac 仍通过部署环境中的 `MOBILE_SYNC_API_TOKEN` 发布本机投影；该密钥不再下发到 iPhone，也不写进 App 包。

## 一次性闭测配置

1. 在 Apple Developer 的 `com.rhythmos.ios` App ID 上启用 **Sign in with Apple**，然后让 Xcode 刷新对应的 development provisioning profile。iOS entitlement 已包含此能力。
2. 在 Supabase SQL Editor 执行 [002_cloud_sync_document_types.sql](../db/supabase/002_cloud_sync_document_types.sql)。这只增加 `mobile_session` 私有文档类型，不删除历史健康数据。
3. 在 Render 设置以下环境变量：
   - `RHYTHMOS_MOBILE_SESSION_SIGNING_KEY`：至少 32 字节的随机值，例如 `python -c 'import secrets; print(secrets.token_urlsafe(48))'` 的输出；仅保存在 Render。
   - `RHYTHMOS_APPLE_AUDIENCE=com.rhythmos.ios`
   - `RHYTHMOS_OWNER_APPLE_SUB_SHA256`：见下一步。
4. Apple 登录用于当前已有 Mac/Polar 云端数据的所有者时，首次尚未设置 allowlist，可在测试 iPhone 点击“使用 Apple 登录”。应用会显示一个 64 位的“测试账号尚待管理员批准”验证码。把该验证码原样保存为 Render 的 `RHYTHMOS_OWNER_APPLE_SUB_SHA256`，再部署服务并重新点击登录。
5. 若要让现有数据所有者建立 **RHYTHMOS 账号**，在 Render 设置 `RHYTHMOS_ACCOUNT_REGISTRATION_ENABLED=true`，并设置 `RHYTHMOS_ACCOUNT_REGISTRATION_CODE_SHA256` 为一次性邀请码的 SHA-256（例如 `python -c 'import hashlib; print(hashlib.sha256(input().encode()).hexdigest())'）。只把原邀请码通过私信交给该所有者一次；原文不会上传或保存。该账号会绑定到既有 Mac/Polar 云端数据。首次成功注册后，服务端会自动封锁后续注册；同时也建议把 `RHYTHMOS_ACCOUNT_REGISTRATION_ENABLED` 改回 `false`，日后登录不受影响。

该验证码是 Apple 用户稳定标识的单向摘要，不是 Apple 邮箱、访问令牌或 Polar 凭据。邀请码的摘要同样不是原邀请码。二者都只用于闭测允许当前所有者账号访问既有 `POLAR_MEMBER_ID` 数据。范围扩大后，每个账号将拥有独立 Polar/HealthKit 连接与独立云端投影；不能把这一单一所有者绑定机制当作公开多用户注册机制。

## 服务端校验

`POST /v1/mobile/auth/apple` 校验 Apple JWT 的 ES256 签名、`iss`、`aud`、`exp` 和 nonce。`POST /v1/mobile/auth/account/register` 与 `/login` 建立 RHYTHMOS 账号会话。通过后才签发 RHYTHMOS 会话；任何同步端点仍要求 Bearer 会话或仅供 Mac 迁移期使用的既有服务令牌。Apple 身份令牌、账号密码、刷新令牌、共享令牌和 Polar 凭据均不写入日志、Supabase 投影或 iOS 偏好设置。
