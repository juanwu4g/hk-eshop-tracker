# HK eShop Price Tracker - Phase 3 Tasks

## Task 1: 环境准备

- [ ] requirements.txt 添加: `langchain`, `langchain-anthropic`, `langchain-community`
- [ ] 如果 search_metacritic 用 DuckDuckGo: 添加 `duckduckgo-search`
- [ ] 安装依赖: `pip install -r requirements.txt`
- [ ] 确认环境变量: `ANTHROPIC_API_KEY`（Claude API key）

**验证**: `python -c "from langchain_anthropic import ChatAnthropic; print('OK')"` 输出OK

## Task 2: 数据库查询函数扩展

- [ ] 在 src/database.py 中添加 Agent 需要的查询函数：
  - `search_games_by_name(query: str)` → list[dict]
    - ILIKE 模糊匹配
    - 返回: id, name, url, 最新价格, 是否打折
  - `get_price_history(game_id: int)` → list[dict]
    - 该游戏所有价格记录，按时间倒序
    - 包含: current_price, original_price, discount_percent, scanned_at
  - `get_current_deals()` → list[dict]
    - 所有当前打折的游戏（最新一次扫描中 original_price IS NOT NULL 的记录）
    - 按 discount_percent 降序
    - 包含: name, current_price, original_price, discount_percent
  - `get_price_stats(game_id: int)` → dict
    - 历史最低价、最高价、平均价、打折次数
    - 当前价格是否为历史最低

**验证**: 手动调用每个函数，确认返回数据正确
- `search_games_by_name("monster")` 返回Monster Hunter等游戏
- `get_current_deals()` 返回折扣列表
- `get_price_stats(某个game_id)` 返回统计数据

## Task 3: Agent Tools 定义 (src/agent/tools.py)

- [ ] 实现 `search_games` Tool
  - 调用 database.search_games_by_name
  - 返回格式化文本（游戏名、价格、折扣信息）
  - Tool description: "搜索数据库中的游戏，输入游戏名称关键词"

- [ ] 实现 `get_price_history` Tool
  - 先用 search_games 找到 game_id（如果输入是名称）
  - 调用 database.get_price_history 和 get_price_stats
  - 返回价格历史和统计信息
  - Tool description: "获取某个游戏的价格历史，输入游戏名称"

- [ ] 实现 `get_current_deals` Tool
  - 调用 database.get_current_deals
  - 返回当前折扣列表
  - Tool description: "获取当前所有打折游戏列表"

- [ ] 实现 `search_metacritic` Tool
  - Web搜索 "metacritic {game_name} nintendo switch"
  - 提取评分信息
  - Tool description: "搜索游戏的Metacritic评分，输入游戏英文名"

**验证**: 单独测试每个Tool函数，确认输入输出正确

## Task 4: Agent 配置 (src/agent/agent.py)

- [ ] 初始化 ChatAnthropic（从 ANTHROPIC_API_KEY 环境变量）
- [ ] 注册4个Tools
- [ ] 编写系统提示:
  ```
  你是香港Nintendo eShop的折扣分析师。
  你可以查询游戏价格历史、当前折扣、Metacritic评分。
  回答时结合价格数据和游戏质量给出购买建议。
  用中文回答。价格单位是HKD（港币）。
  如果用户问的游戏找不到，告诉用户可能是名称不同，建议尝试英文名或其他关键词。
  ```
- [ ] 创建 AgentExecutor，配置 verbose=True（调试时可以看到Agent的思考过程）
- [ ] 实现 `create_agent()` → AgentExecutor
- [ ] 实现 `ask(agent, question: str)` → str

**验证**: 
- `ask(agent, "有什么好的折扣？")` → Agent调用 get_current_deals，返回折扣列表
- `ask(agent, "Monster Hunter值不值得买？")` → Agent调用 search_games + get_price_history + search_metacritic

## Task 5: 命令行交互入口 (scripts/run_agent.py)

- [ ] 从环境变量读取 ANTHROPIC_API_KEY（必须）和 DATABASE_URL（可选）
- [ ] 缺少 ANTHROPIC_API_KEY 时打印提示并退出
- [ ] 调用 create_agent()
- [ ] 进入交互循环：
  ```
  HK eShop 折扣助手（输入 quit 退出）
  > 最近有什么好折扣？
  [Agent回答]
  > Monster Hunter值得买吗？
  [Agent回答]
  > quit
  再见！
  ```
- [ ] 处理异常（API错误、网络错误）不要崩溃

**验证**: 运行 `ANTHROPIC_API_KEY=xxx python scripts/run_agent.py`，能正常对话

## Task 6: 端到端测试

- [ ] 测试场景1: "最近有什么好的折扣？"
  - Agent应调用 get_current_deals
  - 返回折扣列表

- [ ] 测试场景2: "Monster Hunter Generations Ultimate值不值得买？"
  - Agent应调用 search_games 找到游戏
  - Agent应调用 get_price_history 查价格
  - Agent可能调用 search_metacritic 查评分
  - 综合给出推荐

- [ ] 测试场景3: "塞尔达的价格历史"
  - Agent应调用 search_games（可能搜不到，因为数据库用繁体中文名）
  - Agent应尝试其他关键词或告知用户

- [ ] 测试场景4: "帮我生成本周折扣报告"
  - Agent应调用 get_current_deals
  - 生成结构化报告

**验证**: 4个场景都能得到合理回答，Agent正确选择和调用Tools

## 执行顺序

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6
  ↓        ↓        ↓        ↓        ↓        ↓
环境     数据库    Tools    Agent    CLI     测试
```

每个Task完成后先单独验证，再进入下一个。