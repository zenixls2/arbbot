import concurrent.futures
import importlib
import ccxt.async_support as ccxt
import asyncio
import threading
import atexit
import copy
import traceback
import pyglet
import os
from noexcept import lambda_noexcept, ob_noexcept, noreturn_noexcept

absolute_path = os.path.dirname(__file__)
sound = pyglet.media.load(os.path.join(absolute_path, "..", "alert.mp3"), streaming=False)

trade_queue = asyncio.Queue()
executor = concurrent.futures.ThreadPoolExecutor()
ob_fetch = []
lock = threading.Lock()
interval = 1

balances = {}
balances_lock = threading.Lock()
ob_collect = {}

coinspot_usdt = {'id': 'usdt', 'symbol': 'USDT/AUD', 'base': 'USDT', 'quote': 'AUD', 'baseId': 'usdt', 'quoteId': 'aud', 'type': 'spot', 'spot': True}

async def inner_main(configs, reverse_map):
    for name, config in configs.items():
        module = importlib.import_module("ccxt.async_support")
        exchange_cls = getattr(module, name)
        try:
            setting = {
                "apiKey": config.key,
                "secret": config.secret,
                "enableRateLimit": True,
                "nonce": lambda: ccxt.Exchange.microseconds() * 1000,
            }
            ob_fetch.append([exchange_cls, setting, config.pair])
        except ccxt.errors.AuthenticationError as e:
            print(f"skip: {e}")
        except ccxt.errors.NotSupported as e:
            print(f"api not suported: {e}")
        except Exception as e:
            print(f"exception {e}")

    print(f"hello {configs} {reverse_map}")


def ob_done_callback(name, data):
    best_bid_price = 0.
    best_bid_vol = 0.
    best_ask_price = 9999999.
    best_ask_vol = 0.
    with lock:
        ob_collect[name] = data
        for key in ob_collect.keys():
            print(key)
            if len(ob_collect[key]["bids"]) > 0:
                [bid_price, bid_vol] = ob_collect[key]["bids"][0]
                if best_bid_price < bid_price:
                    best_bid_price = bid_price
                    best_bid_vol = bid_vol
            if len(ob_collect[key]["asks"]) > 0:
                [ask_price, ask_vol] = ob_collect[key]["asks"][0]
                if best_ask_price > ask_price:
                    best_ask_price = ask_price
                    best_ask_vol = ask_vol

    if name == "coinspot":
        if len(data["asks"]) > 0:
            [ask, _] = data["asks"][0]
            [bid, _] = data["bids"][0]
            # 0.1% of trading fee
            # we want to buy at best ask price
            min_margin_sell = best_ask_price * 1.0001
            if ask > min_margin_sell:
                # send ask - ticksize
                chance = [
                    "coinspot", ask, best_ask_vol,
                ]
                print("send chance", chance)
                trade_queue.put_nowait(chance)
        

def _poll_orderbook(obj, time):
    loop = asyncio.get_running_loop()
    [exchange, pair] = obj
    loop.call_at(time + interval, _poll_orderbook, obj, time + interval)
    task = loop.create_task(ob_noexcept(exchange.fetch_order_book(pair, 20)))

    try:
        callback = lambda o: ob_done_callback(exchange.id, o.result())
        task.add_done_callback(lambda_noexcept(callback))
    except Exception as e:
        print(f"_poll_orderbook {str(e)}")
    print(time, "done")


def exit_handler(exchange):
    print("exit handle")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(exchange.close())


def poll_orderbook(obj):
    [exchange_cls, settings, pair] = obj

    async def runner():
        exchange = exchange_cls(settings)
        atexit.register(exit_handler, exchange)
        await exchange.load_markets()
        if exchange.id == "coinspot":
            exchange.markets["USDT/AUD"] = coinspot_usdt
        loop = asyncio.get_running_loop()
        time = loop.time()
        loop.call_soon(_poll_orderbook, [exchange, pair], time)
        while True:
            await asyncio.sleep(1)

    asyncio.run(runner())

async def name_with_aw(name, aw):
    try:
        result = await aw
        return (name, result)
    except Exception as e:
        print("Failed to get balance", type(e).__name__, str(e))
        return (name, None)

def poll_balance():
    exchanges = []
    for [exchange_cls, settings, pair] in ob_fetch:
        exchange = exchange_cls(settings)
        exchange.verbose = False
        atexit.register(exit_handler, exchange)
        exchanges.append((exchange, pair))

    async def main_loop():
        global balances
        _balances = {}
        for (ex, pair) in exchanges:
            await ex.load_markets()
            if ex.id == "coinspot":
                ex.markets["USDT/AUD"] = coinspot_usdt
                print(ex.markets.keys())
            info = ex.markets[pair]
            _balances[ex.id] = {}
            _balances[ex.id][info["base"]] = 0.
            _balances[ex.id][info["quote"]] = 0.

        with balances_lock:
            balances = copy.deepcopy(_balances)

        while True:
            aw_set = set()
            for (ex, pair) in exchanges:
                aw_set.add(name_with_aw(ex.id, ex.fetch_balance()))
            try:
                aw_result = await asyncio.gather(*aw_set)
            except Exception as e:
                print(f"get balance: {str(e)}")
                continue
            bb = dict(map(lambda x: (x[0], x[1]["total"]), aw_result))
            for (ex, _) in exchanges:
                for token in _balances[ex.id].keys():
                    _balances[ex.id][token] = bb[ex.id].get(token, 0.0)
            print(f"write balance {_balances}")
            with balances_lock:
                balances = copy.deepcopy(_balances)
    asyncio.run(noreturn_noexcept(main_loop()))

async def create_limit_sell_order(exchange, pair, amount, price):
    path = "v2/my/sell"
    api = "private"
    method = "POST"
    headers = None
    body = None
    info = exchange.markets[pair]
    params = {"cointype": info["base"], "amount": amount, "rate": price, "markettype": info["quote"]}
    print(f"sell param: {params}")
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
    print(f"open order param: {params}")
    req = exchange.sign(path, api, method, params, headers, body)
    return await exchange.fetch(req['url'], req['method'], req['headers'], req['body'])


async def cancel_all(exchange, pair):
    resp = await open_orders(exchange, pair)
    if resp["status"] != "ok":
        print("failed to query open orders")
        return
    for order in resp["sellorders"]:
        oid = order["id"]
        print(f"cancel {oid}...")
        await exchange.cancel_order(oid, params={"side": "sell"})

def take_profit():
    exchanges = {}
    for [exchange_cls, settings, pair] in ob_fetch:
        exchange = exchange_cls(settings)
        exchange.verbose = False
        atexit.register(exit_handler, exchange)
        exchanges[exchange.id] = (exchange, pair)


    async def main_loop():
        global balances
        last_order_id = None
        last_price = None
        for (ex, _) in exchanges.values():
            await ex.load_markets()
            if ex.id == "coinspot":
                ex.markets["USDT/AUD"] = coinspot_usdt
        while True:
            [e, p, v] = await trade_queue.get()
            if p == last_price:
                print("same price, skip")
                continue
            last_price = p
            (exchange, pair) = exchanges[e]
            _balances = {}
            with balances_lock:
                _balances = copy.deepcopy(balances)
                print(f"balances {_balances}")

            if e not in _balances:
                print("balance not ready")
                last_price = None
                continue
            try:
                amount_float = min(_balances[e][exchange.markets[pair]["base"]]-0.0001, v)
                if amount_float < 1:
                    continue
                sell_possible_amount = exchange.decimal_to_precision(
                        amount_float, precision=4)
                
                #if last_order_id is not None:
                #    print(f"cancel old order: {last_order_id}")
                #    # pair is not used
                #    await exchange.cancel_order(last_order_id, params={"side": "sell"})

                await cancel_all(exchange, pair)

                # tick size is actually 0.00001
                price = exchange.decimal_to_precision(p-0.0001, precision=4)
                print(f"create_order at {sell_possible_amount} : {price}")
                order = await create_limit_sell_order(exchange, pair, sell_possible_amount, price)
                #order = await exchange.create_limit_sell_order(pair, sell_possible_amount, price)
                print(f"received create_order response: {order}")
                if order["status"] == "error":
                    print(f"query failed {order}")
                    continue
                last_order_id = order["id"]
                sound.play()
            except Exception as e:
                print(f"takeprofit: {str(e)}")
                traceback.print_exc()
    asyncio.run(main_loop())
        


def main(configs, reverse_map):
    main_loop = asyncio.get_event_loop()
    main_loop.run_until_complete(inner_main(configs, reverse_map))

    futures = set()
    for obj in ob_fetch:
        futures.add(executor.submit(poll_orderbook, obj))

    futures.add(executor.submit(take_profit))
    futures.add(executor.submit(poll_balance))

    for fut in futures:
        fut.result()
