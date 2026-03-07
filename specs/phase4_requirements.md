# HK eShop Price Tracker - Phase 4 Requirements

## 目标

爬取港服eShop所有游戏的详情页，提取完整元数据，构建向量搜索能力，解决Agent搜索匹配问题。

## 背景与动机

### Phase 3 遗留问题

Agent的搜索功能存在严重缺陷：

1. **简繁体不匹配**：用户输入"数码宝贝"搜不到"數碼寶貝"，"传说"搜不到"傳奇"
2. **无英文匹配**：数据库游戏名几乎纯繁体中文，搜"Tales"、"Vesperia"、"BANDAI"全部失败
3. **语义不匹配**：简繁转换能解决"数码宝贝→數碼寶貝"，但解决不了"传说→傳奇"（不同词）
4. **推荐能力弱**：Agent只有价格数据，无法按类型、发行商、语言等维度推荐

### 为什么需要详情页数据

港服eShop详情页（如 `https://store.nintendo.com.hk/70010000049989`）包含丰富的结构化数据：

- **游戏描述**（繁体中文长文本）：包含大量关键词，如"哆啦A夢"、"牧場物語"、"大雄"，做embedding后可实现语义搜索
- **发行商**（英文）：如"BANDAI NAMCO Entertainment"，搜"BANDAI"就能匹配
- **游戏类型**：如"模擬"、"角色扮演"，支持按类型推荐
- **打折时间**：精确到分钟的优惠开始/结束时间，Agent可回答"这个折扣什么时候结束"
- **语言支持**：如"繁體中文, 簡體中文, 韓文"，Agent可按语言过滤
- **发售日、人数、平台**：丰富推荐维度

### 搜索方案：Embedding向量搜索

将每个游戏的 `游戏名 + 描述 + 发行商 + 类型` 拼接为 `search_text`，生成embedding向量存入数据库。

用户查询时：查询文本 → embedding → pgvector相似度搜索。

中文embedding原理和英文完全一样，OpenAI的text-embedding模型原生支持中文，无需额外分词处理。

## 功能需求

### F1: 详情页爬虫

爬取所有游戏（当前1237个）的详情页，提取以下字段：

| 字段 | HTML来源 | 示例值 | 用途 |
|------|----------|--------|------|
| description | `[itemprop="description"]` | 繁体中文游戏描述 | embedding、推荐 |
| genre | `.game_category .attribute-item-val` | 模擬 | 类型推荐 |
| publisher | `.publisher .attribute-item-val` | BANDAI NAMCO Entertainment | 搜索、推荐 |
| release_date | `.release_date .product-attribute-val` | 2022/11/2 | 推荐新游戏 |
| languages | `.supported_languages .attribute-item-val` | 繁體中文, 簡體中文, 韓文 | 语言过滤 |
| players | `.no_of_players .product-attribute-val` | 1 ~ 2 | 推荐 |
| sale_start | `.special-period-start` | 2026/2/11 00:00 | 折扣时间查询 |
| sale_end | `.special-period-end` | 2026/3/8 23:59 | 折扣时间查询 |

### F2: 数据库扩展

新建 `game_details` 表（独立于现有games表）：

- games表保持不变，继续负责列表页数据和每日价格扫描
- game_details表存储详情页元数据（description, genre, publisher, release_date, languages, players, sale_start, sale_end）
- game_details表同时存储RAG向量搜索字段（search_text, name_embedding）
- 通过 game_id 外键关联games表
- 分表原因：更新频率不同（games每日更新，game_details一次性爬取），games表保持轻量不被大文本拖慢

### F3: Embedding生成

对每个游戏的search_text调用embedding API生成向量，存入name_embedding列。

### F4: 向量搜索Tool

新增或替换Agent的search_games Tool：

- 用户查询 → 生成embedding → pgvector余弦相似度搜索 → 返回最匹配的游戏
- 同时保留ILIKE文本搜索作为备选
- 搜索前做简繁转换预处理

### F5: Agent推荐增强

Agent的系统提示和Tools更新，利用新增字段：

- 按类型推荐："推荐休闲游戏" → 筛选genre="模擬"等
- 折扣时间："这个折扣什么时候结束" → 查sale_end
- 语言过滤："有没有支持中文的RPG" → 筛选languages含"中文" + genre含"角色扮演"

## 非功能需求

- 爬取速度：每页3-5秒延迟，1237个游戏预计1-2小时
- 容错：单页失败不影响其他页，失败的记录后续可重试
- 增量更新：只爬 `description IS NULL` 的游戏（未爬过详情页的）
- GitHub Actions集成：可手动触发详情页爬取workflow

## 已验证的技术约束

- 港服eShop有AWS WAF，必须用Playwright真实浏览器访问（与列表页爬虫一致）
- 详情页URL格式：`https://store.nintendo.com.hk/{eshop_id}`
- Nintendo的ec.nintendo.com API无法通过title ID获取英文名（已测试404/not_found）
- 详情页不包含英文游戏名，但描述和发行商字段足够支撑搜索

## 当前数据状态

- games表：1237条记录（仅有name, eshop_id, url, image_url, magento_product_id）
- price_history表：2468条记录
- 数据库：Supabase PostgreSQL（东京区域）
- 仓库：https://github.com/juanwu4g/hk-eshop-tracker