"""详情页爬虫 - 爬取每个游戏的元数据（描述、类型、发行商等）"""

import re
import random
import time

SELECTORS = {
    "description": "[itemprop='description']",
    "genre": ".game_category .attribute-item-val",
    "publisher": ".publisher .attribute-item-val",
    "release_date": ".release_date .product-attribute-val",
    "languages": ".supported_languages .attribute-item-val",
    "players": ".no_of_players .product-attribute-val",
    "sale_start": ".special-period-start",
    "sale_end": ".special-period-end",
}


def _clean_players(text):
    """清理players字段，去掉图标字符，只保留如 '1 ~ 2'"""
    if not text:
        return None
    # 去掉非ASCII图标字符（如 ✕）和多余空格
    cleaned = re.sub(r'[^\d\s~～\-]', '', text).strip()
    return cleaned if cleaned else text.strip()


def _parse_release_date(text):
    """将 '2022/11/2' 格式转为 '2022-11-02'"""
    if not text:
        return None
    text = text.strip()
    match = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None


def _parse_timestamp(text):
    """将 '2026/2/11 00:00' 格式转为 '2026-02-11 00:00:00'"""
    if not text:
        return None
    text = text.strip()
    match = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d} {int(match.group(4)):02d}:{match.group(5)}:00"
    return None


async def _get_text(page, selector):
    """安全获取元素的innerText"""
    el = await page.query_selector(selector)
    if el:
        text = await el.inner_text()
        return text.strip() if text else None
    return None


def _get_text_sync(page, selector):
    """同步版本：安全获取元素的innerText"""
    el = page.query_selector(selector)
    if el:
        text = el.inner_text()
        return text.strip() if text else None
    return None


def scrape_detail_page(page, url):
    """爬取单个详情页，返回元数据字典。失败返回None。"""
    for attempt in range(2):
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_selector(".product-info-main, .product-attributes-all", timeout=60000)
            break
        except Exception as e:
            if attempt == 0:
                print(f"重试...", end=" ", flush=True)
                time.sleep(3)
            else:
                print(f"    页面加载失败: {e}")
                return None

    try:
        details = {}

        for key, selector in SELECTORS.items():
            text = _get_text_sync(page, selector)
            if text:
                if key == "players":
                    details[key] = _clean_players(text)
                elif key == "release_date":
                    details[key] = _parse_release_date(text)
                elif key in ("sale_start", "sale_end"):
                    details[key] = _parse_timestamp(text)
                else:
                    details[key] = text

        return details if details else None

    except Exception as e:
        print(f"    字段提取失败: {e}")
        return None


def scrape_all_details(page, games, delay_range=(3, 5)):
    """批量爬取所有游戏详情页，逐条写入数据库。返回 (成功数, 失败数)。"""
    from src.database import insert_game_details

    total = len(games)
    success = 0
    failed = 0

    for i, game in enumerate(games):
        name = game['name']
        url = game['url']
        game_id = game['id']

        print(f"  [{i+1}/{total}] {name} ...", end=" ", flush=True)

        details = scrape_detail_page(page, url)

        if details:
            try:
                insert_game_details(game_id, details)
                print("OK")
                success += 1
            except Exception as e:
                print(f"DB写入失败: {e}")
                failed += 1
        else:
            print("FAILED")
            failed += 1

        # 页间延迟（最后一页不延迟）
        if i < total - 1:
            delay = random.uniform(*delay_range)
            time.sleep(delay)

    return success, failed
