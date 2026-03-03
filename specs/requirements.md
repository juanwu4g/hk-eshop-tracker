# HK eShop Price Tracker - Requirements

## 项目定位

学习项目，以产品标准执行。核心价值在于技能积累（数据工程、自动化、AI Agent）和作品集展示。

## 数据源

### 目标网站：store.nintendo.com.hk

- Magento电商平台，服务端渲染（SSR）
- 反爬机制：AWS WAF JavaScript Challenge
  - HTTP响应：`202` + `x-amzn-waf-action: challenge`
  - 返回JS脚本（`challenge.js`），浏览器执行后获取token并自动刷新页面
  - 简单HTTP请求（curl/requests/fetch）均无法通过，必须使用真实浏览器引擎
- 采集方式：**Playwright**（无头浏览器）

### 已验证可用的页面和数据

#### 列表页

URL模板：`/download-code?label_platform=4580&p={page}&product_list_limit=48`

实测结果（2025-02-24）：
- `product_list_limit` 支持 12、24、48 三个值（页面有toggle按钮），我们用48减少翻页次数
- 当前总计约1200+个游戏
- 减价专区 `/download-code/sale` 当前有24个折扣商品

列表页可提取的字段（已用浏览器Console验证）：

| 字段 | CSS选择器 | 示例值 |
|------|----------|--------|
| 游戏名称 | `.product-item-link` textContent | 數碼寶貝物語 時空異客 |
| 当前价格 | `.price-final_price [data-price-amount]` | 399 |
| 原价 | `.old-price [data-price-amount]` | 458（无折扣时为null） |
| 商品URL | `.product-item-link` href | https://store.nintendo.com.hk/70010000065203 |
| 封面图 | `.product-image-photo` src | (图片URL) |
| 产品ID | `[data-price-box]` data-price-box | product-id-32240 |

#### 详情页（暂未使用，留待后续Phase）

URL模式：`/{eshop_id}`（如 `/70010000065203`）

详情页包含额外字段：SKU、发售日、厂商、游戏类型、语言、平台、容量、描述。还包含一个Magento JSON对象，其中 `special_price` 有值时表示正在打折。

### 已验证不可用的数据源

| 尝试 | 结果 | 结论 |
|------|------|------|
| `ec.nintendo.com/api/HK/zh/search/sales` | 404 | API已关闭 |
| `amasty_xsearch/autocomplete/index/?q=mario` | 403 | 被WAF拦截 |
| `curl` 带User-Agent直接请求列表页 | 202 + 0 bytes | WAF challenge，无法绕过 |

## 已实现的功能

### Phase 1：数据采集器 ✅

1. Playwright浏览器管理：通过AWS WAF challenge、控制请求节奏
2. 列表页爬虫：遍历所有页面，提取游戏名称、价格（含折扣）、URL、图片
3. 数据持久化：游戏信息和价格快照存入数据库
4. 价格变动检测：识别新折扣/折扣结束/价格变动
5. 可重复执行：每天运行，增量更新，同一天同一价格不重复记录

### Phase 2：自动化 + 云数据库 ✅

1. SQLite → PostgreSQL (Supabase) 迁移
2. 双数据库支持：有 `DATABASE_URL` 环境变量时用PostgreSQL，否则回退SQLite
3. GitHub Actions 每日扫描：UTC 01:00 (HKT 09:00)，timeout 15分钟
4. GitHub Actions 减价监控：每6小时扫描 `/download-code/sale`
5. 数据迁移脚本：本地SQLite → Supabase一次性迁移
6. 异常检测：扫描结果 < 100个游戏时打印警告

## 当前数据状态

- games表：1237条记录
- price_history表：2468条记录（两次扫描）
- 数据库：Supabase PostgreSQL（东京区域）
- 连接方式：Transaction Pooler（IPv4，端口6543）

## Phase 3：AI Agent（当前开发中）

### 目标

构建一个AI Agent，能基于数据库中的价格数据和外部游戏评分，回答用户关于HK eShop折扣的问题。

### 功能需求

1. **折扣评估**："XXX值不值得买？"
   - 查数据库获取价格历史和当前价格
   - 判断是否历史最低、折扣力度如何、打折频率
   - 搜索Metacritic获取游戏评分
   - 综合价格和质量给出推荐

2. **折扣查询**："最近有什么好折扣？"
   - 查当前所有打折游戏
   - 按折扣力度排序
   - 结合评分筛选高质量折扣

3. **价格历史**："XXX的价格历史"
   - 返回该游戏所有历史价格记录
   - 标注历史最低价和平均折扣

4. **折扣报告**："生成本周折扣报告"
   - 汇总当前所有折扣
   - 标注新增折扣和即将结束的折扣
   - 推荐最值得购买的游戏

### 技术选型

- **框架**：LangChain（单Agent + 多Tool，学习框架用法）
- **LLM**：Claude API（通过Anthropic SDK）
- **交互方式**：命令行工具（MVP，后续可扩展到Bot/Web）
- **评分数据**：Agent实时web search获取Metacritic评分（不单独爬取存储）

### 为什么用LangChain而不是raw API或LangGraph

- Raw Claude API：能实现但手动管理Tool定义、对话历史、Agent循环较繁琐
- LangChain：帮助管理Tool、Memory、Agent loop，模式规范，学习价值高
- LangGraph：适合多Agent编排和复杂状态流转，当前单Agent场景不需要，后续扩展时再引入

### 数据依据

初期价格历史数据较少（刚开始积累），所以结合Metacritic评分做推荐。随着数据积累，价格维度的判断会越来越有价值（"这个游戏一年降价过5次，平均折扣40%，当前60%off是罕见好价"）。

## 非功能需求

- 每页间隔3-5秒随机延迟，避免被封
- 支持headless和有头两种模式
- 单页失败不影响其他页
- 日志输出当前进度
- GitHub Actions已验证能通过AWS WAF