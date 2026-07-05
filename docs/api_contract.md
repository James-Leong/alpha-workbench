# API 契约

默认后端地址：`http://localhost:8000`

## Health

### `GET /api/health`

返回：

```json
{
  "status": "ok",
  "app": "AlphaWorkbench"
}
```

## Auth

### `POST /api/auth/register`

请求：

```json
{
  "email": "researcher@example.com",
  "username": "researcher",
  "password": "strong-password"
}
```

返回 `UserRead`，并设置 HttpOnly session cookie。

### `POST /api/auth/login`

请求：

```json
{
  "email": "researcher@example.com",
  "password": "strong-password"
}
```

返回 `UserRead`，并设置 HttpOnly session cookie。

### `GET /api/auth/me`

返回当前登录用户：

```json
{
  "id": 1,
  "email": "researcher@example.com",
  "username": "researcher",
  "csrf_token": "..."
}
```

### `POST /api/auth/logout`

Header：

```text
X-CSRF-Token: ...
```

返回 `204 No Content`。

### `GET /api/auth/github/login`

跳转到 GitHub OAuth 授权页。

### `GET /api/auth/github/callback`

GitHub OAuth callback。成功后创建本地 session 并跳转前端 `/dashboard`。

## Research

### `GET /api/research/projects`

返回当前用户的研究项目列表。

### `POST /api/research/projects`

Header：

```text
X-CSRF-Token: ...
```

请求：

```json
{
  "title": "盈利超预期因子研究",
  "input_text": "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"
}
```

行为：

- 创建研究项目
- 调用当前 mock workflow
- 保存 run、trace 和报告
- 返回研究详情

### `GET /api/research/projects/{project_id}`

返回研究详情，包括：

- 项目基础信息
- 最新运行 ID
- 报告 Markdown
- 指标摘要
- 完整 trace JSON
