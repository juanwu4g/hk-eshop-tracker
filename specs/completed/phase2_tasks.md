# Phase 2 Tasks - ✅ 已完成

## Task 1: Supabase数据库创建 ✅

- [x] 注册Supabase，用GitHub账号登录
- [x] 创建项目 `hk-eshop-tracker`
- [x] 区域选择：Northeast Asia (Tokyo)
- [x] 关闭Data API（不需要REST接口，直接用连接字符串）
- [x] 关闭Automatic RLS（单用户脚本，不需要权限控制）
- [x] 获取连接字符串：使用Transaction Pooler模式（IPv4，端口6543）
  - 原因：Supabase新项目默认IPv6，很多环境不支持，Pooler走IPv4代理

## Task 2: database.py改造（SQLite → PostgreSQL双模式）✅

- [x] requirements.txt 添加 `psycopg2-binary`
- [x] 重写 src/database.py：
  - 从环境变量 `DATABASE_URL` 读取连接字符串
  - 有 DATABASE_URL → 用 psycopg2 连 PostgreSQL
  - 无 DATABASE_URL → 回退 SQLite（本地开发用）
  - SQL语法适配：
    - `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
    - `INSERT OR REPLACE` → `INSERT ... ON CONFLICT (eshop_id) DO UPDATE SET ...`
    - 参数占位符 `?` → `%s`
    - 时间戳 `CURRENT_TIMESTAMP` → `NOW()`
  - 所有函数接口不变（init_db, upsert_game, insert_price, get_latest_price等）

**验证**: 不设DATABASE_URL，`python scripts/run_scan.py --pages 1` SQLite回退正常 ✅

## Task 3: 数据迁移 ✅

- [x] 创建 scripts/migrate_to_supabase.py
- [x] 读取本地 data/eshop.db 所有数据
- [x] 写入 Supabase PostgreSQL
- [x] 处理重复数据（已存在则跳过）
- [x] 迁移结果：games 1237条，price_history 完整迁移

**验证**: Supabase Table Editor中确认数据正确 ✅

## Task 4: GitHub Actions配置 ✅

- [x] 创建 `.github/workflows/daily_scan.yml`
  - 触发：cron `0 1 * * *` (UTC 01:00 = HKT 09:00) + workflow_dispatch手动触发
  - 步骤：checkout → Python 3.11 → pip install → playwright install chromium --with-deps → run_scan.py
  - 环境变量：DATABASE_URL from GitHub Secrets
  - timeout: 15分钟
- [x] 创建 `.github/workflows/sale_monitor.yml`
  - 触发：cron `0 */6 * * *` (每6小时) + workflow_dispatch
  - 步骤：同上，运行 run_sale_monitor.py
  - timeout: 15分钟
- [x] 配置GitHub Secret: DATABASE_URL（Supabase Pooler连接字符串）

**验证**: 手动触发Daily Scan，成功完成，数据写入Supabase ✅
**注意**: GitHub Actions已验证能通过AWS WAF（GitHub IP未被封）

## Task 5: 减价页监控脚本 ✅

- [x] 创建 scripts/run_sale_monitor.py
  - 复用 src/browser.py 和 src/scraper.py
  - 只爬 `/download-code/sale` 一个页面
  - 与数据库最近价格对比
  - 新折扣/折扣结束写入 price_alerts

## Task 6: 错误处理增强 ✅

- [x] 扫描结果 < 100个游戏时打印警告
- [x] 数据库连接正确关闭

## Task 7: 代码推送到GitHub ✅

- [x] 创建GitHub仓库: https://github.com/juanwu4g/hk-eshop-tracker
- [x] .gitignore: venv/, data/eshop.db, __pycache__/, *.pyc
- [x] 使用Personal Access Token认证推送
- [x] 代码推送成功
