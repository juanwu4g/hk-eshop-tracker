# HK eShop Price Tracker - Phase 4 Technical Design

## 架构变更概览

```
Phase 3 (现状):
  用户查询 → ILIKE文本搜索 → 经常搜不到

Phase 4 (目标):
  用户查询 → 简繁转换 → embedding → pgvector余弦相似度 → 精准匹配
                                                         ↓
                                           返回游戏 + 类型/发行商/折扣时间等元数据
```

## 数据库Schema变更

### 新建 game_details 表

games表保持不变（轻量，每日扫描更新价格），详情页数据单独建表：

```sql
-- 启用pgvector扩展（Supabase已预装，只需启用）
CREATE EXTENSION IF NOT EXISTS vector;

-- 详情页元数据 + 向量搜索
CREATE TABLE game_details (
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

-- 向量搜索索引（数据写入后再创建）
-- IVFFlat，1237条数据用lists=20即可
CREATE INDEX idx_game_details_embedding ON game_details
USING ivfflat (name_embedding vector_cosine_ops) WITH (lists = 20);
```

### 为什么独立建表而不是ALTER TABLE

1. **更新频率不同**：games表每天daily_scan更新价格，game_details一次性爬取偶尔更新
2. **性能**：games表保持轻量，不被description大文本拖慢日常扫描
3. **维护方便**：重爬详情页可以TRUNCATE game_details，不影响games
4. **职责清晰**：games = 列表页数据（价格），game_details = 详情页数据（元数据+RAG）

### search_text 字段构建规则

```
search_text = "{name}\n{name_simplified}\n{genre}\n{publisher}\n{description前500字}"
```

示例：
```
哆啦A夢 牧場物語 自然王國與和樂家人
哆啦A梦 牧场物语 自然王国与和乐家人
模擬
BANDAI NAMCO Entertainment
既有療癒內心的場所，也有眾人的家。打動所有世代的心靈...
```

关键设计：
- `name_simplified` 是用 opencc 将繁体游戏名转为简体，确保简体输入也能匹配
- description截取前500字，避免embedding输入太长
- 用换行符分隔各字段，保持结构清晰

### sale_start / sale_end 更新策略

打折时间是动态的——每次打折活动不同。这两个字段在两个地方更新：
1. **详情页爬虫**：首次爬取时写入
2. **每日全量扫描**（现有的daily_scan）：如果未来在列表页也能提取到打折时间，可以顺带更新

注意：折扣结束后这两个字段会过期，但不需要清除——Agent判断时会对比当前时间。

## 新增模块

### src/detail_scraper.py - 详情页爬虫

```python
async def scrape_detail_page(page, url: str) -> dict:
    """爬取单个详情页，返回元数据字典
    
    Args:
        url: 游戏详情页完整URL（直接来自games表的url字段）
    """
    # navigate to url
    # extract fields using CSS selectors
    # return dict with: description, genre, publisher, release_date,
    #                    languages, players, sale_start, sale_end

async def scrape_all_details(page, games: list[dict]) -> list[dict]:
    """批量爬取所有游戏详情页
    
    Args:
        games: list of dicts with id, url, name（来自get_games_without_details）
    
    Returns:
        list of dicts with extracted metadata
    
    每页3-5秒延迟，失败跳过并记录
    """
```

CSS选择器映射（基于实际HTML验证）：

```python
SELECTORS = {
    "description": "[itemprop='description']",
    "genre": ".game_category .attribute-item-val",
    "publisher": ".publisher .attribute-item-val",
    "release_date": ".release_date .product-attribute-val",
    "languages": ".supported_languages .attribute-item-val",
    "players": ".no_of_players .product-attribute-val",
    "sale_start": ".special-period-start",
    "sale_end": ".special-period-end",
}
```

注意事项：
- 部分字段可能不存在（如免费游戏没有sale_start），用 `page.query_selector()` 返回None处理
- players字段包含图标前缀（`✕ 1 ~ 2`），需要strip处理
- release_date格式为 `2022/11/2`，需转为DATE类型
- sale_start/sale_end格式为 `2026/2/11 00:00`，需转为TIMESTAMP

### src/embedding.py - Embedding生成

```python
def generate_embedding(text: str) -> list[float]:
    """调用OpenAI embedding API生成向量"""
    # 使用 text-embedding-3-small (1536维, 便宜)
    # 输入：search_text
    # 输出：1536维float数组

def build_search_text(game: dict) -> str:
    """构建search_text字段"""
    # name + name_simplified(opencc转换) + genre + publisher + description[:500]

def batch_generate_embeddings(games: list[dict]) -> None:
    """批量生成embedding并写入数据库
    
    只处理 name_embedding IS NULL 的记录
    OpenAI batch API支持一次传多条，按100条一批处理
    """
```

Embedding模型选择：
- **text-embedding-3-small**：1536维，$0.02/1M tokens
- 1237个游戏 × ~500 tokens/游戏 ≈ 620K tokens ≈ $0.012（一次性成本极低）
- 需要新环境变量：`OPENAI_API_KEY`

### src/database.py 扩展

```python
def insert_game_details(game_id: int, details: dict) -> None:
    """插入或更新game_details记录
    INSERT INTO game_details (...) VALUES (...)
    ON CONFLICT (game_id) DO UPDATE SET ...
    只更新details中非None的字段
    """

def get_games_without_details() -> list[dict]:
    """获取还没爬过详情页的游戏
    SELECT g.id, g.eshop_id, g.name, g.url FROM games g
    LEFT JOIN game_details gd ON g.id = gd.game_id
    WHERE gd.game_id IS NULL
    """

def update_search_text(game_id: int, search_text: str) -> None:
    """UPDATE game_details SET search_text=... WHERE game_id=game_id"""

def update_embedding(game_id: int, embedding: list[float]) -> None:
    """UPDATE game_details SET name_embedding=%s WHERE game_id=game_id
    注意pgvector的写入格式：embedding::vector
    """

def get_games_without_embedding() -> list[dict]:
    """SELECT game_id, search_text FROM game_details
    WHERE name_embedding IS NULL AND search_text IS NOT NULL"""

def vector_search(query_embedding: list[float], limit: int = 10) -> list[dict]:
    """向量相似度搜索
    SELECT g.id, g.name, g.eshop_id, g.url,
           gd.genre, gd.publisher, gd.languages, gd.players,
           gd.release_date, gd.sale_start, gd.sale_end,
           1 - (gd.name_embedding <=> %s::vector) AS similarity
    FROM game_details gd
    JOIN games g ON g.id = gd.game_id
    WHERE gd.name_embedding IS NOT NULL
    ORDER BY gd.name_embedding <=> %s::vector
    LIMIT %s
    """
```

### src/agent/tools.py 更新

```python
# 替换现有的 search_games Tool
def search_games(query: str) -> str:
    """搜索游戏 - 混合搜索策略
    
    1. 用opencc将query转为简体和繁体两个版本
    2. 对query生成embedding
    3. pgvector余弦相似度搜索 top 10
    4. 同时用ILIKE搜索（简体+繁体版本）
    5. 合并去重，向量搜索结果优先
    6. 返回：游戏名、类型、发行商、当前价格、折扣信息
    """

# 更新现有的 get_game_detail Tool
def get_game_detail(game_id: int) -> str:
    """获取游戏详情 - 现在包含更多信息
    
    返回：游戏名、类型、发行商、发售日、语言、人数、
          当前价格、价格历史、折扣时间（sale_start ~ sale_end）
    """

# 新增 Tool
def search_by_genre(genre: str) -> str:
    """按类型搜索游戏
    
    输入：游戏类型关键词（如"角色扮演"、"动作"、"模拟"）
    返回：该类型下的游戏列表，按折扣力度排序
    """
```

## 文件结构变更

```
src/
├── config.py                    # 新增 OPENAI_API_KEY 配置
├── browser.py                   # 无变化
├── scraper.py                   # 无变化（列表页爬虫）
├── detail_scraper.py            # 【新增】详情页爬虫
├── embedding.py                 # 【新增】Embedding生成和向量搜索
├── database.py                  # 【扩展】新增详情字段和向量搜索方法
├── price_tracker.py             # 无变化
└── agent/
    ├── tools.py                 # 【更新】search_games改为向量搜索，新增search_by_genre
    └── agent.py                 # 【更新】系统提示更新，注册新Tool

scripts/
├── run_detail_scraper.py        # 【新增】详情页爬取入口
├── run_embedding.py             # 【新增】Embedding生成入口
├── run_scan.py                  # 无变化
├── run_sale_monitor.py          # 无变化
├── run_agent.py                 # 无变化
└── migrate_to_supabase.py       # 无变化

.github/workflows/
├── daily_scan.yml               # 无变化
├── sale_monitor.yml             # 无变化
└── detail_scraper.yml           # 【新增】手动触发详情页爬取
```

## 依赖新增

```
# requirements.txt 新增
openai                           # embedding API
opencc-python-reimplemented      # 简繁体转换（纯Python，无需C编译）
pgvector                         # PostgreSQL向量扩展的Python客户端
```

## 环境变量新增

```
OPENAI_API_KEY=sk-xxx            # OpenAI API key（embedding用）
```

现有环境变量不变：
- `DATABASE_URL`：Supabase连接字符串
- `ANTHROPIC_API_KEY`：Claude API key

## GitHub Actions

### detail_scraper.yml（新增）

```yaml
name: Detail Scraper
on:
  workflow_dispatch:              # 仅手动触发（一次性任务）
jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 180         # 3小时（1237页 × 5秒 ≈ 100分钟，留余量）
    steps:
      - checkout
      - python 3.11
      - pip install
      - playwright install chromium --with-deps
      - python scripts/run_detail_scraper.py
    env:
      DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

注意：GitHub Actions免费版单次运行最长6小时，180分钟足够。
Embedding生成不需要workflow，在本地跑一次即可（1分钟内完成）。

## 执行流程

```
Step 1: 数据库Schema迁移（ALTER TABLE + CREATE EXTENSION）
    ↓
Step 2: 详情页爬虫开发 + 本地测试（先爬10个验证）
    ↓
Step 3: 批量爬取1237个详情页（本地或GitHub Actions）
    ↓
Step 4: search_text字段构建（opencc简繁转换）
    ↓
Step 5: Embedding生成（调用OpenAI API）
    ↓
Step 6: 向量搜索Tool实现 + Agent更新
    ↓
Step 7: 端到端测试
```