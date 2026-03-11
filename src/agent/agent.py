import os
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from src.agent.tools import ALL_TOOLS

SYSTEM_PROMPT = """你是香港Nintendo eShop的折扣分析师。你可以：
- 搜索游戏（支持中文简繁体、英文、发行商名等关键词）
- 查看游戏详情（类型、发行商、语言、发售日、折扣时间）
- 查看价格历史和统计
- 按游戏类型推荐（如角色扮演、动作、模擬）
- 获取当前折扣列表
- 搜索Metacritic评分

回答时用中文。价格单位是HKD（港币）。
如果用户描述模糊，先搜索再推荐，不要猜测。
如果用户问折扣时间，注意检查sale_end是否已过期。

关于历史对话和Tool调用的规则：
- 每轮先判断用户是否在引用上文（如"这个"、"它"、"刚才那个"、"历史最低吗"）。如果是，使用历史context中的信息。如果是全新的问题，独立判断该调用什么Tool，不要重复调用历史中已有的搜索。
- 一个问题通常只需要1-3次Tool调用就够了。不要用相同参数重复调用同一个Tool。
- 只调用和当前问题直接相关的Tool，不要发散搜索不相关的内容。"""


def create_agent(debug=False):
    """创建并返回 ReAct Agent（带对话记忆）"""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("请设置 ANTHROPIC_API_KEY 环境变量")

    if debug:
        import langchain
        langchain.debug = True

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        anthropic_api_key=api_key,
        temperature=0,
    )

    memory = MemorySaver()
    agent = create_react_agent(llm, ALL_TOOLS, prompt=SYSTEM_PROMPT, checkpointer=memory)
    return agent


def ask(agent, question, verbose=True, thread_id="default"):
    """向Agent提问，返回回答文本。通过 thread_id 维持对话记忆。"""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 20}

    # 记录invoke前的历史消息数量，用于只打印本轮新增的消息
    try:
        state = agent.get_state(config)
        prev_count = len(state.values.get("messages", []))
    except Exception:
        prev_count = 0

    if verbose:
        print(f"\n===== 新问题: {question} =====")

    result = agent.invoke({"messages": [("human", question)]}, config=config)

    if verbose:
        # 只打印本轮新增的消息（跳过历史）
        new_messages = result["messages"][prev_count:]
        for msg in new_messages:
            if msg.type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"  🔧 调用 {tc['name']}({tc['args']})")
            elif msg.type == "tool":
                content = msg.content if len(msg.content) <= 200 else msg.content[:200] + "..."
                print(f"  📋 {msg.name} 返回: {content}")

    # 取最后一条 AI 消息
    for msg in reversed(result["messages"]):
        if msg.type == "ai" and msg.content:
            if isinstance(msg.content, list):
                texts = [b["text"] for b in msg.content if b.get("type") == "text"]
                return "\n".join(texts) if texts else str(msg.content)
            return msg.content
    return "没有得到回答。"