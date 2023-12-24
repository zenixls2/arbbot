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
import signal
from noexcept import lambda_noexcept, ob_noexcept, noreturn_noexcept
import coinspot
import logging
from enum import StrEnum

class OrderMode(StrEnum):
    # every time when there's a opportunity, set fixed order size as orderSizeAud
    FIXEDSIZE = "fixed_size"
    # set the hard limit as orderSizeAud.
    # if opponent order size is less than orderSizeAud, use opponent order size.
    LIMITSIZE = "limit_size"
    # free size means follow the opponent order size without limit.
    # orderSizeAud will be ignored
    FREESIZE = "free_size"

log = logging.getLogger("arbbot")

absolute_path = os.path.dirname(__file__)
sound = pyglet.media.load(os.path.join(absolute_path, "alert.mp3"), streaming=False)

trade_queue = asyncio.Queue()
ob_fetch = []
lock = threading.Lock()
interval = 1

balances = {}
balances_lock = threading.Lock()
ob_collect = {}

running = True

coinspot_usdt = {
    "id": "usdt",
    "symbol": "USDT/AUD",
    "base": "USDT",
    "quote": "AUD",
    "baseId": "usdt",
    "quoteId": "aud",
    "type": "spot",
    "spot": True,
}

strategyParam = {
    # taker fee percentage. In IR, it's 0.1%. If maker fee does exist, add it altogether.
    "feePercentage": 0.1,
    # only send order with pure profit at {profitPercentage}%,
    # with position at the best ask from exchanges other than CS
    # by default, 0.1%
    "profitPercentage": 0.1,
    # behavior setup when post an order
    "orderMode": OrderMode.LIMITSIZE,
    # order size setup. this value will be used in different cases dependens on orderMode value
    "orderSizeAud": 20,
    # on strategy start, cancel all the limit orders from previous session
    "cancelAllOnStart": True,
    # cancel non-traded order when next opportunity comes
    "cancelNonTradedOrder": True,
}


async def inner_main(configs, reverse_map, strategyConfig):

    # set parameter.
    strategyParam["profitPercentage"] = strategyConfig.get("profitPercentage", 0.1)
    strategyParam["orderMode"] = strategyConfig.get("orderMode", OrderMode.LIMITSIZE)
    strategyParam["orderSizeAud"] = strategyConfig.get("orderSizeAud", 20)
    strategyParam["cancelAllOnStart"] = strategyConfig.get("cancelAllOnStart", True)
    strategyParam["cancelNonTradedOrder"] = strategyConfig.get("cancelNonTradedOrder", True)
    strategyParam["feePercentage"] = strategyConfig.get("feePercentage", 0.1)

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
            log.error(f"skip: {e}", extra={"exchange": name})
        except ccxt.errors.NotSupported as e:
            log.error(f"api not suported: {e}", extra={"exchange": name})
        except Exception as e:
            log.error(f"exception {e}", extra={"exchange": name})

    log.info(f"{configs} {reverse_map} {strategyConfig}", extra={"exchange": "all"})


def ob_done_callback(name, data):
    best_bid_price = 0.0
    best_bid_vol = 0.0
    best_ask_price = 9999999.0
    best_ask_vol = 0.0
    with lock:
        ob_collect[name] = data
        for key in ob_collect.keys():
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
            min_margin_sell = best_ask_price * (1.0 + \
                    strategyParam["feePercentage"] / 100. + \
                    strategyParam["profitPercentage"] / 100.)
            if ask >= min_margin_sell:
                # send ask - ticksize
                chance = [
                    "coinspot",
                    ask,
                    best_ask_vol,
                ]
                log.info(f"send chance {chance}", extra={"exchange": "coinspot"})
                trade_queue.put_nowait(chance)


def _poll_orderbook(obj, time):
    global running
    if not running:
        return
    loop = asyncio.get_running_loop()
    [exchange, pair] = obj 
    loop.call_at(time + interval, _poll_orderbook, obj, time + interval)
    task = loop.create_task(ob_noexcept(exchange.fetch_order_book(pair, 20)))

    try:
        callback = lambda o: ob_done_callback(exchange.id, o.result())
        task.add_done_callback(lambda_noexcept(callback))
    except Exception as e:
        log.error(f"_poll_orderbook {str(e)}", extra={"exchange": exchange.id})


def exit_handler(exchange):
    log.info("exit handle", extra={"exchange": exchange.id})
    loop = asyncio.new_event_loop()
    loop.run_until_complete(exchange.close())


def poll_orderbook(obj):
    [exchange_cls, settings, pair] = obj

    async def runner():
        global running
        exchange = exchange_cls(settings)
        atexit.register(exit_handler, exchange)
        await exchange.load_markets()
        if exchange.id == "coinspot":
            exchange.markets["USDT/AUD"] = coinspot_usdt
        loop = asyncio.get_running_loop()
        time = loop.time()
        loop.call_soon(_poll_orderbook, [exchange, pair], time)
        while running:
            await asyncio.sleep(1)

    asyncio.run(runner())


async def name_with_aw(name, aw):
    try:
        result = await aw
        return (name, result)
    except Exception as e:
        log.error(
            "Failed to get balance %s %s",
            type(e).__name__,
            str(e),
            extra={"exchange": name},
        )
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
        for ex, pair in exchanges:
            await ex.load_markets()
            if ex.id == "coinspot":
                ex.markets["USDT/AUD"] = coinspot_usdt
                keys = ex.markets.keys()
                log.info(f"market keys {keys}", extra={"exchange": ex.id})
            info = ex.markets[pair]
            _balances[ex.id] = {}
            _balances[ex.id][info["base"]] = 0.0
            _balances[ex.id][info["quote"]] = 0.0

        with balances_lock:
            balances = copy.deepcopy(_balances)

        while running:
            aw_set = set()
            for ex, pair in exchanges:
                aw_set.add(name_with_aw(ex.id, ex.fetch_balance()))
            try:
                aw_result = await asyncio.gather(*aw_set)
            except Exception as e:
                log.error(f"get balance: {str(e)}", extra={"exchange": "all"})
                continue
            bb = dict(map(lambda x: (x[0], x[1]["total"]), aw_result))
            for ex, _ in exchanges:
                for token in _balances[ex.id].keys():
                    _balances[ex.id][token] = bb[ex.id].get(token, 0.0)
            log.info(f"write balance {_balances}", extra={"exchange": "all"})
            with balances_lock:
                balances = copy.deepcopy(_balances)

    asyncio.run(noreturn_noexcept(main_loop()))


def take_profit():
    exchanges = {}
    for [exchange_cls, settings, pair] in ob_fetch:
        exchange = exchange_cls(settings)
        exchange.verbose = False
        atexit.register(exit_handler, exchange)
        exchanges[exchange.id] = (exchange, pair)

    async def main_loop():
        global balances
        global strategyParam
        global running
        last_order_id = None
        last_price = None
        for ex, _ in exchanges.values():
            await ex.load_markets()
            if ex.id == "coinspot":
                ex.markets["USDT/AUD"] = coinspot_usdt

        if strategyParam["cancelAllOnStart"]:
            # we cancel all the active orders on the market
            await coinspot.cancel_all(*exchanges["coinspot"])

        while running:
            [e, p, v] = await trade_queue.get()
            if p == last_price:
                log.info(f"same price: {p}, skip", extra={"exchange": "coinspot"})
                continue
            last_price = p
            (exchange, pair) = exchanges[e]
            _balances = {}
            with balances_lock:
                _balances = copy.deepcopy(balances)
                log.debug(f"balances {_balances}", extra={"exchange": "all"})

            if e not in _balances:
                log.warn("balance not ready", extra={"exchange": e})
                last_price = None
                continue
            try:
                if strategyParam["cancelNonTradedOrder"]:
                    await coinspot.cancel_all(exchange, pair)

                amount_float = min(
                    _balances[e][exchange.markets[pair]["base"]] * 0.9999, v
                )
                if strategyParam["orderMode"] == OrderMode.FIXEDSIZE:
                    # if balance is not enough, error might occurr
                    amount_float = strategyParam["orderSizeAud"]
                elif strategyParam["orderMode"] == OrderMode.LIMITSIZE:
                    amount_float = min(amount_float, strategyParam["orderSizeAud"])

                if amount_float < 1:
                    log.info(
                        f"amount to trade is less than 1: {amount_float}",
                        extra={"exchange": exchange.id},
                    )
                    last_price = None
                    continue

                # normalize the order size
                sell_possible_amount = exchange.decimal_to_precision(
                    amount_float, precision=4
                )

                # if last_order_id is not None:
                #    print(f"cancel old order: {last_order_id}")
                #    # pair is not used
                #    await exchange.cancel_order(last_order_id, params={"side": "sell"})

                # tick size is actually 0.00001
                # depends on the currency
                price = exchange.decimal_to_precision(p * 0.9999, precision=4)
                log.info(
                    f"create_order at {sell_possible_amount} : {price}",
                    extra={"exchange": "coinspot"},
                )
                order = await coinspot.create_limit_sell_order(
                    exchange, pair, sell_possible_amount, price
                )
                # order = await exchange.create_limit_sell_order(pair, sell_possible_amount, price)
                log.info(
                    f"received create_order response: {order}",
                    extra={"exchange": "coinspot"},
                )
                if order["status"] == "error":
                    log.info(f"query failed {order}", extra={"exchange": "coinspot"})
                    continue
                last_order_id = order["id"]
                sound.play()
            except Exception as e:
                log.error(f"takeprofit: {str(e)}", extra={"exchange": "coinspot"})
                traceback.print_exc()

    asyncio.run(main_loop())


def main(configs, reverse_map, strategyConfig):
    running = True
    main_loop = asyncio.get_event_loop()
    main_loop.run_until_complete(inner_main(configs, reverse_map, strategyConfig))

    executor = concurrent.futures.ThreadPoolExecutor()
    
    def signal_handler(sig, frame):
        global running
        running = False
        executor.shutdown(True)

    signal.signal(signal.SIGINT, signal_handler)
    futures = set()
    for obj in ob_fetch:
        futures.add(executor.submit(poll_orderbook, obj))

    futures.add(executor.submit(take_profit))
    futures.add(executor.submit(poll_balance))

    atexit.register(executor.shutdown, False)

    for fut in futures:
        fut.result()
