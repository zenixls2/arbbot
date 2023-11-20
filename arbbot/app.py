import concurrent.futures
import importlib
import ccxt.async_support as ccxt
import asyncio
import threading
import atexit

executor = concurrent.futures.ThreadPoolExecutor()
ob_fetch = []
lock = threading.Lock()
interval = 4

ob_collect = {}


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
            ob_fetch.append([exchange_cls, setting, name, config.pair])
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
        print(ob_collect.keys())


def _poll_orderbook(obj, time):
    loop = asyncio.get_running_loop()
    [exchange, name, pair] = obj
    loop.call_at(time + interval, _poll_orderbook, obj, time + interval)
    task = loop.create_task(exchange.fetch_order_book(pair, 20))
    task.add_done_callback(lambda obj: ob_done_callback(name, obj.result()))
    print(time, "done")


def exit_handler(exchange):
    print("exit handle")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(exchange.close())


def poll_orderbook(obj):
    [exchange_cls, settings, name, pair] = obj

    async def runner():
        exchange = exchange_cls(settings)
        atexit.register(exit_handler, exchange)
        await exchange.load_markets()
        loop = asyncio.get_running_loop()
        time = loop.time()
        loop.call_soon(_poll_orderbook, [exchange, name, pair], time)
        while True:
            await asyncio.sleep(1)

    asyncio.run(runner())


def main(configs, reverse_map):
    main_loop = asyncio.get_event_loop()
    main_loop.run_until_complete(inner_main(configs, reverse_map))

    futures = set()
    for obj in ob_fetch:
        futures.add(executor.submit(poll_orderbook, obj))

    for fut in futures:
        fut.result()
