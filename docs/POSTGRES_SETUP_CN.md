# PostgreSQL + pgvector 本地安装与初始化说明

## 1. 目标

为 AI 伴诊平台准备本地开发环境：

- PostgreSQL：存业务数据、文档元数据、父块、长期摘要
- pgvector：存子块向量
- Redis：后续用于短期记忆

当前先完成 PostgreSQL + pgvector。

## 2. 安装 PostgreSQL

推荐使用官方 Windows 安装包：

1. 打开 PostgreSQL 官方下载页
2. 选择 Windows 安装包
3. 下载并安装 PostgreSQL 16 或 17
4. 安装过程中记住以下信息：
   - 超级用户用户名，默认一般是 `postgres`
   - 你设置的数据库密码
   - 端口，默认 `5432`

建议本地开发统一使用：

- 用户名：`postgres`
- 端口：`5432`
- 数据库名：后续创建为 `ai_companion`

## 3. 安装 pgvector

`pgvector` 不是 PostgreSQL 默认自带扩展，需要额外安装。

你可以采用下面两种方式之一：

### 方式 A：系统已提供 pgvector 扩展

如果你的 PostgreSQL 环境已经包含 `vector` 扩展文件，后面直接执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

如果能执行成功，说明已经可用。

### 方式 B：单独安装 pgvector

如果执行失败，说明当前 PostgreSQL 里没有 `vector` 扩展，需要给当前 PostgreSQL 安装 pgvector。

Windows 上建议优先选这两种方式：

1. 安装带 pgvector 的 PostgreSQL 发行版
2. 或安装与当前 PostgreSQL 大版本匹配的 pgvector 二进制扩展

注意：

- pgvector 必须和你的 PostgreSQL 主版本匹配
- 例如 PostgreSQL 16 对应 PostgreSQL 16 版本的 pgvector 扩展

## 4. 创建数据库

安装完成后，打开 `SQL Shell (psql)`，按提示输入：

- Server: `localhost`
- Database: `postgres`
- Port: `5432`
- Username: `postgres`
- Password: 你安装时设置的密码

连接成功后执行：

```sql
CREATE DATABASE ai_companion;
```

然后切换到目标数据库：

```sql
\c ai_companion
```

## 5. 初始化扩展

切换到 `ai_companion` 后，先执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

如果 `vector` 失败，不要继续建表，先安装 pgvector。

## 6. 执行建表 SQL

本仓库已经准备好初始化 SQL 文件：

- [project/db/sql/init_schema.sql](D:/nageoffer/agentic-rag-for-dummies/project/db/sql/init_schema.sql:1)

你需要执行其中的全部语句。

如果你使用 `psql`，可以直接运行：

```sql
\i D:/nageoffer/agentic-rag-for-dummies/project/db/sql/init_schema.sql
```

## 7. 环境变量配置

把 [project/.env.example](D:/nageoffer/agentic-rag-for-dummies/project/.env.example:1) 复制为 `project/.env`，并补充：

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_companion
POSTGRES_USER=postgres
POSTGRES_PASSWORD=你的密码

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

## 8. 验证是否成功

在 `psql` 里运行：

```sql
\dt
```

如果能看到以下表，说明建表成功：

- `documents`
- `parent_chunks`
- `child_chunks`
- `chat_sessions`
- `chat_session_summaries`
- `departments`
- `doctors`
- `doctor_schedules`
- `appointments`
- `appointment_logs`
- `retrieval_logs`

## 9. 你接下来要做什么

完成 PostgreSQL 安装和 `vector` 扩展可用后，下一步是：

1. 执行初始化 SQL
2. 配置 `.env`
3. 我们再一起把 Python 侧数据库连接和管理器代码接上
