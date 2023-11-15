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
