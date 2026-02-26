# HK eShop Price Tracker - Phase 1: 技术设计

## 技术栈

| 组件 | 技术 | 理由 |
|------|------|------|
| 爬虫 | Python + Playwright | 唯一能通过AWS WAF challenge的方案 |
| 数据库 | SQLite | 零配置，单文件，MVP足够 |
| 语言 | Python 3.10+ | Playwright官方支持好 |

## 项目结构

```
hk-eshop-tracker/
├── requirements.txt            # playwright
├── src/
│   ├── config.py               # URL模板、延迟参数、数据库路径
│   ├── browser.py              # Playwright浏览器管理（WAF处理）
│   ├── scraper.py              # 列表页爬虫逻辑
│   ├── database.py             # SQLite数据库操作
│   └── price_tracker.py        # 价格变动检测
├── scripts/
│   └── run_scan.py             # 执行入口：每日扫描
├── data/
│   └── eshop.db                # SQLite数据库文件
└── specs/                      # 本文档
    ├── requirements.md
    ├── design.md
    └── tasks.md
```

## 数据库Schema

### games 表

存储游戏基本信息。`eshop_id` 从URL提取（如 `70010000065203`），作为唯一标识。

```sql
CREATE TABLE games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eshop_id TEXT UNIQUE NOT NULL,        -- URL中的ID，如 '70010000065203'
    name TEXT NOT NULL,                    -- 游戏名称
    url TEXT NOT NULL,                     -- 商品完整URL
    image_url TEXT,                        -- 封面图URL
    magento_product_id TEXT,               -- Magento产品ID，如 '32240'（从 'product-id-32240' 提取）
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_games_eshop_id ON games(eshop_id);
```

### price_history 表

每次扫描为每个游戏记录一条价格快照。同一天同一价格不重复记录。

```sql
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    current_price REAL NOT NULL,           -- 当前售价（finalPrice）
    original_price REAL,                   -- 原价（oldPrice，无折扣时为NULL）
    discount_percent INTEGER,              -- 折扣百分比（计算得出）
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_price_history_game ON price_history(game_id, scanned_at DESC);
```

### price_alerts 表

记录价格变动事件，供后续通知系统使用。

```sql
CREATE TABLE price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    alert_type TEXT NOT NULL,              -- 'new_sale' | 'sale_ended' | 'price_drop' | 'price_increase' | 'historical_low'
    old_price REAL,
    new_price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alerts_created ON price_alerts(created_at DESC);
```

## 模块设计

### config.py

```python
BASE_URL = "https://store.nintendo.com.hk"
LIST_URL_TEMPLATE = "/download-code?label_platform=4580&p={page}&product_list_limit=48"
SALE_URL = "/download-code/sale"
DB_PATH = "data/eshop.db"
MIN_DELAY = 3  # 秒
MAX_DELAY = 5
```

### browser.py

职责：管理Playwright浏览器生命周期，处理WAF challenge。

```
create_browser(headless: bool) → (browser, page)
    - 启动Chromium
    - 设置合理的viewport和user agent

navigate(page, url) → bool
    - page.goto(url, wait_until="networkidle")
    - 等待页面实际内容加载（而非WAF challenge页面）
    - 检测方式：等待 '.products-grid' 或 'itemprop="name"' 出现
    - 超时30秒后重试一次
    - 返回是否成功

wait_between_pages()
    - random sleep 3-5秒
```

WAF challenge处理关键点：
- Playwright用真实Chromium，会自动执行challenge.js
- `wait_until="networkidle"` 会等待JS执行完+页面刷新
- 可能需要额外等待（`page.wait_for_selector`）确保商品列表渲染完成

### scraper.py

职责：从已加载的页面中提取商品数据。

```
scrape_page(page) → list[dict]
    - querySelectorAll('.products-grid .product-item')
    - 对每个item提取: name, finalPrice, oldPrice, url, img, productId
    - 返回商品列表

scrape_all_pages(page) → list[dict]
    - 从p=1开始遍历
    - 每页调用 scrape_page
    - 当页面商品数 < 48 或为 0 时停止
    - 每页之间调用 wait_between_pages
    - 打印进度日志
    - 返回全部商品
```

数据提取使用 `page.evaluate()` 在浏览器内执行JS（已验证的选择器）：
```javascript
// 在page.evaluate中运行
document.querySelectorAll('.products-grid .product-item')
```

### database.py

职责：SQLite数据库的CRUD操作。

```
init_db() → 创建表（如不存在）

upsert_game(game_data) → game_id
    - INSERT OR REPLACE based on eshop_id
    - 从URL提取eshop_id（最后一段路径）
    - 从productId提取数字部分

insert_price(game_id, current_price, original_price) → None
    - 查询今天是否已有相同价格的记录
    - 如果没有才插入（避免重复）

get_latest_price(game_id) → (current_price, original_price) or None
    - 获取该游戏最近一条价格记录
```

### price_tracker.py

职责：对比新旧价格，生成变动事件。

```
detect_changes(game_id, new_price, new_original_price) → list[alert]
    - 获取该游戏上一次的价格记录
    - 对比判断：
      - 之前无折扣 + 现在有折扣 → 'new_sale'
      - 之前有折扣 + 现在无折扣 → 'sale_ended'
      - 价格降低 → 'price_drop'
      - 价格升高 → 'price_increase'
    - 返回alert列表

save_alerts(alerts) → None
    - 批量写入price_alerts表
```

### scripts/run_scan.py

执行入口，串联所有模块：

```
1. init_db()
2. browser, page = create_browser(headless=从命令行参数读取)
3. all_games = scrape_all_pages(page)
4. for game in all_games:
     a. game_id = upsert_game(game)
     b. alerts = detect_changes(game_id, game.price, game.oldPrice)
     c. insert_price(game_id, game.price, game.oldPrice)
     d. save_alerts(alerts)
5. 打印统计：总游戏数、新增数、价格变动数
6. browser.close()
```

## 防封策略

| 策略 | 实现 |
|------|------|
| 请求间隔 | 每页3-5秒随机延迟 |
| 浏览器指纹 | Playwright自带真实Chromium指纹 |
| 频率控制 | 每天最多运行1-2次 |
| 错误处理 | 单页失败跳过，继续下一页 |
| 可选加强 | playwright-stealth插件（如遇检测再加）|
