## Naive way of using prebuilt windows binary:

Download artifacts from the github action tab. Uzip the artifact.zip, and put `.envrc` file inside the `arbbot` folder.

```bash
coinspot_key=xxx
coinspot_secret=xxx
independentreserve_key=xxx
independentreserve_secret=xxx
```

You may also want to edit the config file, which is located in `_internal/config.yaml`. Or you could create another one in other folders and use parameter `-c {config_path}` to assign the path.

And simply run using:

```pwshell
.\arbbot.exe
```

To kill the process, Ctrl+C doesn't work. Please open `Task Manager` and find `arbbot.exe` and click on `End the task`.

## Prepare

Let's start from install poetry:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

If you are not using Unix-like environment, please follow the official manual:
[1] [https://python-poetry.org/docs/#installing-with-the-official-installer](https://python-poetry.org/docs/#installing-with-the-official-installer)
[2] [https://python-poetry.org/docs/#installing-with-pipx](https://python-poetry.org/docs/#installing-with-pipx)

And install the dependencies:

```bash
poetry install
```

## Start with poetry virtual environment

Simliar to virtualenv, run:

```bash
poetry shell
```

Create `.envrc` in the project root:

```ini
coinspot_key=****
coinspot_secret=****

independentreserve_key=****
independentreserve_secret=******
```

And run the following to start:

```bash
python arbbot
```

## Check historical trades from coinspot

```bash
python dump_trades.py

# -l LIMIT, --limit LIMIT: show latest LIMIT number of trades
# -p PAIR, --pair PAIR: show PAIR trades. If PAIR=="*", show all trades
# example:
#   python dump_trades.py -l 10 -p *
#   python dump_trades.py -l 10 -p BTC/AUD
```

## export requirements.txt

```bash
poetry export -f requirements.txt -o requirements.txt --without-h
ashes
```

## Development

Recommend to have black installed in your editor to do basic formatting.

We provide vimrc configuration here only. VS-code/pycharm users have to configure on their own.

```vimrc
call plug#begin()

Plug 'psf/black', { 'branch': 'stable' }

call plug#end()


augroup black_on_save
  autocmd!
  autocmd BufWritePre *.py Black
augroup end
```
