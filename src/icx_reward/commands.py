from functools import wraps

from icx_reward.penalty import PenaltyEventSig, PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.utils import pprint
from icx_reward.vote import VoteFetcher


def use_rpc(f):
    @wraps(f)
    def wrapper(args):
        return f(args, RPC(args["uri"]))

    return wrapper


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
def fetch_vote(args: dict, rpc: RPC):
    export_fp = args.get("export")
    resp = rpc.term(height=args.get("height", None))
    start_height = int(resp["startBlockHeight"], 16)
    end_height = int(resp["endBlockHeight"], 16)
    iiss_version = int(resp["iissVersion"], 16)

    if iiss_version < 4:
        pprint("Can't fetch vote. Support IISS 4 only.")
        return

    pprint(f"Fetch votes from {start_height} to {end_height}")
    vf = VoteFetcher(rpc, start_height, end_height)
    vf.run()
    if export_fp is not None:
        vf.export(export_fp)
    else:
        vf.print_result()


@use_rpc
def find_penalty(args: dict, rpc: RPC):
    resp = rpc.term(height=args.get("height", None))
    start_height = int(resp["startBlockHeight"], 16)
    end_height = int(resp["endBlockHeight"], 16)

    pprint(f"Find penalties from {start_height} to {end_height}")
    pf = PenaltyFetcher(rpc, args["address"], start_height, end_height)
    pf.run()
    pf.print_event([PenaltyEventSig.Imposed, PenaltyEventSig.Slash])


@use_rpc
def check(args: dict, rpc: RPC):
    # TODO
    pass
