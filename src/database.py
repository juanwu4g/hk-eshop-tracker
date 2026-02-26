import os
import re
import sqlite3
from src.config import DB_PATH


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """创建三张表（如不存在）"""
    conn = _get_conn()
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
    eshop_id = _extract_eshop_id(game_data['url'])
    product_id = _extract_product_id(game_data.get('pid'))

    # 检查是否已存在
    row = conn.execute("SELECT id FROM games WHERE eshop_id = ?", (eshop_id,)).fetchone()
    if row:
        conn.execute("""
            UPDATE games SET name = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE eshop_id = ?
        """, (game_data['name'], game_data.get('img'), eshop_id))
        conn.commit()
        game_id = row['id']
    else:
        cursor = conn.execute("""
            INSERT INTO games (eshop_id, name, url, image_url, magento_product_id)
            VALUES (?, ?, ?, ?, ?)
        """, (eshop_id, game_data['name'], game_data['url'], game_data.get('img'), product_id))
        conn.commit()
        game_id = cursor.lastrowid
    conn.close()
    return game_id


def insert_price(game_id, current_price, original_price):
    """插入价格记录（同一天同一价格不重复）"""
    conn = _get_conn()

    existing = conn.execute("""
        SELECT id FROM price_history
        WHERE game_id = ? AND date(scanned_at) = date('now')
          AND current_price = ? AND COALESCE(original_price, 0) = COALESCE(?, 0)
    """, (game_id, current_price, original_price)).fetchone()

    if existing:
        conn.close()
        return

    discount_percent = None
    if original_price and original_price > 0 and current_price < original_price:
        discount_percent = round((1 - current_price / original_price) * 100)

    conn.execute("""
        INSERT INTO price_history (game_id, current_price, original_price, discount_percent)
        VALUES (?, ?, ?, ?)
    """, (game_id, current_price, original_price, discount_percent))
    conn.commit()
    conn.close()


def get_latest_price(game_id):
    """获取该游戏最近一条价格记录，返回dict或None"""
    conn = _get_conn()
    row = conn.execute("""
        SELECT current_price, original_price, discount_percent, scanned_at
        FROM price_history
        WHERE game_id = ?
        ORDER BY scanned_at DESC
        LIMIT 1
    """, (game_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
