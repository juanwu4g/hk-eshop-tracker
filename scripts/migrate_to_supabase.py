#!/usr/bin/env python3
"""将本地 SQLite 数据迁移到 Supabase PostgreSQL"""

import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("错误：请设置 DATABASE_URL 环境变量")
    sys.exit(1)

import psycopg2

SQLITE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'eshop.db')


def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"错误：找不到本地数据库 {SQLITE_PATH}")
        sys.exit(1)

    # 连接 SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    # 连接 PostgreSQL
    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_cur = pg_conn.cursor()

    # 确保表已创建
    from src.database import init_db
    # 临时覆盖让 init_db 用 PG
    init_db()

    # 迁移 games 表
    games = sqlite_conn.execute("SELECT * FROM games ORDER BY id").fetchall()
    games_migrated = 0
    id_map = {}  # sqlite_id → pg_id

    for g in games:
        pg_cur.execute("""
            INSERT INTO games (eshop_id, name, url, image_url, magento_product_id, first_seen_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (eshop_id) DO NOTHING
            RETURNING id
        """, (g['eshop_id'], g['name'], g['url'], g['image_url'],
              g['magento_product_id'], g['first_seen_at'], g['updated_at']))
        row = pg_cur.fetchone()
        if row:
            id_map[g['id']] = row[0]
            games_migrated += 1
        else:
            # 已存在，获取 PG 中的 id
            pg_cur.execute("SELECT id FROM games WHERE eshop_id = %s", (g['eshop_id'],))
            id_map[g['id']] = pg_cur.fetchone()[0]

    pg_conn.commit()
    print(f"Games: {games_migrated} 条新迁移（共 {len(games)} 条）")

    # 迁移 price_history 表
    prices = sqlite_conn.execute("SELECT * FROM price_history ORDER BY id").fetchall()
    prices_migrated = 0

    for p in prices:
        pg_game_id = id_map.get(p['game_id'])
        if not pg_game_id:
            continue
        pg_cur.execute("""
            INSERT INTO price_history (game_id, current_price, original_price, discount_percent, scanned_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (pg_game_id, p['current_price'], p['original_price'],
              p['discount_percent'], p['scanned_at']))
        prices_migrated += 1

    pg_conn.commit()
    print(f"Price history: {prices_migrated} 条迁移")

    # 迁移 price_alerts 表（如有数据）
    alerts = sqlite_conn.execute("SELECT * FROM price_alerts ORDER BY id").fetchall()
    alerts_migrated = 0

    for a in alerts:
        pg_game_id = id_map.get(a['game_id'])
        if not pg_game_id:
            continue
        pg_cur.execute("""
            INSERT INTO price_alerts (game_id, alert_type, old_price, new_price, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (pg_game_id, a['alert_type'], a['old_price'], a['new_price'], a['created_at']))
        alerts_migrated += 1

    pg_conn.commit()
    print(f"Price alerts: {alerts_migrated} 条迁移")

    # 清理
    pg_cur.close()
    pg_conn.close()
    sqlite_conn.close()
    print("\n迁移完成!")


if __name__ == '__main__':
    migrate()
