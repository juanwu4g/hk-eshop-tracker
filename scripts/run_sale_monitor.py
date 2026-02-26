#!/usr/bin/env python3
"""HK eShop 减价页监控 - 每6小时检查折扣变化"""

import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import BASE_URL, SALE_URL
from src.database import (
    init_db, upsert_game, insert_price,
    get_latest_price_by_eshop_id, save_alerts,
)
from src.browser import create_browser, navigate, close_browser
from src.scraper import scrape_page
from src.price_tracker import detect_changes


def parse_price(value):
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def main():
    init_db()

    print("启动浏览器...")
    browser, page = create_browser(headless=True)

    try:
        url = BASE_URL + SALE_URL
        print(f"正在爬取减价页: {url}")

        ok = navigate(page, url)
        if not ok:
            print("减价页加载失败")
            return

        items = scrape_page(page)
        print(f"减价页共 {len(items)} 个商品")

        stats = {'total': 0, 'new_sale': 0, 'sale_ended': 0,
                 'price_drop': 0, 'price_increase': 0}

        for game in items:
            current_price = parse_price(game.get('finalPrice'))
            original_price = parse_price(game.get('oldPrice'))

            if current_price is None:
                continue

            game_id = upsert_game(game)
            alerts = detect_changes(game_id, current_price, original_price)
            insert_price(game_id, current_price, original_price)
            save_alerts(alerts)

            stats['total'] += 1
            for a in alerts:
                t = a['alert_type']
                if t in stats:
                    stats[t] += 1

        # 打印摘要
        price_changes = stats['new_sale'] + stats['sale_ended'] + stats['price_drop'] + stats['price_increase']
        print(f"\n减价页监控完成")
        print(f"折扣商品数: {stats['total']}")
        print(f"价格变动: {price_changes} ({stats['new_sale']}个新折扣, {stats['sale_ended']}个折扣结束, {stats['price_drop'] + stats['price_increase']}个价格变动)")

    finally:
        close_browser()


if __name__ == '__main__':
    main()
