# Azure 应用设置核对清单

> Outlook Fusion 支持 per-account client_id（token 与 client_id 绑定，不能跨应用互换）。
> 每个要用于 OAuth 授权/保活的 Azure 应用都必须在 [Azure 门户](https://portal.azure.com) 完成以下配置。

## 已知 client_id（来自旧项目，参考）

| client_id | 用途 | 状态 |
|-----------|------|------|
| `dbc8e03a...` | 旧 OutlookManager 使用 | 待核对 |
| `64add95f...` | 旧 OutlookManager 使用 | 待核对 |
| `9e5f94bc...` | 旧 OutlookManager 使用 | 待核对 |

> ⚠️ 完整 client_id 在旧项目 `data/accounts.json` 中。批量导入时使用卡密里自带的 client_id。

## 每个应用的必配项

### 1. 认证（Authentication）

| 项 | 值 |
|----|----|
| 平台 | Web |
| **重定向 URI** | `${REDIRECT_BASE_URL}/auth/callback`（如 `https://your-domain.com/auth/callback`） |
| 支持账户类型 | 个人 Microsoft 账户（消费级）/ 视账户域而定 |
| 允许公共客户端流 | ✅ 启用（`allowPublicClient`） |
| 隐式授权 | ❌ 不需要（使用授权码 + PKCE） |

### 2. API 权限（API permissions）

授权码流需要，两种协议 scope 选其一（或都配）：

| 协议 | 委托权限 |
|------|----------|
| IMAP | `https://outlook.office.com/IMAP.AccessAsUser.All` |
| Graph | `https://graph.microsoft.com/Mail.Read` |

对应 scope 字符串（config.py）：

```
GRAPH_SCOPE = https://graph.microsoft.com/.default offline_access
IMAP_SCOPE  = https://outlook.office.com/IMAP.AccessAsUser.All offline_access
```

### 3. 证书与机密（Certificates & secrets）

- **公共客户端**（无 secret）：refresh_token 可长期有效（消费级账户）。
- 若应用被标记为机密客户端：需配置 client_secret，并在刷新时带上（本项目未实现 secret 支持，纯公共客户端模式）。

## 注意事项

1. **redirect URI 变更**：隧道 URL 变化时，必须同步更新每个 client_id 的 Azure redirect URI，否则授权失败。
2. **权限漂移检查**：token 刷新失败（400/401）时，先在 Azure 核对权限是否被移除。
3. **多 client_id 并存**：每个账户用自己的 client_id 刷新，互不干扰（本项目已按 per-account client_id 实现）。
