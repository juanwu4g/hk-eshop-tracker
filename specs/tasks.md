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

## Task 7: 优化迭代（基于实际测试发现的问题）

以下问题在端到端测试中发现，按优先级排序：

### 7.1 对话记忆（最高优先级）

**问题**：Agent没有对话记忆，每次invoke是独立的。用户刚聊完宵星傳奇，紧接着问"目前的价格是历史最低吗"，Agent不知道在说哪个游戏。"还有其他类似的吗"也无法理解上文。

**修复**：使用 LangChain 的 `ConversationBufferWindowMemory`，保留最近10轮对话（k=10）。
- 创建 memory 对象时设置 `return_messages=True`, `memory_key="chat_history"`
- 传入 AgentExecutor

**验证**：
- 先问"宵星傳奇有打折吗"
- 再问"目前价格是历史最低吗" → Agent应该知道在问宵星傳奇，不需要用户重复
- 再问"还有其他类似的吗" → Agent应该知道在说JRPG或Tales系列

### 7.2 Tool重构：get_price_history → get_game_detail（接受game_id）

**问题**：搜索"宵星傳奇 REMASTER"时，get_price_history返回了组合包的数据而不是单独版。根本原因是Tool内部用名称匹配，ILIKE `%宵星傳奇 REMASTER%` 同时匹配了组合包（名字里也包含这个词），取了第一条。

**修复**：
- 把 `get_price_history(game_name: str)` 改为 `get_game_detail(game_id: int)`
- 输入从游戏名改成game_id（从search_games的返回结果中获取）
- 返回内容：游戏名、当前价格、价格历史记录、统计信息（历史最低/最高/平均、打折次数、是否历史最低）
- Tool description: "获取某个游戏的详细价格信息和历史记录，输入game_id（从search_games结果中获取）"

修复后Agent的工作流变成：
1. search_games("宵星") → 返回两个结果，含game_id
2. Agent看到ID:1138是单独版
3. get_game_detail(1138) → 返回准确的价格历史

**验证**：`get_game_detail(1138)` 返回宵星傳奇 REMASTER 单独版的价格历史，不是组合包的

### 7.3 游戏名模糊搜索增强

**问题**：搜索"传说"找不到"傳奇"，"数码宝贝"找不到"數碼寶貝"。简体中文无法匹配繁体中文。

**修复**（两部分）：

**A. 简繁体转换**：
- 安装 `opencc-python-reimplemented`（纯Python，无需C编译）
- 在 search_games Tool 内部，搜索前将用户输入转为繁体中文
- 同时用简体原文和繁体转换后的文字各搜一次，合并去重
- 这样"数码宝贝" → "數碼寶貝" 就能匹配了

**B. 系统提示优化**：
- 系统提示中加入："数据库中游戏名以繁体中文为主，部分含英文。搜索时如果中文搜不到结果，请尝试英文游戏名或更短的关键词。"
- 这样Agent搜"传说系列"无结果时，会自动尝试搜"Tales"

**验证**：
- `search_games("数码宝贝")` → 能找到數碼寶貝相关游戏
- `search_games("传说")` → 可能仍找不到（传说≠傳奇），但Agent会尝试英文"Tales"
- `search_games("Tales")` → 能找到Tales系列游戏

### 7.4 减少不必要的Tool调用

**问题**：Agent重复调用同一个Tool，输入一样，结果一样，浪费token和时间。

**修复**：
- 系统提示中加入："如果一个Tool已经返回了结果，不要用相同的参数重复调用。"
- AgentExecutor 设置 `max_iterations=8`，防止无限循环
- 7.2的修复（改用game_id）也会减少因歧义导致的重复调用

**验证**：同一个问题中，不出现对同一Tool用相同参数的重复调用