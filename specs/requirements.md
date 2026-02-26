# HK eShop Price Tracker - Phase 1: 数据采集器

## 项目定位

学习项目，以产品标准执行。当前阶段目标：构建一个可靠的数据采集器，每日抓取香港Nintendo eShop的游戏价格数据并存入数据库。

## 数据源

### 目标网站：store.nintendo.com.hk

- Magento电商平台，服务端渲染（SSR）
- 反爬机制：AWS WAF JavaScript Challenge
  - HTTP响应：`202` + `x-amzn-waf-action: challenge`
  - 返回一段JS脚本（`challenge.js`），浏览器执行后获取token并自动刷新页面
  - 简单HTTP请求（curl/requests/fetch）均无法通过，必须使用真实浏览器引擎
- 采集方式：**Playwright**（无头浏览器）

### 已验证可用的页面和数据

#### 列表页

URL模板：`/download-code?label_platform=4580&p={page}&product_list_limit=48`

实测结果（2025-02-24）：
- `product_list_limit` 支持 12、24、48 三个值（页面有toggle按钮），我们用48减少翻页次数
- 当前总计约1000个游戏（~21页 × 48个/页）
- 减价专区 `/download-code/sale` 当前有24个折扣商品

列表页可提取的字段（已用浏览器Console验证）：

| 字段 | CSS选择器 | 示例值 |
|------|----------|--------|
| 游戏名称 | `.product-item-link` textContent | 數碼寶貝物語 時空異客 |
| 当前价格 | `.price-final_price [data-price-amount]` | 399 |
| 原价 | `.old-price [data-price-amount]` | 458（无折扣时为null） |
| 商品URL | `.product-item-link` href | https://store.nintendo.com.hk/70010000065203 |
| 封面图 | `.product-image-photo` src | (图片URL) |
| 产品ID | `[data-price-box]` data-price-box | product-id-32240 |

验证用的JS代码（在浏览器Console中运行成功）：
```javascript
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
```

#### 详情页（仅供参考，Phase 1暂不爬取）

URL模式：`/{eshop_id}`（如 `/70010000065203`）

详情页包含额外字段：SKU、发售日、厂商、游戏类型、语言、平台、容量、描述。还包含一个Magento JSON对象，其中 `special_price` 有值时表示正在打折。详情页爬取留到后续Phase。

### 已验证不可用的数据源

| 尝试 | 结果 | 结论 |
|------|------|------|
| `ec.nintendo.com/api/HK/zh/search/sales` | 404 HTML错误页 | API已关闭 |
| `amasty_xsearch/autocomplete/index/?q=mario` | 403 | 被WAF拦截 |
| `curl` 带User-Agent直接请求列表页 | 202 + 0 bytes body | WAF challenge，无法绕过 |

## Phase 1 功能需求

1. **Playwright浏览器管理**：启动浏览器、通过AWS WAF challenge、控制请求节奏
2. **列表页爬虫**：遍历所有页面（p=1到最后一页），提取每个游戏的名称、价格（含折扣）、URL、图片
3. **数据持久化**：将游戏信息和价格快照存入SQLite数据库
4. **价格变动检测**：对比本次扫描与上次的价格，识别新折扣/价格变动
5. **可重复执行**：脚本可每天运行，增量更新数据

## 非功能需求

- 每页间隔3-5秒随机延迟，避免被封
- 支持headless和有头两种模式（调试用有头，生产用headless）
- 遇到错误能优雅处理（单页失败不影响其他页）
- 日志输出当前进度（正在爬第X页，共找到Y个游戏）
