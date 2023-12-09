import logging
from datetime import datetime, timedelta

log = logging.getLogger('arbbot')

async def create_limit_sell_order(exchange, pair, amount, price):
    path = "v2/my/sell"
    api = "private"
    method = "POST"
    headers = None
    body = None
    info = exchange.markets[pair]
    params = {"cointype": info["base"], "amount": amount, "rate": price, "markettype": info["quote"]}
    log.debug(f"sell param: {params}", extra={'exchange': 'coinspot'})
    req = exchange.sign(path, api, method, params, headers, body)
    try:
        order = await exchange.fetch(req['url'], req['method'], req['headers'], req['body'])
        return order
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def open_orders(exchange, pair):
    path = "v2/ro/my/orders/limit/open"
    api = "private"
    method = "POST"
    headers = None
    body = None
    info = exchange.markets[pair]
    params = {"cointype": info["base"]}
    log.debug(f"open order param: {params}", extra={'exchange': 'coinspot'})
    req = exchange.sign(path, api, method, params, headers, body)
    return await exchange.fetch(req['url'], req['method'], req['headers'], req['body'])

async def completed_orders(exchange, pair):
    time_24_hours_ago = datetime.now() - timedelta(hours=24)
    time_str = time_24_hours_ago.strftime("%Y-%m-%d")
    info = exchange.markets[pair]
    path = f"v2/ro/my/orders/completed"
    api = "private"
    method = "POST"
    headers = None
    body = None
    params = {"cointype": info['base'], "markettype": info['quote'], "limit": 20, "startdate": time_str}
    req = exchange.sign(path, api, method, {}, headers, body)
    return await exchange.fetch(req['url'], req['method'], req['headers'], req['body'])

async def cancel_all(exchange, pair):
    resp = await open_orders(exchange, pair)
    if resp["status"] != "ok":
        log.error("failed to query open orders", extra={'exchange': 'coinspot'})
        return
    for order in resp["sellorders"]:
        oid = order["id"]
        log.info(f"cancel {oid}...", extra={'exchange': 'coinspot'})
        await exchange.cancel_order(oid, params={"side": "sell"})
