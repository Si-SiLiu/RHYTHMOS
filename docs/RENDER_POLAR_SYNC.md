# Render：Polar 自动同步服务

这是 RHYTHMOS iPhone 第一阶段的服务端部署方式。Polar AccessLink 的授权码、client secret、刷新令牌和原始数据始终留在服务端；iPhone 只使用 HTTPS 读取已验证的每日快照。没有 Polar 指标的手工录入入口。

## 部署

1. 将本仓库推送到你自己的 GitHub/GitLab 私有仓库；确认 `.env`、`data/` 和任何令牌文件都没有提交。
2. 在 Render 选择 **New + → Blueprint**，选择仓库。平台会识别根目录的 `render.yaml`。
3. 保留 `0.5c-512mb` 方案和 1 GB 持久磁盘。这是单实例设计：数据库、同步历史和加密令牌都放在挂载的 `data/` 内。不要选无持久磁盘的免费服务，否则重启后会丢失授权和同步数据。
4. Render 首次创建时填写以下密钥环境变量：

   - `POLAR_CLIENT_ID`、`POLAR_CLIENT_SECRET`：Polar AccessLink 应用凭据。
   - `POLAR_REDIRECT_URI`：部署完成后服务的完整回调地址，例如 `https://rhythmos-polar-sync.onrender.com/oauth2_callback`。
   - `POLAR_TOKEN_ENCRYPTION_KEY`：用下面的本地命令生成；只保存到 Render。
   - `MOBILE_SYNC_API_TOKEN`：用下面的本地命令生成；以后通过配对写入 iPhone Keychain，不放进 App 包或 Info.plist。
   - `POLAR_CONNECT_PASSWORD`：用于首次浏览器授权的独立密码。用户名默认为 `owner`。

   ```bash
   .venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   .venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
   ```

5. 在 Polar AccessLink 应用配置里添加与 `POLAR_REDIRECT_URI` **逐字一致**的回调地址，然后触发一次 Render 手动部署以读取该变量。
6. 浏览器打开 `https://你的服务.onrender.com/connect/polar`，按提示输入 `owner` 和 `POLAR_CONNECT_PASSWORD`，登录 Polar Flow 并授权。成功页面只会显示已连接，不会显示 token。

## 接口约定

所有移动端接口都需要 `Authorization: Bearer <MOBILE_SYNC_API_TOKEN>`，且响应禁止缓存。

| 接口 | 用途 |
| --- | --- |
| `GET /healthz` | Render 健康检查；不含账户或数据状态。 |
| `GET /v1/mobile/status` | 确认 Polar 是否已连接。 |
| `POST /v1/mobile/sync` | 服务端从 Polar 拉取、导入并计算恢复数据。 |
| `GET /v1/mobile/daily-snapshot?date=YYYY-MM-DD` | iPhone 读取 `rhythmos.mobile_daily_snapshot` v1。 |

## 自动化策略

服务端接口已具备自动拉取能力，下一步 iOS 会在启动、进入前台和后台刷新时调用同步接口，再读取快照。为了让服务端在 iPhone 没有打开时也更新，可在 Render Dashboard 创建一个每小时 Cron Job，向 `POST /v1/mobile/sync` 发送同一个 Bearer token；Cron Job 不直接访问持久磁盘，它只通过 HTTPS 触发该 Web Service。

不在 `render.yaml` 中预创建 Cron Job，是为了避免把服务 URL 或共享 token 写入仓库。创建时将同一个 `MOBILE_SYNC_API_TOKEN` 作为 Cron 环境变量，并使用类似以下命令（替换为实际公开 URL）：

```bash
curl --fail --silent --show-error --request POST \
  --header "Authorization: Bearer $MOBILE_SYNC_API_TOKEN" \
  "https://你的服务.onrender.com/v1/mobile/sync"
```

## 运行边界

- 不把 `POLAR_CLIENT_SECRET`、refresh token 或 `MOBILE_SYNC_API_TOKEN` 写入 iOS 源码、日志、快照或仓库。
- `POLAR_TOKEN_ENCRYPTION_KEY` 丢失后，旧的令牌文件无法解密；应删除该服务令牌文件并重新授权 Polar，而不是尝试绕过加密。
- 本阶段是单一所有者服务。多用户发布前，需要把共享移动 token 替换为用户账户、设备配对和服务端会话令牌。
