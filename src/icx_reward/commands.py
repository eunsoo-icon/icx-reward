import json
from functools import wraps

from .rpc import RPC


def use_rpc(f):
    @wraps(f)
    def wrapper(args):
        return f(args, RPC(args["uri"]))

    return wrapper


def pprint(data):
    if isinstance(data, dict):
        print(json.dumps(data, indent=4))
    else:
        print(data)


@use_rpc
def query(args: dict, rpc: RPC):
    resp = rpc.query_iscore(
        address=args["address"],
        height=args.get("height", None),
    )
    pprint(resp)


@use_rpc
def term(args: dict, rpc: RPC):
    resp = rpc.term(height=args.get("height", None))
    pprint(resp)


@use_rpc
def check(args: dict, rpc: RPC):
    # TODO
    pass
