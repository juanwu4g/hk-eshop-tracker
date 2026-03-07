import os
import re
import sqlite3
from src.config import DB_PATH

DATABASE_URL = os.environ.get('DATABASE_URL')
_use_pg = bool(DATABASE_URL)

if _use_pg:
    import psycopg2
    import psycopg2.extras


def _get_conn():
    if _use_pg:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _placeholder():
    """返回当前后端的参数占位符"""
    return '%s' if _use_pg else '?'


def _fetchone_dict(cursor):
    """从cursor取一行，返回dict或None"""
    if _use_pg:
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    else:
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


def _fetchall_dict(cursor):
    """从cursor取所有行，返回list[dict]"""
    if _use_pg:
        rows = cursor.fetchall()
        if not rows:
            return []
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    else:
        return [dict(row) for row in cursor.fetchall()]


def init_db():
    """创建三张表（如不存在）"""
    conn = _get_conn()
    cur = conn.cursor()

    if _use_pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY,
                eshop_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                image_url TEXT,
                magento_product_id TEXT,
                first_seen_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_eshop_id ON games(eshop_id)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id SERIAL PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id),
                current_price REAL NOT NULL,
                original_price REAL,
                discount_percent INTEGER,
                scanned_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_game ON price_history(game_id, scanned_at DESC)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id SERIAL PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id),
                alert_type TEXT NOT NULL,
                old_price REAL,
                new_price REAL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_created ON price_alerts(created_at DESC)
        """)
        # Phase 4: pgvector + game_details
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS game_details (
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
            )
        """)
        conn.commit()
    else:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eshop_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                image_url TEXT,
                magento_product_id TEXT,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_games_eshop_id ON games(eshop_id);

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id),
                current_price REAL NOT NULL,
                original_price REAL,
                discount_percent INTEGER,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_price_history_game ON price_history(game_id, scanned_at DESC);

            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id),
                alert_type TEXT NOT NULL,
                old_price REAL,
                new_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_created ON price_alerts(created_at DESC);
        """)
        conn.commit()

    cur.close()
    conn.close()


def _extract_eshop_id(url):
    """从URL提取eshop_id，如 https://store.nintendo.com.hk/70010000065203 → 70010000065203"""
    match = re.search(r'/(\d{10,})$', url)
    return match.group(1) if match else url.rstrip('/').split('/')[-1]


def _extract_product_id(pid):
    """从pid提取数字，如 product-id-32240 → 32240"""
    if not pid:
        return None
    match = re.search(r'(\d+)', pid)
    return match.group(1) if match else pid


def upsert_game(game_data):
    """插入或更新游戏信息，返回game_id"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()
    eshop_id = _extract_eshop_id(game_data['url'])
    product_id = _extract_product_id(game_data.get('pid'))

    # 检查是否已存在
    cur.execute(f"SELECT id FROM games WHERE eshop_id = {p}", (eshop_id,))
    row = cur.fetchone()

    if row:
        game_id = row[0] if _use_pg else row['id']
        cur.execute(f"""
            UPDATE games SET name = {p}, image_url = {p}, updated_at = CURRENT_TIMESTAMP
            WHERE eshop_id = {p}
        """, (game_data['name'], game_data.get('img'), eshop_id))
        conn.commit()
    else:
        cur.execute(f"""
            INSERT INTO games (eshop_id, name, url, image_url, magento_product_id)
            VALUES ({p}, {p}, {p}, {p}, {p})
            {'RETURNING id' if _use_pg else ''}
        """, (eshop_id, game_data['name'], game_data['url'], game_data.get('img'), product_id))
        conn.commit()
        if _use_pg:
            game_id = cur.fetchone()[0]
        else:
            game_id = cur.lastrowid

    cur.close()
    conn.close()
    return game_id


def insert_price(game_id, current_price, original_price):
    """插入价格记录（同一天同一价格不重复）"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()

    if _use_pg:
        cur.execute(f"""
            SELECT id FROM price_history
            WHERE game_id = {p} AND scanned_at::date = CURRENT_DATE
              AND current_price = {p} AND COALESCE(original_price, 0) = COALESCE({p}, 0)
        """, (game_id, current_price, original_price))
    else:
        cur.execute(f"""
            SELECT id FROM price_history
            WHERE game_id = {p} AND date(scanned_at) = date('now')
              AND current_price = {p} AND COALESCE(original_price, 0) = COALESCE({p}, 0)
        """, (game_id, current_price, original_price))

    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return

    discount_percent = None
    if original_price and original_price > 0 and current_price < original_price:
        discount_percent = round((1 - current_price / original_price) * 100)

    cur.execute(f"""
        INSERT INTO price_history (game_id, current_price, original_price, discount_percent)
        VALUES ({p}, {p}, {p}, {p})
    """, (game_id, current_price, original_price, discount_percent))
    conn.commit()
    cur.close()
    conn.close()


def get_latest_price(game_id):
    """获取该游戏最近一条价格记录，返回dict或None"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()
    cur.execute(f"""
        SELECT current_price, original_price, discount_percent, scanned_at
        FROM price_history
        WHERE game_id = {p}
        ORDER BY scanned_at DESC
        LIMIT 1
    """, (game_id,))
    result = _fetchone_dict(cur)
    cur.close()
    conn.close()
    return result


def get_latest_price_by_eshop_id(eshop_id):
    """通过eshop_id查询是否已有价格记录"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()
    cur.execute(f"""
        SELECT ph.id FROM games g
        JOIN price_history ph ON ph.game_id = g.id
        WHERE g.eshop_id = {p}
        LIMIT 1
    """, (eshop_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def save_alerts(alerts):
    """批量写入price_alerts表"""
    if not alerts:
        return
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()

    for alert in alerts:
        cur.execute(f"""
            INSERT INTO price_alerts (game_id, alert_type, old_price, new_price)
            VALUES ({p}, {p}, {p}, {p})
        """, (alert['game_id'], alert['alert_type'], alert['old_price'], alert['new_price']))

    conn.commit()
    cur.close()
    conn.close()


# === Agent 查询函数 ===

def search_games_by_name(query):
    """模糊搜索游戏名称，返回匹配的游戏列表（含最新价格和折扣信息）"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()

    if _use_pg:
        cur.execute(f"""
            SELECT g.id, g.name, g.url,
                   ph.current_price, ph.original_price, ph.discount_percent
            FROM games g
            LEFT JOIN LATERAL (
                SELECT current_price, original_price, discount_percent
                FROM price_history
                WHERE game_id = g.id
                ORDER BY scanned_at DESC
                LIMIT 1
            ) ph ON true
            WHERE g.name ILIKE {p}
            ORDER BY g.name
            LIMIT 20
        """, (f'%{query}%',))
    else:
        cur.execute(f"""
            SELECT g.id, g.name, g.url,
                   ph.current_price, ph.original_price, ph.discount_percent
            FROM games g
            LEFT JOIN price_history ph ON ph.id = (
                SELECT id FROM price_history
                WHERE game_id = g.id
                ORDER BY scanned_at DESC
                LIMIT 1
            )
            WHERE g.name LIKE {p}
            ORDER BY g.name
            LIMIT 20
        """, (f'%{query}%',))

    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def get_price_history(game_id):
    """获取某游戏的所有价格记录，按时间倒序"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()
    cur.execute(f"""
        SELECT current_price, original_price, discount_percent, scanned_at
        FROM price_history
        WHERE game_id = {p}
        ORDER BY scanned_at DESC
    """, (game_id,))
    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def get_current_deals():
    """获取当前所有打折游戏（最新扫描中有折扣的），按折扣力度降序"""
    conn = _get_conn()
    cur = conn.cursor()

    if _use_pg:
        cur.execute("""
            SELECT g.name, ph.current_price, ph.original_price, ph.discount_percent
            FROM games g
            JOIN LATERAL (
                SELECT current_price, original_price, discount_percent
                FROM price_history
                WHERE game_id = g.id
                ORDER BY scanned_at DESC
                LIMIT 1
            ) ph ON true
            WHERE ph.original_price IS NOT NULL AND ph.discount_percent IS NOT NULL
            ORDER BY ph.discount_percent DESC
        """)
    else:
        cur.execute("""
            SELECT g.name, ph.current_price, ph.original_price, ph.discount_percent
            FROM games g
            JOIN price_history ph ON ph.id = (
                SELECT id FROM price_history
                WHERE game_id = g.id
                ORDER BY scanned_at DESC
                LIMIT 1
            )
            WHERE ph.original_price IS NOT NULL AND ph.discount_percent IS NOT NULL
            ORDER BY ph.discount_percent DESC
        """)

    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def get_price_stats(game_id):
    """获取某游戏的价格统计：历史最低/最高/平均价、打折次数、是否历史最低"""
    conn = _get_conn()
    cur = conn.cursor()
    p = _placeholder()

    cur.execute(f"""
        SELECT
            MIN(current_price) AS min_price,
            MAX(current_price) AS max_price,
            AVG(current_price) AS avg_price,
            COUNT(*) FILTER (WHERE discount_percent IS NOT NULL) AS discount_count,
            COUNT(*) AS total_records
        FROM price_history
        WHERE game_id = {p}
    """ if _use_pg else f"""
        SELECT
            MIN(current_price) AS min_price,
            MAX(current_price) AS max_price,
            AVG(current_price) AS avg_price,
            SUM(CASE WHEN discount_percent IS NOT NULL THEN 1 ELSE 0 END) AS discount_count,
            COUNT(*) AS total_records
        FROM price_history
        WHERE game_id = {p}
    """, (game_id,))

    stats = _fetchone_dict(cur)

    # 查当前价格判断是否历史最低
    cur.execute(f"""
        SELECT current_price FROM price_history
        WHERE game_id = {p}
        ORDER BY scanned_at DESC
        LIMIT 1
    """, (game_id,))
    latest = _fetchone_dict(cur)

    cur.close()
    conn.close()

    if stats and latest:
        stats['current_price'] = latest['current_price']
        stats['is_lowest'] = latest['current_price'] <= stats['min_price']
        if stats['avg_price']:
            stats['avg_price'] = round(stats['avg_price'], 1)

    return stats


# === Phase 4: game_details 函数 ===

def insert_game_details(game_id, details):
    """插入或更新game_details记录（只更新非None字段）"""
    conn = _get_conn()
    cur = conn.cursor()

    # 构建动态字段列表（只包含非None值）
    fields = ['game_id']
    values = [game_id]
    update_parts = []

    for key in ('description', 'genre', 'publisher', 'release_date',
                'languages', 'players', 'sale_start', 'sale_end'):
        if details.get(key) is not None:
            fields.append(key)
            values.append(details[key])
            update_parts.append(f"{key} = EXCLUDED.{key}")

    update_parts.append("updated_at = NOW()")

    placeholders = ', '.join(['%s'] * len(values))
    field_names = ', '.join(fields)
    update_sql = ', '.join(update_parts)

    cur.execute(f"""
        INSERT INTO game_details ({field_names})
        VALUES ({placeholders})
        ON CONFLICT (game_id) DO UPDATE SET {update_sql}
    """, values)

    conn.commit()
    cur.close()
    conn.close()


def get_games_without_details():
    """获取还没爬过详情页的游戏"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT g.id, g.eshop_id, g.name, g.url
        FROM games g
        LEFT JOIN game_details gd ON g.id = gd.game_id
        WHERE gd.game_id IS NULL
        ORDER BY g.id
    """)
    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def get_details_without_search_text():
    """获取有description但没有search_text的游戏"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT gd.game_id, g.name, gd.description, gd.genre, gd.publisher
        FROM game_details gd
        JOIN games g ON g.id = gd.game_id
        WHERE gd.description IS NOT NULL AND gd.search_text IS NULL
        ORDER BY gd.game_id
    """)
    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def update_search_text(game_id, search_text):
    """更新search_text字段"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE game_details SET search_text = %s, updated_at = NOW() WHERE game_id = %s",
        (search_text, game_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def update_embedding(game_id, embedding):
    """更新name_embedding向量字段"""
    conn = _get_conn()
    cur = conn.cursor()
    embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
    cur.execute(
        "UPDATE game_details SET name_embedding = %s::vector, updated_at = NOW() WHERE game_id = %s",
        (embedding_str, game_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_games_without_embedding():
    """获取有search_text但没有embedding的游戏"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT game_id, search_text
        FROM game_details
        WHERE name_embedding IS NULL AND search_text IS NOT NULL
        ORDER BY game_id
    """)
    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def vector_search(query_embedding, limit=10):
    """向量相似度搜索"""
    conn = _get_conn()
    cur = conn.cursor()
    embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
    cur.execute("""
        SELECT g.id, g.name, g.eshop_id, g.url,
               gd.genre, gd.publisher, gd.languages, gd.players,
               gd.release_date, gd.sale_start, gd.sale_end,
               1 - (gd.name_embedding <=> %s::vector) AS similarity
        FROM game_details gd
        JOIN games g ON g.id = gd.game_id
        WHERE gd.name_embedding IS NOT NULL
        ORDER BY gd.name_embedding <=> %s::vector
        LIMIT %s
    """, (embedding_str, embedding_str, limit))
    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results


def get_game_details_by_id(game_id):
    """获取单个游戏的详情信息（含game_details元数据）"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT g.id, g.name, g.url,
               gd.genre, gd.publisher, gd.languages, gd.players,
               gd.release_date, gd.sale_start, gd.sale_end, gd.description
        FROM games g
        LEFT JOIN game_details gd ON g.id = gd.game_id
        WHERE g.id = %s
    """, (game_id,))
    result = _fetchone_dict(cur)
    cur.close()
    conn.close()
    return result


def search_by_genre(genre_keyword, limit=20):
    """按游戏类型搜索，返回带最新价格的列表"""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT g.id, g.name, gd.genre, gd.publisher,
               ph.current_price, ph.original_price, ph.discount_percent
        FROM game_details gd
        JOIN games g ON g.id = gd.game_id
        LEFT JOIN LATERAL (
            SELECT current_price, original_price, discount_percent
            FROM price_history
            WHERE game_id = g.id
            ORDER BY scanned_at DESC
            LIMIT 1
        ) ph ON true
        WHERE gd.genre ILIKE %s
        ORDER BY ph.discount_percent DESC NULLS LAST, g.name
        LIMIT %s
    """, (f'%{genre_keyword}%', limit))
    results = _fetchall_dict(cur)
    cur.close()
    conn.close()
    return results
