#!/usr/bin/env python3
"""HK eShop Price Tracker - 每日扫描入口"""

import argparse
import re
import sys
import os

# 确保项目根目录在path中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import (
    init_db, upsert_game, insert_price,
    get_latest_price_by_eshop_id, save_alerts,
)
from src.browser import create_browser, close_browser
from src.scraper import scrape_all_pages
from src.price_tracker import detect_changes


def parse_price(value):
    """将价格字符串转为float，无效返回None"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description='HK eShop 价格扫描')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='无头模式运行（默认True）')
    parser.add_argument('--no-headless', action='store_true',
                        help='有头模式运行（调试用）')
    parser.add_argument('--pages', type=int, default=None,
                        help='限制爬取页数（调试用）')
    args = parser.parse_args()

    headless = not args.no_headless

    # 1. 初始化数据库
    init_db()

    # 2. 启动浏览器
    print("启动浏览器...")
    browser, page = create_browser(headless=headless)

    try:
        # 3. 爬取所有页面
        all_games = scrape_all_pages(page, max_pages=args.pages)

        # 3.5 扫描结果异常检测
        if len(all_games) < 100 and args.pages is None:
            print(f"⚠️ 警告：本次只扫描到 {len(all_games)} 个游戏，可能是网站结构变化或被封，请手动检查")
            sys.exit(1)

        # 4. 处理每个游戏
        stats = {'total': 0, 'new': 0, 'new_sale': 0, 'sale_ended': 0,
                 'price_drop': 0, 'price_increase': 0}

        for game in all_games:
            current_price = parse_price(game.get('finalPrice'))
            original_price = parse_price(game.get('oldPrice'))

            if current_price is None:
                continue

            # a. 判断是否新游戏
            match = re.search(r'/(\d{10,})$', game['url'])
            eshop_id = match.group(1) if match else None
            is_new = (eshop_id and get_latest_price_by_eshop_id(eshop_id) is None)

            # b. upsert游戏信息
            game_id = upsert_game(game)

            # c. 检测价格变动
            alerts = detect_changes(game_id, current_price, original_price)

            # d. 插入价格记录
            insert_price(game_id, current_price, original_price)

            # e. 保存alerts
            save_alerts(alerts)

            # 统计
            stats['total'] += 1
            if is_new:
                stats['new'] += 1
            for a in alerts:
                t = a['alert_type']
                if t in stats:
                    stats[t] += 1

        # 5. 打印统计
        price_changes = stats['new_sale'] + stats['sale_ended'] + stats['price_drop'] + stats['price_increase']
        print(f"\n扫描完成")
        print(f"总游戏数: {stats['total']}")
        print(f"新增游戏: {stats['new']}")
        print(f"价格变动: {price_changes} ({stats['new_sale']}个新折扣, {stats['sale_ended']}个折扣结束, {stats['price_drop'] + stats['price_increase']}个价格变动)")

    finally:
        # 6. 关闭浏览器
        close_browser()


if __name__ == '__main__':
    main()
