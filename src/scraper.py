from src.config import BASE_URL, LIST_URL_TEMPLATE
from src.browser import navigate, wait_between_pages


JS_EXTRACT_ITEMS = """
(() => {
    var items = document.querySelectorAll('.products-grid .product-item');
    var data = [];
    items.forEach(function(item) {
        var name = item.querySelector('.product-item-link')?.textContent?.trim();
        var finalPrice = item.querySelector('.price-final_price [data-price-amount]')?.getAttribute('data-price-amount');
        var oldPrice = item.querySelector('.old-price [data-price-amount]')?.getAttribute('data-price-amount');
        var url = item.querySelector('.product-item-link')?.href;
        var img = item.querySelector('.product-image-photo')?.src;
        var pid = item.querySelector('[data-price-box]')?.getAttribute('data-price-box');
        if(name) data.push({name, finalPrice, oldPrice, url, img, pid});
    });
    return data;
})()
"""


def scrape_page(page):
    """从当前已加载的页面提取商品列表"""
    return page.evaluate(JS_EXTRACT_ITEMS)


def scrape_all_pages(page, max_pages=None):
    """遍历所有列表页，返回去重后的全部商品"""
    all_games = []
    seen_urls = set()
    page_num = 1

    while True:
        if max_pages and page_num > max_pages:
            break

        url = BASE_URL + LIST_URL_TEMPLATE.format(page=page_num)
        print(f"正在爬取第{page_num}页...")

        ok = navigate(page, url)
        if not ok:
            print(f"  第{page_num}页加载失败，跳过")
            break

        items = scrape_page(page)
        print(f"  本页{len(items)}个商品")

        if len(items) == 0:
            break

        for item in items:
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                all_games.append(item)

        if len(items) < 48:
            break

        page_num += 1
        wait_between_pages()

    print(f"爬取完成，共{len(all_games)}个商品（去重后）")
    return all_games
