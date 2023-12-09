from dotenv import dotenv_values
from ruamel.yaml import YAML
from pathlib import Path
import argparse
import ccxt.async_support as ccxt
from config import Config
#from app import main
from first_strategy import main
import logging
import coloredlogs
import sys, os

yaml = YAML()

LOGGING_FORMAT = "%(asctime)s [%(levelname)s][%(exchange)s][%(filename)s:%(lineno)d] %(message)s"
os.environ['COLOREDLOGS_LOG_FORMAT'] = LOGGING_FORMAT
log = logging.getLogger('arbbot')
coloredlogs.install(milliseconds=True, level=logging.DEBUG, logger=log)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="arbbot", description="arbitrage bot on cryptomarkets"
    )
    parser.add_argument("-c", "--config", type=str, default="config.yaml")
    args = parser.parse_args()
    config_path = Path(args.config)

    key_secrets = dict(dotenv_values(".envrc"))
    raw_config = yaml.load(config_path)

    log.info("start program", extra={'exchange': 'all'})
    reverse_map = {}
    configs = {}
    # check
    for exchange in raw_config["exchanges"]:
        name = next(iter(exchange.keys()))
        if not name in ccxt.exchanges:
            raise Exception(f"exchange name not supported: ${name}")
        key = key_secrets[name + "_key"]
        secret = key_secrets[name + "_secret"]

        pair = exchange[name][0]
        if not pair in reverse_map:
            reverse_map[pair] = {}
            for n in raw_config["exchanges"]:
                _name, _value = next(iter(n.items()))
                reverse_map[pair][_name] = _value
        configs[name] = Config(name, key, secret, pair)
    main(configs, reverse_map)
