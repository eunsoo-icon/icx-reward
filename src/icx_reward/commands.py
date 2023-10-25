from functools import wraps

from icx_reward.penalty import PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.types.event import EventSig
from icx_reward.types.exception import InvalidParamsException
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
    resp, start_height, end_height = get_term_height(rpc, height=args.get("height", None))
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
    _, start_height, end_height = get_term_height(rpc, height=args.get("height", None))
    address = args["address"]

    pprint(f"Find penalties of {address} from {start_height} to {end_height}")
    try:
        pf = PenaltyFetcher(rpc, address, start_height, end_height)
    except InvalidParamsException as e:
        pprint(f"{e}")
        return
    pf.run()
    pf.print_event([EventSig.Penalty, EventSig.Slash])


@use_rpc
def check(args: dict, rpc: RPC):
    # TODO
    pass


def get_term_height(rpc: RPC, height: int = None) -> (dict, int, int):
    resp = rpc.term(height)
    start_height = int(resp["startBlockHeight"], 16)
    end_height = int(resp["endBlockHeight"], 16)
    last_height = rpc.sdk.get_block("latest")["height"]
    if last_height < end_height:
        end_height = last_height
    return resp, start_height, end_height
