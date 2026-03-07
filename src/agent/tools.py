from langchain_core.tools import tool
from src.database import (
    search_games_by_name,
    get_price_history as db_get_price_history,
    get_price_stats,
    get_current_deals as db_get_current_deals,
    get_game_details_by_id,
    vector_search as db_vector_search,
    search_by_genre as db_search_by_genre,
)


@tool
def search_games(query: str) -> str:
    """搜索数据库中的游戏，输入游戏名称关键词。支持中文简繁体、英文、发行商名等关键词。"""
    from src.embedding import convert_to_traditional, convert_to_simplified, generate_embedding
    import os

    results_map = {}  # id -> result dict, 保持去重

    # 1. 向量搜索（如果有OPENAI_API_KEY）
    if os.environ.get('OPENAI_API_KEY'):
        try:
            query_embedding = generate_embedding(query)
            vector_results = db_vector_search(query_embedding, limit=10)
            for r in vector_results:
                r['_source'] = 'vector'
                r['_similarity'] = r.get('similarity', 0)
                results_map[r['id']] = r
        except Exception as e:
            pass  # 向量搜索失败时回退到文本搜索

    # 2. 文本搜索（简体+繁体+原文）
    traditional = convert_to_traditional(query)
    simplified = convert_to_simplified(query)

    for q in set([query, traditional, simplified]):
        for r in search_games_by_name(q):
            if r['id'] not in results_map:
                r['_source'] = 'text'
                results_map[r['id']] = r

    results = list(results_map.values())
    if not results:
        return f"没有找到包含「{query}」的游戏。建议尝试英文名或其他关键词。"

    lines = [f"找到 {len(results)} 个匹配游戏：\n"]
    for r in results:
        price_info = f"HKD{r.get('current_price', '?')}"
        if r.get('discount_percent'):
            price_info += f"（原价 HKD{r['original_price']}，{r['discount_percent']}% off）"
        extra = ""
        if r.get('genre'):
            extra += f" [{r['genre']}]"
        if r.get('publisher'):
            extra += f" - {r['publisher']}"
        lines.append(f"- [ID:{r['id']}] {r.get('name', '?')}{extra} - {price_info}")

    return "\n".join(lines)


@tool
def get_game_detail(game_id: int) -> str:
    """获取某个游戏的详细信息（类型、发行商、语言、折扣时间、价格历史），输入game_id。"""
    game = get_game_details_by_id(game_id)
    if not game:
        return f"找不到 game_id={game_id} 的游戏。"

    history = db_get_price_history(game_id)
    stats = get_price_stats(game_id)

    lines = [f"【{game['name']}】\n"]

    # 元数据
    if game.get('genre'):
        lines.append(f"类型: {game['genre']}")
    if game.get('publisher'):
        lines.append(f"发行商: {game['publisher']}")
    if game.get('release_date'):
        lines.append(f"发售日: {game['release_date']}")
    if game.get('languages'):
        lines.append(f"支持语言: {game['languages']}")
    if game.get('players'):
        lines.append(f"游玩人数: {game['players']}")
    if game.get('sale_start') and game.get('sale_end'):
        lines.append(f"优惠期间: {game['sale_start']} ~ {game['sale_end']}")
    elif game.get('sale_end'):
        lines.append(f"优惠截止: {game['sale_end']}")

    lines.append("")

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
def search_by_genre(genre: str) -> str:
    """按游戏类型搜索，如角色扮演、动作、模擬、益智、冒險、派對等。"""
    from src.embedding import convert_to_traditional

    # 简→繁转换（数据库中类型是繁体）
    genre_t = convert_to_traditional(genre)

    results = []
    for q in set([genre, genre_t]):
        for r in db_search_by_genre(q):
            if not any(x['id'] == r['id'] for x in results):
                results.append(r)

    if not results:
        return f"没有找到类型包含「{genre}」的游戏。"

    lines = [f"找到 {len(results)} 个「{genre}」类游戏：\n"]
    for r in results:
        price_info = f"HKD{r.get('current_price', '?')}"
        if r.get('discount_percent'):
            price_info += f"（{r['discount_percent']}% off）"
        lines.append(f"- [ID:{r['id']}] {r['name']} [{r.get('genre', '')}] - {price_info}")

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


ALL_TOOLS = [search_games, get_game_detail, get_current_deals, search_by_genre, search_metacritic]
