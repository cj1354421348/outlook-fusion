# 📧 Outlook Fusion

Outlook 邮箱账户全生命周期管理系统：**OAuth 授权拿 token → 自动续期保活 → 健康检查 → 邮件读取**（IMAP/Graph 双协议）。数据以 PostgreSQL 为主源，单实例部署。

> 融合重写自 MS-Graph-Token-Generator（项目 A）+ OutlookManager（项目 B）。**不含发送邮件（SMTP）功能。**

## ✨ 功能

| 模块 | 说明 |
|------|------|
| 账户管理 | 单个注册 / 批量导入（`邮箱----密码----client_id----令牌`）/ 状态管理 / 删除 |
| Token 保活 | 每日自动刷新（`REFRESH_INTERVAL_HOURS` 可配，上限 7 天）；失败阈值自动标记 `expired` |
| 协议探测 | 自动识别 GRAPH vs IMAP（scope 探测），IMAP 双 host 回退（office365 → live） |
| 邮件读取 | 列表 / 详情 / 搜索 / 双视图 / CSV 导出（无发送链路） |
| 通知 | webhook 推送（沿用项目 A 的 Notify Hub 协议） |
| 安全 | 登录会话（内存 TTL）+ 登录限流锁定 + API key（只存 SHA256 哈希）+ CORS 白名单 |
| Web UI | server-rendered 登录页 + 控制台（账户/批量导入/邮件查看） |

## 🚀 快速开始

### 环境要求
- Python ≥ 3.12（建议 3.13）
- PostgreSQL（本机或 Aiven 云，本项目连接串示例为 Aiven）

### 1. 安装

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置 `.env`（参考 `.env.example`）

| 变量 | 必填 | 说明 |
|------|------|------|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@host:5432/db?ssl=require` |
| `SECRET_KEY` | ✅ | cookie 签名：`python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `TOKEN_ENCRYPTION_KEY` | ✅ | Fernet key：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`，**必须备份** |
| `APP_USERNAME` / `APP_PASSWORD` | 可选 | Web 登录凭据（默认 admin/admin） |

### 3. 迁移 + 启动

```powershell
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

访问 `http://localhost:8000`（自动跳转登录页）。

## 🔌 API 一览

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/auth/login` | 无 | 登录（设置 cookie） |
| POST | `/api/auth/logout` | cookie | 登出 |
| GET/POST | `/api/accounts` | 需认证 | 账户列表 / 注册 |
| POST | `/api/accounts/batch` | 需认证 | 批量导入 |
| DELETE | `/api/accounts/{email}` | 需认证 | 删除账户 |
| PUT | `/api/accounts/{email}/status` | 需认证 | 状态管理 |
| GET | `/api/accounts/_health` | 需认证 | Token 健康摘要 |
| POST | `/api/tokens/{email}/refresh` | 需认证 | 单账户刷新 |
| POST | `/api/tokens/refresh-all` | 需认证 | 全量刷新 + 通知 |
| GET | `/api/emails/{email}` | 需认证 | 邮件列表 |
| GET | `/api/emails/{email}/{id}` | 需认证 | 邮件详情 |
| GET | `/api/emails/{email}/search` | 需认证 | 搜索 |
| GET | `/api/emails/{email}/export.csv` | 需认证 | CSV 导出 |
| GET | `/api/admin/security/status` | cookie | 安全状态 |

> **需认证** = 登录会话 cookie 或 `X-API-Key` 头（API key 在 `/api/admin/api-key/rotate` 生成）。

## 🐳 Docker 部署

```bash
cd deploy
docker compose up -d
```

- 使用 Aiven PG：注释掉 `postgres` 服务，`DATABASE_URL` 指向 Aiven。
- HTTPS：配置 `Caddyfile` 域名 + 更新 `AZURE_SETUP.md` 的 redirect URI。

## ⚠️ 硬性约束

- **单 worker**：`uvicorn --workers 1`（main.py 已断言），内存缓存/会话/IMAP 池依赖单进程。
- **token 加密**：refresh_token 一律 Fernet 加密入库，`TOKEN_ENCRYPTION_KEY` 丢失则全部不可恢复。
- **API key 只存哈希**：生成时明文仅展示一次。

## 📄 文档

- [Azure 应用配置清单](deploy/AZURE_SETUP.md)
- [完整开发计划](.omo/plans/outlook-fusion-plan.md)

## 📦 旧项目状态

- `../MS-Graph-Token-Generator`（项目 A）— 已归档
- `../OutlookManager`（项目 B）— 已归档
