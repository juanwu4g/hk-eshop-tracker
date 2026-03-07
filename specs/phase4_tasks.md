# HK eShop Price Tracker - Phase 4 Tasks

## 前置信息

- 仓库：https://github.com/juanwu4g/hk-eshop-tracker
- 数据库：Supabase PostgreSQL（连接字符串在 DATABASE_URL 环境变量）
- 现有games表：1237条记录，字段有 id, eshop_id, name, url, image_url, magento_product_id, first_seen_at, updated_at
- 详情页URL格式：`https://store.nintendo.com.hk/{eshop_id}`
- 港服eShop有AWS WAF，必须用Playwright真实浏览器访问
- 参考现有代码：src/browser.py（浏览器管理）、src/scraper.py（列表页爬虫）、src/database.py（数据库操作）

## Task 1: 数据库Schema迁移

在Supabase SQL Editor中执行以下迁移（或写成迁移脚本）：

```sql
-- 启用pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 新建详情页数据表（独立于games表）
CREATE TABLE IF NOT EXISTS game_details (
    game_id INTEGER PRIMARY KEY REFERENCES games(id),
    description TEXT,
    genre VARCHAR(100),
    publisher VARCHAR(200),
    release_date DATE,
    languages VARCHAR(500),
    players VARCHAR(50),
    sale_start TIMESTAMP,
    sale_end TIMESTAMP,
    search_text TEXT,
    name_embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

设计说明：
- 独立建表而非ALTER TABLE加列，因为games表每天daily_scan更新价格，game_details是一次性爬取偶尔更新，更新频率不同
- games表保持轻量（不被description大文本拖慢），game_details专门存详情页元数据和RAG向量
- 重爬详情页可直接TRUNCATE game_details，不影响games

**注意**：向量索引在数据量写入后再创建（Task 5之后），空表建索引没意义。

**验证**：在Supabase SQL Editor执行 `SELECT table_name FROM information_schema.tables WHERE table_name = 'game_details';` 确认表存在。

## Task 2: 详情页爬虫 (src/detail_scraper.py)

### 2.1 创建 src/detail_scraper.py

参考现有的 src/scraper.py 和 src/browser.py 的代码风格。

核心函数：

- [ ] `scrape_detail_page(page, url: str) -> dict | None`
  - 访问游戏详情页URL（直接使用games表中的url字段）
  - 等待页面加载（wait_for_selector `.product-info-main` 或 `.product-attributes-all`）
  - 用以下CSS选择器提取字段：

  ```python
  SELECTORS = {
      "description": "[itemprop='description']",          # innerText
      "genre": ".game_category .attribute-item-val",       # innerText，strip
      "publisher": ".publisher .attribute-item-val",        # innerText，strip
      "release_date": ".release_date .product-attribute-val",  # innerText，strip
      "languages": ".supported_languages .attribute-item-val", # innerText，strip
      "players": ".no_of_players .product-attribute-val",      # innerText，strip掉图标字符
      "sale_start": ".special-period-start",               # innerText（可能不存在）
      "sale_end": ".special-period-end",                   # innerText（可能不存在）
  }
  ```

  - 每个selector用 `page.query_selector()` 获取，不存在则返回None
  - players字段需要清理：去掉 `✕` 和多余空格，只保留如 `1 ~ 2`
  - release_date转为 `YYYY-MM-DD` 格式（输入如 `2022/11/2`）
  - sale_start/sale_end保持原始字符串（如 `2026/2/11 00:00`），数据库存为TIMESTAMP
  - 返回dict，失败返回None并打印错误日志

- [ ] `scrape_all_details(page, games: list[dict], delay_range=(3, 5)) -> tuple[int, int]`
  - 遍历games列表，调用scrape_detail_page
  - 每页之间 random sleep delay_range秒
  - 成功后立即调用database.insert_game_details写入game_details表（逐条写入，避免全部爬完才写导致中途失败丢数据）
  - 打印进度：`[{current}/{total}] {name} - OK` 或 `[{current}/{total}] {name} - FAILED: {error}`
  - 返回 (成功数, 失败数)

### 2.2 创建 scripts/run_detail_scraper.py

- [ ] 入口脚本
  - 从数据库获取所有 `description IS NULL` 的游戏
  - 创建Playwright浏览器（复用src/browser.py的create_browser）
  - 调用 scrape_all_details
  - 打印总结：`完成：{success}成功，{failed}失败，共{total}个`

**验证**：
- 先只爬5个游戏测试：`python scripts/run_detail_scraper.py --limit 5`（加个可选的limit参数）
- 检查数据库：`SELECT name, genre, publisher, release_date FROM games WHERE description IS NOT NULL LIMIT 5;`
- 确认字段值正确，无乱码

## Task 3: 数据库扩展 (src/database.py)

在现有的 src/database.py 中新增以下函数：

- [ ] `init_game_details_table() -> None`
  - CREATE TABLE IF NOT EXISTS game_details（同Task 1的SQL）
  - 在init_db()中调用，确保表存在

- [ ] `insert_game_details(game_id: int, details: dict) -> None`
  - INSERT INTO game_details (game_id, description, genre, ...) VALUES (...)
  - ON CONFLICT (game_id) DO UPDATE SET description=EXCLUDED.description, ...
  - 只更新details中非None的字段
  - 同时设置 updated_at=NOW()

- [ ] `get_games_without_details() -> list[dict]`
  - SELECT g.id, g.eshop_id, g.name, g.url FROM games g
    LEFT JOIN game_details gd ON g.id = gd.game_id
    WHERE gd.game_id IS NULL
  - 用于增量爬取（只爬还没有详情的游戏）

- [ ] `update_search_text(game_id: int, search_text: str) -> None`
  - UPDATE game_details SET search_text=..., updated_at=NOW() WHERE game_id=game_id

- [ ] `update_embedding(game_id: int, embedding: list[float]) -> None`
  - UPDATE game_details SET name_embedding=%s, updated_at=NOW() WHERE game_id=game_id
  - 注意pgvector的写入格式

- [ ] `get_games_without_embedding() -> list[dict]`
  - SELECT game_id, search_text FROM game_details WHERE name_embedding IS NULL AND search_text IS NOT NULL

- [ ] `vector_search(query_embedding: list[float], limit: int = 10) -> list[dict]`
  - ```sql
    SELECT g.id, g.name, g.eshop_id, g.url,
           gd.genre, gd.publisher, gd.languages, gd.players,
           gd.release_date, gd.sale_start, gd.sale_end,
           1 - (gd.name_embedding <=> %s::vector) AS similarity
    FROM game_details gd
    JOIN games g ON g.id = gd.game_id
    WHERE gd.name_embedding IS NOT NULL
    ORDER BY gd.name_embedding <=> %s::vector
    LIMIT %s
    ```
  - 返回list[dict]，包含similarity字段（0~1，越高越相似）

**验证**：Task 2爬完5个游戏后，查询 `SELECT gd.*, g.name FROM game_details gd JOIN games g ON g.id = gd.game_id LIMIT 5;` 确认数据写入正确。

## Task 4: 简繁转换 + search_text构建

### 4.1 依赖安装

- [ ] requirements.txt 添加：`opencc-python-reimplemented`
- [ ] 安装：`pip install opencc-python-reimplemented`

### 4.2 创建 src/embedding.py

- [ ] `convert_to_simplified(text: str) -> str`
  - 使用 opencc 的 `t2s`（繁→简）配置
  - 输入繁体中文，输出简体中文
  - 示例：`"數碼寶貝"` → `"数码宝贝"`

- [ ] `build_search_text(game: dict) -> str`
  - 输入：game dict（需要 name, description, genre, publisher 字段）
  - 输出：拼接后的search_text
  - 格式：
    ```
    {name}
    {convert_to_simplified(name)}
    {genre or ''}
    {publisher or ''}
    {description[:500] or ''}
    ```
  - 示例输出：
    ```
    哆啦A夢 牧場物語 自然王國與和樂家人
    哆啦A梦 牧场物语 自然王国与和乐家人
    模擬
    BANDAI NAMCO Entertainment
    既有療癒內心的場所，也有眾人的家...
    ```

- [ ] `batch_build_search_text() -> int`
  - 查询所有 game_details 中 `description IS NOT NULL AND search_text IS NULL` 的游戏（需JOIN games表拿name）
  - 为每个游戏调用 build_search_text
  - 调用 database.update_search_text 写入
  - 返回处理数量
  - 打印进度

**验证**：
- `convert_to_simplified("數碼寶貝物語")` 返回 `"数码宝贝物语"`
- 查数据库：`SELECT name, LEFT(search_text, 100) FROM games WHERE search_text IS NOT NULL LIMIT 3;`

## Task 5: Embedding生成

### 5.1 依赖安装

- [ ] requirements.txt 添加：`openai`, `pgvector`
- [ ] 安装：`pip install openai pgvector`

### 5.2 在 src/embedding.py 中添加

- [ ] `generate_embedding(text: str) -> list[float]`
  - 调用 OpenAI API：`openai.embeddings.create(model="text-embedding-3-small", input=text)`
  - 返回1536维向量
  - 需要环境变量 `OPENAI_API_KEY`

- [ ] `batch_generate_embeddings(batch_size: int = 100) -> int`
  - 查询所有 `search_text IS NOT NULL AND name_embedding IS NULL` 的游戏
  - OpenAI embedding API支持批量输入（一次最多2048条）
  - 按batch_size分批处理，每批调用一次API
  - 写入数据库
  - 返回处理数量
  - 打印进度和token用量估算

### 5.3 创建 scripts/run_embedding.py

- [ ] 入口脚本
  - 先执行 batch_build_search_text（构建search_text）
  - 再执行 batch_generate_embeddings（生成embedding）
  - 打印总结

### 5.4 创建向量索引

Embedding全部写入后，创建索引：

```sql
CREATE INDEX idx_game_details_embedding ON game_details
USING ivfflat (name_embedding vector_cosine_ops) WITH (lists = 20);
```

lists值说明：通常为 sqrt(行数)，1237行 → sqrt(1237) ≈ 35，但数据量小用20即可。

**验证**：
- `python scripts/run_embedding.py` 运行成功
- 查数据库：`SELECT g.name, gd.name_embedding IS NOT NULL AS has_embedding FROM game_details gd JOIN games g ON g.id = gd.game_id LIMIT 10;` 全部为true
- 测试向量搜索（在Supabase SQL Editor）：
  ```sql
  -- 先随便拿一个游戏的embedding，搜索最相似的
  SELECT g.name, 1 - (a.name_embedding <=> b.name_embedding) AS similarity
  FROM game_details a
  JOIN game_details b ON b.game_id = (SELECT id FROM games WHERE name LIKE '%哆啦A夢 牧場物語%' LIMIT 1)
  JOIN games g ON g.id = a.game_id
  WHERE a.game_id != b.game_id
  AND a.name_embedding IS NOT NULL
  ORDER BY a.name_embedding <=> b.name_embedding
  LIMIT 5;
  ```
  应该返回类型或发行商相似的游戏。

## Task 6: Agent搜索升级 (src/agent/tools.py)

### 6.1 更新 search_games Tool

- [ ] 替换现有的ILIKE搜索为混合搜索：

  ```python
  def search_games(query: str) -> str:
      """搜索游戏 - 向量搜索 + 文本搜索混合"""
      # 1. 简繁转换
      query_traditional = convert_to_traditional(query)  # opencc s2t
      query_simplified = convert_to_simplified(query)     # opencc t2s
      
      # 2. 向量搜索
      query_embedding = generate_embedding(query)
      vector_results = database.vector_search(query_embedding, limit=10)
      
      # 3. 文本搜索（ILIKE，作为补充）
      text_results_1 = database.search_games_by_name(query)
      text_results_2 = database.search_games_by_name(query_traditional)
      text_results_3 = database.search_games_by_name(query_simplified)
      
      # 4. 合并去重（向量搜索结果在前）
      # 5. 格式化返回
  ```

- [ ] 在 embedding.py 中添加 `convert_to_traditional(text: str) -> str`（opencc `s2t` 配置）

### 6.2 更新 get_game_detail Tool

- [ ] 返回信息中新增：genre, publisher, release_date, languages, players, sale_start, sale_end
- [ ] sale_start/sale_end格式化为可读形式，如"优惠期间: 2026/2/11 ~ 2026/3/8"

### 6.3 新增 search_by_genre Tool（可选）

- [ ] 按游戏类型搜索
  - 输入：类型关键词（如"角色扮演"、"动作"、"模拟"）
  - 查询：`SELECT ... FROM games WHERE genre ILIKE '%{keyword}%' ORDER BY ...`
  - 可按当前是否打折排序
  - Tool description: "按游戏类型搜索，如角色扮演、动作、模擬、益智等"

### 6.4 更新系统提示 (src/agent/agent.py)

- [ ] 更新系统提示，告知Agent新能力：

```
你是香港Nintendo eShop的折扣分析师。你可以：
- 搜索游戏（支持中文简繁体、英文、发行商名等关键词）
- 查看游戏详情（类型、发行商、语言、发售日、折扣时间）
- 查看价格历史和统计
- 按游戏类型推荐
- 获取当前折扣列表

回答时用中文。价格单位是HKD（港币）。
如果用户描述模糊，先搜索再推荐，不要猜测。
如果用户问折扣时间，注意检查sale_end是否已过期。
```

**验证**：
- `search_games("数码宝贝")` → 应该能找到 "數碼寶貝物語 時空異客"（通过向量搜索或简繁转换）
- `search_games("Tales")` → 应该能找到傳奇系列（通过embedding语义匹配）
- `search_games("BANDAI")` → 应该能找到万代发行的游戏（通过search_text中的publisher字段）
- `search_games("牧场")` → 应该能找到牧場物語（简繁转换）
- Agent对话测试："推荐一个适合两个人玩的游戏" → Agent使用搜索 + players字段推荐

## Task 7: 端到端测试

- [ ] 测试场景1: "数码宝贝值得买吗"
  - 之前搜不到，现在应该能通过向量搜索或简繁转换找到"數碼寶貝物語 時空異客"
  - Agent返回价格、类型、发行商等信息

- [ ] 测试场景2: "有没有BANDAI的游戏在打折"
  - Agent搜索publisher含"BANDAI"的游戏，筛选打折中的
  - 返回列表

- [ ] 测试场景3: "推荐一个角色扮演游戏"
  - Agent使用search_by_genre或向量搜索
  - 结合价格和折扣推荐

- [ ] 测试场景4: "宵星传奇的折扣什么时候结束"
  - Agent搜索到游戏（简繁转换："传奇"→"傳奇"或向量匹配）
  - 返回sale_end字段

- [ ] 测试场景5: "有没有支持简体中文的休闲游戏"
  - Agent组合languages和genre条件
  - 返回匹配结果

## 执行顺序

```
Task 1 (Schema迁移)
  ↓
Task 2 + Task 3 (详情页爬虫 + 数据库函数，可并行开发)
  ↓
本地测试：爬5个游戏验证
  ↓
批量爬取：全部1237个游戏
  ↓
Task 4 (简繁转换 + search_text)
  ↓
Task 5 (Embedding生成)
  ↓
Task 6 (Agent搜索升级)
  ↓
Task 7 (端到端测试)
```

## 关键提醒

1. **爬虫一定要用Playwright**，直接HTTP请求会被AWS WAF拦截（返回202 + challenge.js）
2. **逐条写入数据库**，不要攒到最后一起写——1237页爬2小时，中途失败会丢全部数据
3. **embedding只需跑一次**，后续新游戏在daily_scan时增量处理
4. **先小规模测试**（5-10个游戏），确认选择器正确后再批量跑
5. **sale_start/sale_end可能不存在**（没打折的游戏），CSS选择器返回None时跳过
6. **pgvector在Supabase已预装**，只需 `CREATE EXTENSION IF NOT EXISTS vector;` 启用