import concurrent.futures
import importlib
import ccxt.async_support as ccxt
import asyncio
import threading
import atexit
from noexcept import lambda_noexcept, ob_noexcept, noreturn_noexcept

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
    with lock:
        ob_collect[name] = data
        best_bid_price = 0.
        best_bid_vol = 0
        best_bid_exchange = name
        best_ask_price = 999999999.
        best_ask_vol = 0
        best_ask_exchange = name
        for key in ob_collect.keys():
            if len(ob_collect[key]["bids"]) > 0:
                [bid_price, bid_vol] = ob_collect[key]["bids"][0]
                if bid_price > best_bid_price:
                    best_bid_price = bid_price
                    best_bid_vol = bid_vol
                    best_bid_exchange = key
            if len(ob_collect[key]["asks"]) > 0:
                [ask_price, ask_vol] = ob_collect[key]["asks"][0]
                if ask_price < best_ask_price:
                    best_ask_price = ask_price
                    best_ask_vol = ask_vol
                    best_bid_exchange = key
        print(name, "best_ask", best_ask_price, "best_bid", best_bid_price)
        # in coinspot, market order fee is 0.1%
        # in IR, fee is 0
        if best_bid_price - best_ask_price > best_bid_price * 0.001 and best_bid_exchange != best_ask_exchange:
            chance = [
                best_ask_exchange, best_ask_price, best_ask_vol,
                best_bid_exchange, best_bid_price, best_bid_vol,
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
        print()
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
            balances = _balances

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
                for token in balances[ex.id].keys():
                    _balances[ex.id][token] = bb[ex.id].get(token, 0.0)
            with balances_lock:
                balances = _balances
    asyncio.run(noreturn_noexcept(main_loop()))


def take_profit():
    exchanges = {}
    for [exchange_cls, settings, pair] in ob_fetch:
        exchange = exchange_cls(settings)
        exchange.verbose = False
        atexit.register(exit_handler, exchange)
        exchanges[exchange.id] = (exchange, pair)


    async def main_loop():
        for (ex, _) in exchanges.values():
            await ex.load_markets()
            if ex.id == "coinspot":
                ex.markets["USDT/AUD"] = coinspot_usdt
        while True:
            [ae, ap, av, be, bp, bv] = await trade_queue.get()
            (aexchange, apair) = exchanges[ae]
            (bexchange, bpair) = exchanges[be]
            _balances = {}
            with balances_lock:
                _balances = balances
            buy_possible_aud = min(_balances[ae][aexchange.markets[apair]["quote"]], av * ap)
            sell_possible_aud = min(_balances[be][bexchange.markets[bpair]["base"]], bv) * bp
            arb_aud = min(buy_possible_aud, sell_possible_aud)
            arb_buy_price = ap
            arb_sell_price = bp
            arb_buy_amount = arb_aud / arb_buy_price
            arb_sell_amount = arb_aud / arb_sell_price
            print(ap, av, bp, bv)
            # TODO: check balance
            await asyncio.gather(
                noreturn_noexcept(
                    aexchange.create_limit_buy_order(apair, arb_buy_amount, arb_buy_price)),
                noreturn_noexcept(
                    bexchange.create_limit_sell_order(bpair, arb_sell_amount, arb_sell_price)))
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
