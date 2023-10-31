import sys
from functools import wraps

from icx_reward.penalty import PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.reward import PRepCalculator, Voter
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

    vf = VoteFetcher(rpc, start_height, end_height, file=sys.stdout)
    vf.run()
    if export_fp is not None:
        print(f"## Export result to {export_fp.name}")
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
    pf.print_result()


@use_rpc
def check(args: dict, rpc: RPC):
    address = args["address"]
    import_fp = args["import"]
    height = args["height"]
    term, start_height, end_height = get_term_height(rpc, height=height)
    iiss_version = int(term["iissVersion"], 16)
    if iiss_version < 4:
        pprint("Can't fetch vote. Support IISS 4 only.")
        return
    period = int(term["period"], 16)
    event_start_height = start_height - 2 * period
    event_end_height = end_height - 2 * period

    print(f"## Check reward of {address} at height {height if height is not None else 'latest'}\n")

    # get all vote events
    vf = VoteFetcher(
        rpc=rpc, start_height=event_start_height, end_height=event_end_height, import_fp=import_fp, file=sys.stdout,
    )
    vf.run()
    votes = vf.votes

    print()

    # prep reward
    pc = PRepCalculator.from_term(rpc.term(event_start_height))
    pc.run(rpc, votes)
    pc.print_summary(sys.stdout)

    print()

    # voter reward
    voter = Voter(address, votes.get(address, None), pc.start_height, pc.offset_limit(), pc.preps, sys.stdout)
    voter.update_accumulated_vote()
    voter.calculate()

    print()

    prep = pc.get_prep(address)
    reward = (0 if prep is None else prep.reward()) + voter.reward
    print(f"## Calculated reward: {reward}")
    print(f"\t= PRep.commission + PRep.wage + Voter.reward")
    print(f"\t= {0 if prep is None else prep.commission} + {0 if prep is None else prep.wage} + {voter.reward}")

    # query iscore from network
    iscore = (int(rpc.query_iscore(address, start_height + 1).get("iscore", "0x0"), 16)
              - int(rpc.query_iscore(address, start_height).get("iscore", "0x0"), 16))

    print(f"\n## Queried I-Score: {iscore}")

    if reward != iscore:
        print(f"!!!!! ERROR: Calculated and queried reward are not same. {reward} != {iscore}")


def get_term_height(rpc: RPC, height: int = None) -> (dict, int, int):
    resp = rpc.term(height)
    start_height = int(resp["startBlockHeight"], 16)
    end_height = int(resp["endBlockHeight"], 16)
    last_height = rpc.sdk.get_block("latest")["height"]
    if last_height < end_height:
        end_height = last_height
    return resp, start_height, end_height
