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
