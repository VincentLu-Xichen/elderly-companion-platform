# Vercel + Supabase 部署手册

本方案使用 Vercel 托管 FastAPI，Supabase 只提供 PostgreSQL。浏览器仍只访问 FastAPI，不能直接访问 Supabase 或 Azure OpenAI。

## 1. 部署结构

```text
学生或管理员浏览器
    -> Vercel FastAPI
       -> Supabase PostgreSQL
       -> Azure OpenAI
```

消息、语境快照、Trace 和错误详情继续由应用使用 AES-GCM 加密后写入数据库。不要在前端加入 Supabase anon key，也不需要启用 Supabase Auth。

## 2. 上传 GitHub 前检查

建议使用 GitHub 私有仓库。确认 `.env`、数据库、Vercel 本地配置和真实密钥没有被 Git 跟踪：

```bash
git status --short
git ls-files | rg '(^|/)\.env$|\.(db|sqlite|sqlite3)$|^\.vercel/'
```

如果第二条命令有输出，先停止上传并移除对应敏感文件。不要提交真实的 Azure key、Supabase 密码、`APP_SECRET`、`DATA_ENCRYPTION_KEY`、管理员密码或邀请码。

创建空的 GitHub 私有仓库后执行：

```bash
git remote add origin https://github.com/<owner>/<repository>.git
git push -u origin main
```

如果已经存在 remote，先使用 `git remote -v` 核对，不要重复添加。

## 3. 创建 Supabase 数据库

创建 Supabase 项目时，选择尽量靠近 Vercel Function 和 Azure OpenAI 的区域。在 Supabase Dashboard 的 **Connect** 页面取得两条连接：

- Direct Connection：仅用于 Alembic migration；如果本地没有 IPv6，可使用 Session Pooler 端口 `5432`。
- Transaction Pooler：Vercel 运行时使用端口 `6543`。

Supabase 显示的协议通常是 `postgresql://`。本项目使用 psycopg 3，必须改成 `postgresql+psycopg://`。密码中的保留字符需要 URL 编码，并保留 TLS 参数：

```dotenv
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<encoded-password>@<region>.pooler.supabase.com:6543/postgres?sslmode=require
DATABASE_POOL_MODE=transaction
```

生产库首次部署或 migration 更新时，从仓库根目录使用迁移连接执行：

```bash
DATABASE_URL='<direct-or-session-migration-url>' \
DATABASE_POOL_MODE=application \
INVITE_CODES='<anonymous-label>:<invite-code>' \
.venv/bin/python -m scripts.bootstrap_database
```

该命令先运行现有 Alembic migrations，再以 Argon2 哈希写入或更新邀请码。不要在 Vercel Build Command 或应用冷启动中执行它。

## 4. 配置 Vercel

在 Vercel 导入 GitHub 仓库：

- Framework Preset：FastAPI，通常可自动识别。
- Root Directory：仓库根目录。
- Build Command：留空。
- Output Directory：留空。
- Function Region：选择离 Supabase 项目最近的单一区域。

根目录的 `app.py` 是 Vercel ASGI 入口，`vercel.json` 将单次 Function 最长执行时间设置为 90 秒。Vercel 会自动设置 `VERCEL=1`，应用因此不会在冷启动时建表或初始化邀请码。

在 Vercel 的 Production 环境配置：

```dotenv
APP_ENV=production
COOKIE_SECURE=true
DATABASE_POOL_MODE=transaction
# Supabase Vercel Integration 会自动注入 POSTGRES_URL；手工配置时也可使用：
DATABASE_URL=postgresql+psycopg://...:6543/postgres?sslmode=require

APP_SECRET=<long-random-secret>
DATA_ENCRYPTION_KEY=<urlsafe-base64-encoded-32-byte-key>
INVITE_CODES=<anonymous-label>:<invite-code>
ADMIN_PASSWORD=<strong-admin-password>
CONSENT_VERSION=2026-07-v1
CBT_COURSE_AGENT_VERSION=course-v1
DAILY_CHAT_AGENT_VERSION=daily-chat-v1
SESSION_HOURS=12
MAX_MESSAGE_CHARS=2000
RATE_LIMIT_PER_MINUTE=30

AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_DEPLOYMENT=<deployment>
# 可选；不设置时课程复用上面的 deployment
AZURE_OPENAI_COURSE_DEPLOYMENT=<course-deployment>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

可使用以下命令生成两个独立密钥：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

第二个输出用于 `DATA_ENCRYPTION_KEY`。该密钥丢失后，数据库中的加密研究记录无法恢复；更换它之前必须先迁移已有密文。请进行离线备份。

不要让 Preview Deployment 连接正式数据库。需要 Preview 时，应使用独立 Supabase 项目及独立加密密钥。

## 5. 验收

部署完成后检查：

```bash
curl -f https://<deployment-domain>/healthz
```

然后完整验证邀请码登录、同意告知、Daily Chat、CBT 语境确认、模型回复、刷新恢复、管理员查看、JSON/CSV 导出和删除。

本地回归命令：

```bash
.venv/bin/python -m unittest discover tests -v
.venv/bin/python -m compileall -q daily_agent cbt_course webapp tests
node --check webapp/static/app.js
```

更新数据库模型时必须新增 Alembic migration；先执行一次数据库 bootstrap/migration，再发布依赖新字段的 Vercel 版本。。
