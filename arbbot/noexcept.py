def lambda_noexcept(func):
    def _wrapper(o):
        try:
            func(o)
        except Exception as e:
            print("exception in ccxt: ", type(e).__name__, str(e))
            return
    return _wrapper

async def ob_noexcept(aw):
    try:
        result = await aw
        return result
    except Exception as e:
        print("Failed to get ob", type(e).__name__, str(e))
        return {"bids": [], "asks": []}

async def noreturn_noexcept(aw):
    resp = None
    try:
        resp = await aw
    except Exception as e:
        print("Failed to run", type(e).__name__, str(e))
        return
    print(resp)
