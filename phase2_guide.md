# Phase 2 部署指南

## 第一步：注册 Supabase 并创建数据库 ✅ 已完成

连接字符串格式：
```
postgresql://postgres:[YOUR-PASSWORD]@db.vcjihkjianymkgkjclyd.supabase.co:5432/postgres
```
把 `[YOUR-PASSWORD]` 替换成你的真实密码。

## 第二步：配置 GitHub Secrets

1. 打开 https://github.com/juanwu4g/hk-eshop-tracker/settings/secrets/actions
2. 点 "New repository secret"
3. Name: `DATABASE_URL`
4. Value: 你的完整连接字符串（含真实密码）
5. 点 "Add secret"

## 第三步：让 Claude Code 改造代码

把下面这整段 prompt 复制给 Claude Code：

---

请阅读项目中 specs/ 目录下的文件了解项目背景，然后执行以下改造：

## 任务：将项目从 SQLite 迁移到 PostgreSQL (Supabase)，并添加 GitHub Actions 自动化

### 1. 数据库迁移：SQLite → PostgreSQL

修改 requirements.txt，添加 psycopg2-binary。

重写 src/database.py：
- 从环境变量 DATABASE_URL 读取连接字符串
- 如果 DATABASE_URL 不存在，回退到本地 SQLite（本地开发用）
- 用 psycopg2 连接 PostgreSQL
- 修改 SQL 语法差异：
  - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
  - INSERT OR REPLACE → INSERT ... ON CONFLICT (eshop_id) DO UPDATE SET ...
  - 参数占位符从 ? 改为 %s
- 保持所有函数接口不变（init_db, upsert_game, insert_price, get_latest_price 等）
- init_db() 用 CREATE TABLE IF NOT EXISTS
- 确保数据库连接在使用后正确关闭

保留 SQLite 回退能力，判断逻辑：
```python
import os
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # 用 psycopg2 连 PostgreSQL
else:
    # 用 sqlite3（原来的逻辑）
```

表结构（三张表）：

games 表：
- id SERIAL PRIMARY KEY
- eshop_id TEXT UNIQUE NOT NULL
- name TEXT NOT NULL
- url TEXT NOT NULL
- image_url TEXT
- magento_product_id TEXT
- first_seen_at TIMESTAMP DEFAULT NOW()
- updated_at TIMESTAMP DEFAULT NOW()

price_history 表：
- id SERIAL PRIMARY KEY
- game_id INTEGER NOT NULL REFERENCES games(id)
- current_price REAL NOT NULL
- original_price REAL
- discount_percent INTEGER
- scanned_at TIMESTAMP DEFAULT NOW()

price_alerts 表：
- id SERIAL PRIMARY KEY
- game_id INTEGER NOT NULL REFERENCES games(id)
- alert_type TEXT NOT NULL
- old_price REAL
- new_price REAL
- created_at TIMESTAMP DEFAULT NOW()

索引：
- idx_games_eshop_id ON games(eshop_id)
- idx_price_history_game ON price_history(game_id, scanned_at DESC)
- idx_alerts_created ON price_alerts(created_at DESC)

### 2. 数据迁移脚本

创建 scripts/migrate_to_supabase.py：
- 读取本地 data/eshop.db 中所有数据
- 写入 PostgreSQL（通过 DATABASE_URL 环境变量）
- 迁移 games 表和 price_history 表的所有记录
- 处理重复数据（已存在则跳过）
- 打印迁移统计

### 3. GitHub Actions 工作流

创建 .github/workflows/daily_scan.yml：

```yaml
name: Daily Price Scan

on:
  schedule:
    - cron: '0 1 * * *'  # UTC 01:00 = HKT 09:00
  workflow_dispatch:  # 支持手动触发

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium --with-deps
      
      - name: Run daily scan
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python scripts/run_scan.py
```

创建 .github/workflows/sale_monitor.yml：

```yaml
name: Sale Monitor

on:
  schedule:
    - cron: '0 */6 * * *'  # 每6小时
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium --with-deps
      
      - name: Run sale monitor
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python scripts/run_sale_monitor.py
```

### 4. 减价页监控脚本

创建 scripts/run_sale_monitor.py：
- 复用 src/browser.py 和 src/scraper.py
- 只爬取 https://store.nintendo.com.hk/download-code/sale 这一个页面
- 提取当前所有折扣商品
- 与数据库中最近的价格记录对比
- 发现新折扣或折扣结束时写入 price_alerts 表
- 打印结果摘要

### 5. 错误处理增强

修改 scripts/run_scan.py：
- 扫描结果异常少（< 100个游戏）时打印警告："⚠️ 警告：本次只扫描到 X 个游戏，可能是网站结构变化或被封，请手动检查"
- 确保数据库连接正确关闭

### 验证

每完成一部分先验证：
1. database.py 改好后：不设 DATABASE_URL，运行 python scripts/run_scan.py --pages 1，确认 SQLite 回退正常
2. 全部完成后，列出需要我手动执行的步骤

---

## 第四步：运行数据迁移（Claude Code 完成后）

在本地终端把已有的1231条数据迁移到 Supabase：

```bash
cd ~/hk_eshop_tracker_p1
export DATABASE_URL="postgresql://postgres:你的密码@db.vcjihkjianymkgkjclyd.supabase.co:5432/postgres"
pip install psycopg2-binary
python scripts/migrate_to_supabase.py
```

## 第五步：Push 代码并测试 GitHub Actions

```bash
cd ~/hk_eshop_tracker_p1
git add .
git commit -m "Phase 2: PostgreSQL + GitHub Actions"
git push
```

去 GitHub 仓库页面：
1. 点 "Actions" 标签
2. 选 "Daily Price Scan"
3. 点 "Run workflow" → "Run workflow" 手动触发
4. 等几分钟看是否成功（绿色 ✓）

## 第六步：验证数据

去 Supabase Dashboard（https://supabase.com/dashboard）：
1. 进入你的项目
2. 左边菜单点 "Table Editor"
3. 查看 games 表是否有数据
4. 查看 price_history 表是否有新记录

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| GitHub Actions playwright 报错 | chromium 依赖没装 | 确认有 `playwright install chromium --with-deps` |
| 数据库连接失败 | 连接字符串或密码错误 | 检查 DATABASE_URL secret |
| 扫描结果为0 | WAF拦截了GitHub的IP | 可能需要加 playwright-stealth 插件 |
| migrate 脚本报错 | 本地没有 eshop.db | 先在本地跑一次 run_scan.py 生成数据 |
