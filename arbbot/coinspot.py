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
    path = "v2/ro/my/orders/market/open"
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
    for order in resp["buyorders"]:
        oid = order["id"]
        log.info("cancel {oid}...", extra={'exchange': 'coinspot'})
        await exchange.cancel_order(oid, params={"side": "buy"})

if __name__ == "__main__":
    from dotenv import dotenv_values
    import ccxt.async_support as ccxt
    import asyncio
    # for test purpose, please put valid key/value pairs in .envrc
    # pattern:
    # coinspot_key=xxxxxx
    # coinspot_secret=xxxxxxxxxx
    key_secrets = dict(dotenv_values(".envrc"))
    setting = {
        "apiKey": key_secrets['coinspot_key'],
        "secret": key_secrets['coinspot_secret'],
        "enableRateLimit": True,
        "nonce": lambda: ccxt.Exchange.microseconds() * 1000,
    }
    async def run():
        ex = ccxt.coinspot(setting)
        ex.markets["USDT/AUD"] = coinspot_usdt = {
            "id": "usdt",
            "symbol": "USDT/AUD",
            "base": "USDT",
            "quote": "AUD",
            "baseId": "usdt",
            "quoteId": "aud",
            "type": "spot",
            "spot": True,
        }
        await ex.load_markets()
        value = (ex, "USDT/AUD")
        #r = await completed_orders(ex, "USDT/AUD")
        #print(r)
        #print(await ex.cancel_order("65a4b7df20c0f44a75895d7d", params={"side": "sell"}))
        #print(await create_limit_sell_order(ex, "USDT/AUD", 20, 1.55))
        #print(await open_orders(ex, "USDT/AUD"))
        #await cancel_all(*value)
        await ex.close()
    asyncio.run(run())
