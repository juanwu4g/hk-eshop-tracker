# Phase 1 Tasks - ✅ 已完成

## Task 1: 项目初始化 ✅

- [x] 创建项目目录结构（见design.md）
- [x] 创建虚拟环境: `python -m venv venv`
- [x] 创建requirements.txt: `playwright`
- [x] 安装依赖: `pip install -r requirements.txt && playwright install chromium`
- [x] 创建config.py（常量定义）

**验证**: `python -c "from playwright.sync_api import sync_playwright; print('OK')"` 输出OK ✅

## Task 2: 浏览器管理模块 (browser.py) ✅

- [x] 实现 `create_browser(headless=True)` → 返回 browser, page
- [x] 实现 `navigate(page, url)`:
  - `page.goto(url, wait_until="networkidle")`
  - `page.wait_for_selector('.products-grid', timeout=30000)` 确认WAF已通过
  - 失败时重试一次
  - 返回 True/False
- [x] 实现 `wait_between_pages()` → random sleep 3-5秒

**验证**: 成功打开 `store.nintendo.com.hk/download-code?label_platform=4580&p=1&product_list_limit=48`，页面包含商品数据 ✅

## Task 3: 数据库模块 (database.py) ✅

- [x] 实现 `init_db()` → 创建三张表（games, price_history, price_alerts）
- [x] 实现 `upsert_game(game_data)` → 返回game_id
  - 从URL提取eshop_id（`https://store.nintendo.com.hk/70010000065203` → `70010000065203`）
  - 从pid提取数字（`product-id-32240` → `32240`）
  - 已存在则更新name/image_url/updated_at，不存在则插入
- [x] 实现 `insert_price(game_id, current_price, original_price)`
  - 同一天同一价格不重复插入
  - 自动计算discount_percent
- [x] 实现 `get_latest_price(game_id)` → dict or None

**验证**: 数据库文件 `data/eshop.db` 中数据正确 ✅

## Task 4: 列表页爬虫 (scraper.py) ✅

- [x] 实现 `scrape_page(page)` → list[dict]
  - 使用 `page.evaluate()` 执行已验证的JS选择器
  - 返回格式: `[{name, finalPrice, oldPrice, url, img, pid}, ...]`
- [x] 实现 `scrape_all_pages(page)` → list[dict]
  - 从p=1开始，逐页爬取
  - 判断最后一页：本页商品数 < 48 或为 0
  - 每页间调用 `wait_between_pages()`
  - 打印日志：`正在爬取第X页... 本页Y个商品`
  - 返回去重后的全部商品列表

**验证**: 成功爬取1231个游戏 ✅

## Task 5: 价格变动检测 (price_tracker.py) ✅

- [x] 实现 `detect_changes(game_id, new_price, new_original)` → list[dict]
  - 查询该游戏上次价格
  - 首次记录：无alert
  - 无折扣→有折扣：`new_sale`
  - 有折扣→无折扣：`sale_ended`
  - 价格降低：`price_drop`
  - 价格升高：`price_increase`
- [x] 实现 `save_alerts(alerts)` → 写入price_alerts表

**验证**: 各类alert正确生成 ✅

## Task 6: 执行入口 (scripts/run_scan.py) ✅

- [x] 串联所有模块：init_db → create_browser → scrape_all_pages → upsert+detect+insert → 统计 → close
- [x] 支持命令行参数: `--headless`（默认True）, `--pages`（限制页数，调试用）
- [x] 打印最终统计

**验证结果**:
- `python scripts/run_scan.py --pages 2` 测试2页：96个商品 ✅
- `python scripts/run_scan.py` 全量运行：1231个游戏 ✅
- 重复运行不产生重复记录，无虚假alert ✅
