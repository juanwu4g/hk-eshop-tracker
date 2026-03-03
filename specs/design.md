# HK eShop Price Tracker - Technical Design

## 技术栈

| 组件 | 技术 | 理由 |
|------|------|------|
| 爬虫 | Python + Playwright | 唯一能通过AWS WAF challenge的方案 |
| 数据库（生产） | PostgreSQL (Supabase) | 云端持久化，GitHub Actions可访问 |
| 数据库（本地） | SQLite | 本地开发回退，零配置 |
| 定时调度 | GitHub Actions | 免费，无需服务器 |
| AI Agent | LangChain + Claude API | 单Agent多Tool，学习框架模式 |
| LLM | Claude (Anthropic SDK) | 已有API key |
| 语言 | Python 3.11 | Playwright官方支持好 |

## 项目结构

```
hk-eshop-tracker/
├── requirements.txt                # playwright, psycopg2-binary, langchain, anthropic
├── .github/
│   └── workflows/
│       ├── daily_scan.yml          # 每日全量扫描 (UTC 01:00)
│       └── sale_monitor.yml        # 每6小时减价监控
├── src/
│   ├── config.py                   # URL模板、延迟参数、数据库路径
│   ├── browser.py                  # Playwright浏览器管理（WAF处理）
│   ├── scraper.py                  # 列表页爬虫逻辑
│   ├── database.py                 # 数据库操作（PostgreSQL + SQLite双模式）
│   ├── price_tracker.py            # 价格变动检测
│   └── agent/
│       ├── __init__.py
│       ├── tools.py                # Agent的Tool定义（查数据库、搜评分）
│       └── agent.py                # LangChain Agent配置和运行
├── scripts/
│   ├── run_scan.py                 # 每日全量扫描入口
│   ├── run_sale_monitor.py         # 减价页监控入口
│   ├── run_agent.py                # Agent命令行交互入口
│   └── migrate_to_supabase.py      # SQLite → Supabase一次性迁移
├── data/
│   └── eshop.db                    # 本地SQLite数据库（gitignore）
└── specs/
    ├── requirements.md
    ├── design.md
    ├── tasks.md                    # 当前Phase的任务
    └── completed/                  # 已完成Phase的任务归档
```

## 数据库

### 连接方式

```python
import os
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # PostgreSQL via psycopg2
else:
    # SQLite fallback (data/eshop.db)
```

生产环境（GitHub Actions）：通过 Secrets 注入 DATABASE_URL
本地开发：不设环境变量，自动用SQLite

### Supabase 配置

- 项目区域：Northeast Asia (Tokyo)
- 连接方式：Transaction Pooler（IPv4，端口6543）
- Data API：已关闭（不需要，直接用连接字符串）
- RLS：已关闭（单用户脚本，不需要权限控制）

### Schema

#### games 表

```sql
CREATE TABLE games (
    id SERIAL PRIMARY KEY,
    eshop_id TEXT UNIQUE NOT NULL,        -- URL中的ID，如 '70010000065203'
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    image_url TEXT,
    magento_product_id TEXT,              -- 从 'product-id-32240' 提取 '32240'
    first_seen_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_games_eshop_id ON games(eshop_id);
```

#### price_history 表

```sql
CREATE TABLE price_history (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id),
    current_price REAL NOT NULL,
    original_price REAL,                  -- 无折扣时为NULL
    discount_percent INTEGER,             -- 计算得出
    scanned_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_price_history_game ON price_history(game_id, scanned_at DESC);
```

#### price_alerts 表

```sql
CREATE TABLE price_alerts (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id),
    alert_type TEXT NOT NULL,             -- 'new_sale' | 'sale_ended' | 'price_drop' | 'price_increase'
    old_price REAL,
    new_price REAL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_alerts_created ON price_alerts(created_at DESC);
```

## 模块设计

### browser.py

管理Playwright浏览器生命周期，处理WAF challenge。

- `create_browser(headless)` → browser, page
- `navigate(page, url)` → bool：goto + wait_for_selector('.products-grid')，超时重试一次
- `wait_between_pages()` → random sleep 3-5秒

### scraper.py

从页面提取商品数据。

- `scrape_page(page)` → list[dict]：用 page.evaluate() 执行已验证的CSS选择器
- `scrape_all_pages(page)` → list[dict]：自动翻页，商品数 < 48 时停止

### database.py

双模式数据库操作（PostgreSQL / SQLite）。

- `init_db()` → 创建表
- `upsert_game(game_data)` → game_id：INSERT ON CONFLICT UPDATE
- `insert_price(game_id, price, original_price)` → None：同一天同一价格不重复
- `get_latest_price(game_id)` → dict or None

### price_tracker.py

价格变动检测。

- `detect_changes(game_id, new_price, new_original)` → list[alert]
  - 无折扣→有折扣：new_sale
  - 有折扣→无折扣：sale_ended
  - 价格降低：price_drop
  - 价格升高：price_increase
- `save_alerts(alerts)` → 写入price_alerts表

## GitHub Actions

### daily_scan.yml
- 触发：cron `0 1 * * *` (UTC 01:00 = HKT 09:00) + 手动
- timeout：15分钟
- 步骤：checkout → Python 3.11 → pip install → playwright install chromium --with-deps → run_scan.py
- 环境变量：DATABASE_URL from secrets

### sale_monitor.yml
- 触发：cron `0 */6 * * *` (每6小时) + 手动
- timeout：15分钟
- 步骤：同上，运行 run_sale_monitor.py

## AI Agent (Phase 3)

### 架构

```
用户输入（命令行）
    ↓
scripts/run_agent.py（交互循环）
    ↓
src/agent/agent.py（LangChain Agent）
    ├── Tool: search_games(query)        → 模糊搜索数据库中的游戏
    ├── Tool: get_price_history(game_id)  → 获取价格历史记录
    ├── Tool: get_current_deals()         → 获取当前所有折扣商品
    └── Tool: search_metacritic(game_name)→ web搜索获取Metacritic评分
    ↓
综合回答
```

### 依赖

```
langchain
langchain-anthropic
langchain-community
```

### src/agent/tools.py

定义4个Tool，供LangChain Agent调用：

```
search_games(query: str) → str
    - 用 ILIKE 模糊匹配游戏名称
    - 返回匹配的游戏列表（名称、当前价格、是否打折）
    - 查数据库，复用 database.py 的连接

get_price_history(game_id: int) → str
    - 查询该游戏所有价格记录
    - 计算历史最低价、平均价、打折次数
    - 返回格式化的价格历史文本

get_current_deals() → str
    - 查询所有 original_price IS NOT NULL 的最新记录
    - 按 discount_percent 降序排列
    - 返回折扣列表

search_metacritic(game_name: str) → str
    - 用 web search 搜索 "metacritic {game_name} switch score"
    - 提取评分信息
    - 返回评分文本
    - 注意：此Tool需要网络访问，可以用 langchain 内置的搜索工具
      或简单用 requests 抓搜索结果
```

关键设计原则（之前讨论过）：
- 一个Tool = 一个动作，可用一句话描述
- 每个Agent 5-10个Tool是最优范围，我们4个刚好
- Tool的description要写清楚，让LLM知道什么时候该用哪个

### src/agent/agent.py

```
create_agent() → AgentExecutor
    - 初始化 ChatAnthropic（Claude）
    - 注册4个Tools
    - 设置系统提示（角色：HK eShop折扣分析师）
    - 返回可调用的AgentExecutor

系统提示要点：
    - 你是香港Nintendo eShop的折扣分析师
    - 你可以查询游戏价格历史、当前折扣、Metacritic评分
    - 回答时结合价格数据和游戏质量给出推荐
    - 用中文回答
    - 价格单位是HKD
```

### scripts/run_agent.py

命令行交互入口：

```
1. 从环境变量读取 ANTHROPIC_API_KEY
2. 从环境变量读取 DATABASE_URL（可选，无则用SQLite）
3. create_agent()
4. 进入交互循环：
   while True:
       user_input = input("你想了解什么？> ")
       if user_input in ('quit', 'exit', 'q'):
           break
       response = agent.invoke(user_input)
       print(response)
```

### Metacritic评分获取方式

不单独爬取存储。Agent在需要时实时web search获取。原因：
- 评分数据变化频率低，不需要每天更新
- 避免维护额外的爬虫
- 1200+个游戏全量爬Metacritic成本太高
- 只在用户查询特定游戏时才需要评分

实现方式有两个选择（让Claude Code决定哪个更合适）：
- LangChain内置的 `DuckDuckGoSearchRun` 或 `TavilySearch`
- 简单的 `requests` + BeautifulSoup 解析搜索结果

## 防封策略

| 策略 | 实现 |
|------|------|
| 请求间隔 | 每页3-5秒随机延迟 |
| 浏览器指纹 | Playwright自带真实Chromium指纹 |
| 频率控制 | 全量每天1次，减价页每6小时 |
| 错误处理 | 单页失败跳过，< 100游戏时警告 |