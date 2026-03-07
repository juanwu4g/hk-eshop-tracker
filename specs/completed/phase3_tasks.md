# Phase 3 Tasks - ✅ 已完成

## Task 1: 环境准备 ✅

- [x] requirements.txt 添加: `langchain`, `langchain-anthropic`, `langchain-community`, `langgraph`, `ddgs`, `opencc-python-reimplemented`
- [x] 安装依赖
- [x] 确认环境变量: `ANTHROPIC_API_KEY`

**注意**: 原计划用 `duckduckgo-search`，实际已更名为 `ddgs`，旧包返回空结果

**验证**: `from langchain_anthropic import ChatAnthropic` 导入成功 ✅

## Task 2: 数据库查询函数扩展 ✅

- [x] `search_games_by_name(query)` → list[dict]
  - PostgreSQL 用 ILIKE + `JOIN LATERAL` 获取最新价格
  - SQLite 用 LIKE + correlated subquery 替代
  - 返回: id, name, url, current_price, original_price, discount_percent
- [x] `get_price_history(game_id)` → list[dict]
  - 按时间倒序，包含 current_price, original_price, discount_percent, scanned_at
- [x] `get_current_deals()` → list[dict]
  - 最新扫描中有折扣的游戏，按 discount_percent 降序
  - 实测返回 325 个折扣商品
- [x] `get_price_stats(game_id)` → dict
  - 历史最低/最高/平均价、打折次数、是否历史最低
  - PostgreSQL 用 `COUNT(*) FILTER (WHERE ...)`，SQLite 用 `SUM(CASE WHEN ...)`
- [x] 新增 `_fetchall_dict()` 辅助函数，统一 PG/SQLite 返回格式

**验证**: 手动调用每个函数，数据返回正确 ✅

## Task 3: Agent Tools 定义 ✅

- [x] `search_games(query)` Tool
  - 调用 database.search_games_by_name
  - 返回格式化文本（[ID:xxx] 游戏名 - 价格信息）
- [x] `get_game_detail(game_id)` Tool（原设计为 get_price_history，Task 7.2 重构）
  - 输入 game_id 精确查询（避免名称歧义）
  - 返回价格历史 + 统计信息
- [x] `get_current_deals()` Tool
  - 返回当前折扣列表（限制前30条避免输出过长）
- [x] `search_metacritic(game_name)` Tool
  - 使用 `ddgs` 包搜索 "metacritic {game_name} nintendo switch score"
  - 返回搜索结果摘要

**验证**: 4个Tool函数独立测试通过 ✅

## Task 4: Agent 配置 ✅

- [x] 初始化 ChatAnthropic（claude-sonnet-4-20250514, temperature=0）
- [x] 注册4个Tools
- [x] 编写系统提示（折扣分析师角色、繁体中文搜索提示、防重复调用指示）
- [x] 创建 ReAct Agent（`langgraph.prebuilt.create_react_agent`）
- [x] 实现 `create_agent()` 和 `ask()` 函数

**注意**: 原计划用 LangChain 的 `AgentExecutor`，但 LangChain v1.2 已废弃该 API，改用 LangGraph 的 `create_react_agent`

**验证**: Agent 能正确调用 Tools 并综合回答 ✅

## Task 5: 命令行交互入口 ✅

- [x] 从环境变量读取 ANTHROPIC_API_KEY（必须）和 DATABASE_URL（可选）
- [x] 缺少 ANTHROPIC_API_KEY 时打印提示并退出
- [x] 调用 create_agent()
- [x] 交互循环（输入 quit/exit/q 退出）
- [x] 异常处理（API错误、网络错误不崩溃）
- [x] `--debug` 参数开启 LangChain 全局 debug

**验证**: `python scripts/run_agent.py` 能正常对话 ✅

## Task 6: 端到端测试 ✅

- [x] 测试场景1: "最近有什么好的折扣？" → Agent 调用 get_current_deals，返回折扣列表 ✅
- [x] 测试场景2: "Monster Hunter值不值得买？" → Agent 调用 search_games + get_game_detail + search_metacritic ✅
- [x] 测试场景3: "塞尔达的价格历史" → Agent 尝试搜索，建议用其他关键词 ✅
- [x] 测试场景4: "帮我生成本周折扣报告" → Agent 调用 get_current_deals，生成结构化报告 ✅

## Task 7: 优化迭代 ✅

### 7.1 对话记忆 ✅
- [x] 使用 `MemorySaver` + `thread_id` 实现多轮对话记忆
- [x] Agent 能理解上下文指代（"这个游戏"、"还有类似的吗"）

### 7.2 Tool重构 ✅
- [x] `get_price_history(game_name)` → `get_game_detail(game_id)`
- [x] 通过 game_id 精确查询，解决组合包 vs 单独版的名称歧义

### 7.3 简繁搜索增强 ✅
- [x] 集成 `opencc-python-reimplemented`，search_games 自动简→繁转换
- [x] 双向搜索合并去重（如 "数码宝贝" → "數碼寶貝"）
- [x] 系统提示引导 Agent 尝试英文关键词

### 7.4 减少不必要的Tool调用 ✅
- [x] 系统提示加 "不要重复调用" 指示
- [x] `recursion_limit=20` 防止无限循环

### 未完成项
- [ ] 实时流式输出：尝试 `stream_mode="messages"` 但 Anthropic AIMessageChunk.content 格式不兼容，回退到 invoke 模式
- [ ] verbose 日志历史消息重复：invoke 模式下遍历 messages 包含历史消息，checkpointer 导致之前对话的 Tool 调用重复打印

## 踩坑记录

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `AgentExecutor` 导入失败 | LangChain v1.2 已废弃 | 改用 `langgraph.prebuilt.create_react_agent` |
| `duckduckgo-search` 搜索返回空结果 | 包已更名为 `ddgs` | `pip install ddgs`，`from ddgs import DDGS` |
| `verbose=True` 无效 | `create_react_agent` 不支持 | 手动遍历 messages 打印 Tool 调用日志 |
| `ask()` 返回 "没有得到回答" | Anthropic content 是 list 格式 | 兼容处理 `list[dict]` 和 `str` 两种格式 |
| 流式输出 chunk 丢失文本 | AI chunk 同时含 tool_calls 和 content，if/else 互斥跳过 | 回退到 invoke 模式 |
