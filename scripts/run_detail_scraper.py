"""详情页爬取入口脚本"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import create_browser, close_browser
from src.database import init_db, get_games_without_details
from src.detail_scraper import scrape_all_details


def main():
    parser = argparse.ArgumentParser(description="爬取游戏详情页")
    parser.add_argument("--limit", type=int, default=0, help="限制爬取数量（0=全部）")
    args = parser.parse_args()

    init_db()

    games = get_games_without_details()
    if not games:
        print("所有游戏详情页已爬取完成，无需重跑。")
        return

    if args.limit > 0:
        games = games[:args.limit]

    print(f"待爬取: {len(games)} 个游戏详情页")
    print()

    browser, page = create_browser(headless=True)

    try:
        success, failed = scrape_all_details(page, games)
        print()
        print(f"完成: {success} 成功, {failed} 失败, 共 {len(games)} 个")
    finally:
        close_browser()


if __name__ == "__main__":
    main()
