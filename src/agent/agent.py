import os
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from src.agent.tools import ALL_TOOLS

SYSTEM_PROMPT = """你是香港Nintendo eShop的折扣分析师。
你可以查询游戏价格历史、当前折扣、Metacritic评分。
回答时结合价格数据和游戏质量给出购买建议。
用中文回答。价格单位是HKD（港币）。
如果用户问的游戏找不到，告诉用户可能是名称不同，建议尝试英文名或其他关键词。"""


def create_agent(debug=False):
    """创建并返回 ReAct Agent"""
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

    agent = create_react_agent(llm, ALL_TOOLS, prompt=SYSTEM_PROMPT)
    return agent


def ask(agent, question, verbose=True):
    """向Agent提问，返回回答文本。verbose=True 时打印 Tool 调用过程。"""
    result = agent.invoke({"messages": [("human", question)]})

    if verbose:
        for msg in result["messages"]:
            if msg.type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"  🔧 调用 {tc['name']}({tc['args']})")
            elif msg.type == "tool":
                # 截断过长的 tool 输出
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
