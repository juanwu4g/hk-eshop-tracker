from src.database import get_latest_price


def detect_changes(game_id, new_price, new_original):
    """对比新旧价格，返回alert列表"""
    alerts = []
    latest = get_latest_price(game_id)

    # 首次记录，无alert
    if latest is None:
        return alerts

    old_price = latest['current_price']
    old_original = latest['original_price']

    # 判断折扣状态
    had_discount = old_original is not None and old_original > old_price
    has_discount = new_original is not None and new_original > new_price

    if not had_discount and has_discount:
        # 无折扣 → 有折扣
        alerts.append({
            'game_id': game_id,
            'alert_type': 'new_sale',
            'old_price': old_price,
            'new_price': new_price,
        })
    elif had_discount and not has_discount:
        # 有折扣 → 无折扣
        alerts.append({
            'game_id': game_id,
            'alert_type': 'sale_ended',
            'old_price': old_price,
            'new_price': new_price,
        })
    elif new_price < old_price:
        # 价格降低
        alerts.append({
            'game_id': game_id,
            'alert_type': 'price_drop',
            'old_price': old_price,
            'new_price': new_price,
        })
    elif new_price > old_price:
        # 价格升高
        alerts.append({
            'game_id': game_id,
            'alert_type': 'price_increase',
            'old_price': old_price,
            'new_price': new_price,
        })

    return alerts
