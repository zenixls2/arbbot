import importlib
import ccxt


async def main(configs, reverse_map):
    for name, config in configs.items():
        module = importlib.import_module("ccxt." + name)
        exchange_cls = getattr(module, name)
        print(ccxt.Exchange.milliseconds())
        try:
            exchange = exchange_cls(
                {
                    "apiKey": config.key,
                    "secret": config.secret,
                    "enableRateLimit": True,
                    "nonce": lambda: ccxt.Exchange.microseconds() * 1000,
                }
            )
            balance = exchange.fetch_balance()
            print(f"{exchange} {balance}")
        except ccxt.errors.AuthenticationError as e:
            print(f"skip: {e}")
        except ccxt.errors.NotSupported as e:
            print(f"api not suported: {e}")
    print(f"hello {configs} {reverse_map}")
