#!/usr/bin/env python3
"""HK eShop 减价页监控 - 每6小时检查折扣变化"""

import signal
import sys
import os

GLOBAL_TIMEOUT = 300  # 5分钟全局超时

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import BASE_URL
from src.database import (
    init_db, upsert_game, insert_price, save_alerts,
)
from src.browser import create_browser, close_browser
from src.scraper import scrape_all_pages
from src.price_tracker import detect_changes

SALE_URL_TEMPLATE = BASE_URL + "/download-code/sale?product_list_limit=48&p={page}"


def parse_price(value):
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _timeout_handler(signum, frame):
    print(f"\n❌ 全局超时（{GLOBAL_TIMEOUT}秒），强制退出")
    close_browser()
    sys.exit(2)


def main():
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(GLOBAL_TIMEOUT)

    init_db()

    print("启动浏览器...")
    browser, page = create_browser(headless=True)

    try:
        print("正在爬取减价页（所有页面）...")
        items = scrape_all_pages(page, url_template=SALE_URL_TEMPLATE)

        if len(items) == 0:
            print("❌ 减价页无商品，可能加载失败")
            sys.exit(1)

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
        signal.alarm(0)
        close_browser()


if __name__ == '__main__':
    main()
