import random
import time
from playwright.sync_api import sync_playwright
from src.config import MIN_DELAY, MAX_DELAY


_playwright = None
_browser = None


def create_browser(headless=True):
    """启动Chromium浏览器，返回 (browser, page)"""
    global _playwright, _browser
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=headless)
    page = _browser.new_page(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    return _browser, page


def navigate(page, url):
    """导航到指定URL，等待WAF challenge通过并确认商品列表加载。失败重试一次。"""
    for attempt in range(2):
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_selector(".products-grid", timeout=30000)
            return True
        except Exception as e:
            if attempt == 0:
                print(f"  页面加载失败，重试中... ({e})")
                time.sleep(3)
            else:
                print(f"  页面加载失败，跳过: {e}")
                return False


def wait_between_pages():
    """页面间随机延迟"""
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    time.sleep(delay)


def close_browser():
    """关闭浏览器和Playwright"""
    global _playwright, _browser
    if _browser:
        _browser.close()
        _browser = None
    if _playwright:
        _playwright.stop()
        _playwright = None
