# 认证设计

## 目标

本阶段实现产品级最小认证能力：

- 账号密码注册
- 账号密码登录
- GitHub OAuth 登录
- 本地 SQLite 用户表
- 服务端 session
- 登录后访问 dashboard 和研究记录

## 账号密码

用户表为 `users`：

- `email`：唯一
- `username`：唯一
- `password_hash`：使用 Argon2 哈希
- `is_active`：账号状态

明文密码不会落库。

## Session

登录成功后：

1. 后端生成随机 session token。
2. SQLite `user_sessions` 表只保存 token 的 SHA-256 哈希。
3. 浏览器只保存 `HttpOnly` cookie。
4. `/api/auth/me` 返回用户信息和 CSRF token。

这样前端 JavaScript 无法直接读取登录 cookie，降低 XSS 后的凭据泄漏风险。

## CSRF

需要登录且会修改数据的接口要求 `X-CSRF-Token`：

- `POST /api/auth/logout`
- `POST /api/research/projects`

CSRF token 保存在服务端 session 表中，并通过 `/api/auth/me` 或登录响应返回给前端。

## GitHub OAuth

GitHub 登录流程：

1. 前端跳转 `/api/auth/github/login`。
2. 后端重定向到 GitHub 授权页。
3. GitHub callback 返回后，后端读取 GitHub 用户与邮箱。
4. 若本地已有同邮箱用户，则绑定 OAuth account。
5. 若没有本地用户，则创建本地用户。
6. 后端创建本地 session，并跳转回前端 `/dashboard`。

需要配置：

```env
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
BACKEND_BASE_URL=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:5173
```

GitHub OAuth App callback URL：

```text
http://localhost:8000/api/auth/github/callback
```
