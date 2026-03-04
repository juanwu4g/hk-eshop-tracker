from langchain_core.tools import tool
from src.database import (
    search_games_by_name,
    get_price_history as db_get_price_history,
    get_price_stats,
    get_current_deals as db_get_current_deals,
)


def _to_traditional(text):
    """简体转繁体"""
    try:
        from opencc import OpenCC
        cc = OpenCC('s2t')
        return cc.convert(text)
    except ImportError:
        return text


@tool
def search_games(query: str) -> str:
    """搜索数据库中的游戏，输入游戏名称关键词。可以用中文或英文搜索。"""
    # 同时用原文和繁体搜索，合并去重
    results = search_games_by_name(query)
    traditional = _to_traditional(query)
    if traditional != query:
        results_t = search_games_by_name(traditional)
        seen_ids = {r['id'] for r in results}
        for r in results_t:
            if r['id'] not in seen_ids:
                results.append(r)
                seen_ids.add(r['id'])

    if not results:
        return f"没有找到包含「{query}」的游戏。建议尝试英文名或其他关键词。"

    lines = [f"找到 {len(results)} 个匹配游戏：\n"]
    for r in results:
        price_info = f"HKD{r['current_price']}"
        if r['discount_percent']:
            price_info += f"（原价 HKD{r['original_price']}，{r['discount_percent']}% off）"
        lines.append(f"- [ID:{r['id']}] {r['name']} - {price_info}")

    return "\n".join(lines)


@tool
def get_game_detail(game_id: int) -> str:
    """获取某个游戏的详细价格信息和历史记录，输入game_id（从search_games结果中获取）。"""
    # 先获取游戏名称
    from src.database import _get_conn, _placeholder, _fetchone_dict
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()
    cur.execute(f"SELECT id, name FROM games WHERE id = {p}", (game_id,))
    game = _fetchone_dict(cur)
    cur.close()
    conn.close()

    if not game:
        return f"找不到 game_id={game_id} 的游戏。"

    history = db_get_price_history(game_id)
    stats = get_price_stats(game_id)

    lines = [f"【{game['name']}】价格信息\n"]

    # 统计
    if stats:
        lines.append(f"历史最低价: HKD{stats['min_price']}")
        lines.append(f"历史最高价: HKD{stats['max_price']}")
        lines.append(f"平均价格: HKD{stats['avg_price']}")
        lines.append(f"记录次数: {stats['total_records']}")
        lines.append(f"打折次数: {stats['discount_count']}")
        if stats.get('is_lowest'):
            lines.append("⭐ 当前价格为历史最低！")
        lines.append("")

    # 价格历史
    lines.append("价格记录：")
    for h in history[:10]:
        entry = f"  {h['scanned_at']} - HKD{h['current_price']}"
        if h['discount_percent']:
            entry += f"（原价 HKD{h['original_price']}，{h['discount_percent']}% off）"
        lines.append(entry)

    if len(history) > 10:
        lines.append(f"  ...还有 {len(history) - 10} 条更早记录")

    return "\n".join(lines)


@tool
def get_current_deals() -> str:
    """获取当前所有打折游戏列表，按折扣力度排序。"""
    deals = db_get_current_deals()
    if not deals:
        return "当前没有打折游戏。"

    lines = [f"当前共 {len(deals)} 个折扣游戏（按折扣力度排序）：\n"]
    for i, d in enumerate(deals[:30]):
        lines.append(
            f"{i+1}. {d['name']} - HKD{d['current_price']}"
            f"（原价 HKD{d['original_price']}，{d['discount_percent']}% off）"
        )

    if len(deals) > 30:
        lines.append(f"\n...还有 {len(deals) - 30} 个折扣游戏")

    return "\n".join(lines)


@tool
def search_metacritic(game_name: str) -> str:
    """搜索游戏的Metacritic评分，输入游戏英文名。"""
    from ddgs import DDGS

    query = f"metacritic {game_name} nintendo switch score"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
    except Exception as e:
        return f"搜索失败: {e}"

    if not results:
        return f"没有找到「{game_name}」的Metacritic评分信息。"

    lines = [f"Metacritic搜索结果（{game_name}）：\n"]
    for r in results:
        lines.append(f"- {r['title']}")
        lines.append(f"  {r['body']}")
        lines.append(f"  链接: {r['href']}")
        lines.append("")

    return "\n".join(lines)


ALL_TOOLS = [search_games, get_game_detail, get_current_deals, search_metacritic]
