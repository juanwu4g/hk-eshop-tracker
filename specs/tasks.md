# HK eShop Price Tracker - Phase 1 Tasks

## Task 1: 项目初始化

- [ ] 创建项目目录结构（见design.md）
- [ ] 创建虚拟环境: `python -m venv venv`
- [ ] 创建requirements.txt: `playwright`
- [ ] 安装依赖: `pip install -r requirements.txt && playwright install chromium`
- [ ] 创建config.py（常量定义）

**验证**: `python -c "from playwright.sync_api import sync_playwright; print('OK')"` 输出OK

## Task 2: 浏览器管理模块 (browser.py)

- [ ] 实现 `create_browser(headless=True)` → 返回 browser, page
- [ ] 实现 `navigate(page, url)`:
  - `page.goto(url, wait_until="networkidle")`
  - `page.wait_for_selector('.products-grid', timeout=30000)` 确认WAF已通过
  - 失败时重试一次
  - 返回 True/False
- [ ] 实现 `wait_between_pages()` → random sleep 3-5秒

**验证**: 运行测试脚本，成功打开 `store.nintendo.com.hk/download-code?label_platform=4580&p=1&product_list_limit=48`，页面包含商品数据（不是WAF challenge页面）

## Task 3: 数据库模块 (database.py)

- [ ] 实现 `init_db()` → 创建三张表（games, price_history, price_alerts）
- [ ] 实现 `upsert_game(game_data)` → 返回game_id
  - 从URL提取eshop_id（`https://store.nintendo.com.hk/70010000065203` → `70010000065203`）
  - 从pid提取数字（`product-id-32240` → `32240`）
  - 已存在则更新name/image_url/updated_at，不存在则插入
- [ ] 实现 `insert_price(game_id, current_price, original_price)`
  - 同一天同一价格不重复插入
  - 自动计算discount_percent
- [ ] 实现 `get_latest_price(game_id)` → dict or None

**验证**: 手动调用各函数，检查数据库文件 `data/eshop.db` 中数据正确

## Task 4: 列表页爬虫 (scraper.py)

- [ ] 实现 `scrape_page(page)` → list[dict]
  - 使用 `page.evaluate()` 执行已验证的JS选择器
  - 返回格式: `[{name, finalPrice, oldPrice, url, img, pid}, ...]`
- [ ] 实现 `scrape_all_pages(page)` → list[dict]
  - 从p=1开始，逐页爬取
  - 判断最后一页：本页商品数 < 48 或为 0
  - 每页间调用 `wait_between_pages()`
  - 打印日志：`正在爬取第X页... 本页Y个商品`
  - 返回去重后的全部商品列表

**验证**: 运行后获得约1000个游戏数据，打印前5条和总数确认

## Task 5: 价格变动检测 (price_tracker.py)

- [ ] 实现 `detect_changes(game_id, new_price, new_original)` → list[dict]
  - 查询该游戏上次价格
  - 首次记录：无alert
  - 无折扣→有折扣：`new_sale`
  - 有折扣→无折扣：`sale_ended`
  - 价格降低：`price_drop`
  - 价格升高：`price_increase`
- [ ] 实现 `save_alerts(alerts)` → 写入price_alerts表

**验证**: 构造测试场景（mock数据），确认各类alert正确生成

## Task 6: 执行入口 (scripts/run_scan.py)

- [ ] 串联所有模块：init_db → create_browser → scrape_all_pages → upsert+detect+insert → 统计 → close
- [ ] 支持命令行参数: `--headless`（默认True）, `--pages`（限制页数，调试用）
- [ ] 打印最终统计：
  ```
  扫描完成
  总游戏数: 1023
  新增游戏: 15
  价格变动: 8 (3个新折扣, 2个折扣结束, 3个价格变动)
  ```

**验证（首次运行）**:
1. `python scripts/run_scan.py --pages 2` 先测试2页
2. 检查 `data/eshop.db`，确认games表有~96条记录，price_history有对应记录
3. `python scripts/run_scan.py` 全量运行
4. 确认games表有~1000条记录
5. 再运行一次，确认不会重复插入价格记录，且无虚假alert

## 执行顺序

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6
  ↓        ↓        ↓        ↓        ↓        ↓
环境     浏览器    数据库    爬虫     检测     集成
```

每个Task完成后先单独验证，再进入下一个。
