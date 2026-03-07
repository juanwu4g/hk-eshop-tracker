"""Embedding生成和简繁转换模块"""

import os
from opencc import OpenCC

_cc_t2s = OpenCC('t2s')  # 繁→简
_cc_s2t = OpenCC('s2t')  # 简→繁


def convert_to_simplified(text):
    """繁体转简体"""
    return _cc_t2s.convert(text)


def convert_to_traditional(text):
    """简体转繁体"""
    return _cc_s2t.convert(text)


def build_search_text(game):
    """构建search_text字段

    game需包含: name, description, genre, publisher
    """
    parts = [game['name']]
    # 繁体名→简体名
    simplified_name = convert_to_simplified(game['name'])
    if simplified_name != game['name']:
        parts.append(simplified_name)
    # 类型
    if game.get('genre'):
        parts.append(game['genre'])
    # 发行商
    if game.get('publisher'):
        parts.append(game['publisher'])
    # 描述截取前500字
    if game.get('description'):
        parts.append(game['description'][:500])

    return '\n'.join(parts)


def generate_embedding(text):
    """调用OpenAI API生成embedding向量（1536维）"""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def batch_build_search_text():
    """批量构建search_text，返回处理数量"""
    from src.database import get_details_without_search_text, update_search_text

    games = get_details_without_search_text()
    if not games:
        print("所有游戏已有search_text，无需处理。")
        return 0

    print(f"待构建search_text: {len(games)} 个")
    for i, game in enumerate(games):
        search_text = build_search_text(game)
        update_search_text(game['game_id'], search_text)
        if (i + 1) % 100 == 0:
            print(f"  已处理 {i + 1}/{len(games)}")

    print(f"search_text构建完成: {len(games)} 个")
    return len(games)


def batch_generate_embeddings(batch_size=100):
    """批量生成embedding，返回处理数量"""
    from openai import OpenAI
    from src.database import get_games_without_embedding, update_embedding

    client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

    games = get_games_without_embedding()
    if not games:
        print("所有游戏已有embedding，无需处理。")
        return 0

    print(f"待生成embedding: {len(games)} 个")
    total_processed = 0

    for batch_start in range(0, len(games), batch_size):
        batch = games[batch_start:batch_start + batch_size]
        texts = [g['search_text'] for g in batch]

        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )

        for j, embedding_data in enumerate(response.data):
            game_id = batch[j]['game_id']
            update_embedding(game_id, embedding_data.embedding)

        total_processed += len(batch)
        print(f"  已处理 {total_processed}/{len(games)} (tokens: ~{response.usage.total_tokens})")

    print(f"embedding生成完成: {total_processed} 个")
    return total_processed
