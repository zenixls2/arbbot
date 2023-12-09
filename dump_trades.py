import ccxt.async_support as ccxt
from ccxt.base.types import Entry
from arbbot.coinspot import completed_orders
import asyncio
from dotenv import dotenv_values
import argparse

key_secrets = dict(dotenv_values(".envrc"))
key = key_secrets["coinspot_key"]
secret = key_secrets["coinspot_secret"]

ex = ccxt.coinspot({
    "apiKey": key,
    "secret": secret,
    "enableRateLimit": True,
    "nonce": lambda: ccxt.Exchange.milliseconds(),
    })


"""
format:
    {'coin': 'USDT', 'rate': '1.563927', 'market': 'USDT/AUD', 'amount': '0.00899998', 'type': 'instant', 'otc': False, 'solddate': '2023-11-11T06:12:46.321Z', 'total': '0.01407531172146', 'audfeeExGst': '0.00012925', 'audGst': '0.00001292', 'audtotal': '0.01'}
"""

async def main(pair, limit): 
    await ex.load_markets()
    ex.markets["USDT/AUD"] = {'id': 'usdt', 'symbol': 'USDT/AUD', 'base': 'USDT', 'quote': 'AUD', 'baseId': 'usdt', 'quoteId': 'aud', 'active': None, 'type': 'spot', 'linear': None, 'inverse': None, 'spot': True, 'swap': False, 'future': False, 'option': False, 'margin': None, 'contract': False, 'contractSize': None, 'expiry': None, 'expiryDatetime': None, 'optionType': None, 'strike': None, 'settle': None, 'settleId': None, 'precision': {'amount': None, 'price': None, 'cost': None, 'base': None, 'quote': None}, 'limits': {'amount': {'min': None, 'max': None}, 'price': {'min': None, 'max': None}, 'cost': {'min': None, 'max': None}, 'leverage': {'min': None, 'max': None}}, 'info': None, 'percentage': True, 'lowercaseId': None, 'index': False, 'taker': None, 'maker': None, 'created': None}
    result = await completed_orders(ex, pair)
    await ex.close()
    if result["status"] != "ok":
        return

    print("buyorders:")
    counter = 0
    for order in result["buyorders"]:
        if pair != "*" and order['market'] != pair:
            continue
        if counter >= limit:
            break
        counter += 1
        print("\t", order['market'], order['solddate'], order['rate'], order['amount'], order['audGst'])


    print("sellorders:")
    counter = 0
    for order in result["sellorders"]:
        if pair != "*" and order['market'] != pair:
            continue
        if counter >= limit:
            break
        counter += 1
        print("\t", order['market'], order['solddate'], order['rate'], order['amount'], order['audGst'])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
            prog="trade_dump", description="dump trades from coinspot exchange")
    parser.add_argument("-l", "--limit", type=int, default="100")
    parser.add_argument("-p", "--pair", type=str, default="USDT/AUD")
    args = parser.parse_args()
    asyncio.run(main(args.pair, args.limit))
