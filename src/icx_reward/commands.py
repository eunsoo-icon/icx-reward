import sys
from functools import wraps

from icx_reward.penalty import PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.reward import PRepReward, Voter
from icx_reward.types.exception import InvalidParamsException
from icx_reward.utils import pprint
from icx_reward.vote import VoteFetcher


def use_rpc(f):
    @wraps(f)
    def wrapper(args):
        return f(args, RPC(args["uri"]))

    return wrapper


def use_term_info(f):
    @wraps(f)
    def wrapper(args):
        rpc = RPC(args["uri"])
        resp = rpc.term(args.get("height", None))
        start_height = int(resp["startBlockHeight"], 16)
        end_height = int(resp["endBlockHeight"], 16)
        last_height = rpc.sdk.get_block("latest")["height"]
        if last_height < end_height:
            end_height = last_height
        return f(args, resp, start_height, end_height)

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
    uri = args["uri"]
    export_fp = args.get("export")
    address = args["address"]
    resp, start_height, end_height = get_term_height(rpc, height=args.get("height", None))
    iiss_version = int(resp["iissVersion"], 16)

    if iiss_version < 4:
        pprint("Can't fetch vote. Support IISS 4 only.")
        return

    pprint(f"## Fetch votes of {'all' if address is None else address} from {start_height} to {end_height}")
    vf = VoteFetcher(uri)
    vf.fetch(start_height, end_height, address, fp=sys.stdout)
    if export_fp is not None:
        print(f"## Export result to {export_fp.name}")
        vf.export(export_fp)
    else:
        vf.print_result()


@use_term_info
def fetch_penalty(args: dict, _term: dict, start_height: int, end_height: int):
    address = args["address"]

    pprint(f"## Fetch penalties of {address} from {start_height} to {end_height}")
    pf = PenaltyFetcher(args["uri"])
    try:
        penalties = pf.run(start_height, end_height, address, True)
    except InvalidParamsException as e:
        pprint(f"{e}")
        return

    print()
    for height, penalty in penalties.items():
        pprint(f"{penalty}")


@use_rpc
def check(args: dict, rpc: RPC):
    uri = args["uri"]
    address = args["address"]
    import_fp = args["import"]
    height = args["height"]
    term, start_height, end_height = get_term_height(rpc, height=height)
    iiss_version = int(term["iissVersion"], 16)
    if iiss_version < 4:
        pprint("Support IISS 4 only.")
        return
    period = int(term["period"], 16)
    event_start_height = start_height - 2 * period
    event_end_height = end_height - 2 * period

    print(f"## Check reward of {address} at height {height if height is not None else 'latest'}\n")

    # get all vote events
    vf = VoteFetcher(uri)
    if import_fp is None:
        print(f"## Fetch all votes from {event_start_height} to {event_end_height}")
        vf.fetch(event_start_height, event_end_height, fp=sys.stdout)
    else:
        print(f"## Import votes from {import_fp.name}")
        vf.import_from_file(import_fp)
    vf.update_votes_for_reward()

    print()

    # prep reward
    pr = PRepReward.from_network(uri, event_start_height)
    print(f"## Calculate reward of elected PReps from {pr.start_height} to {pr.end_height}")
    pr.calculate(vf.votes)
    pr.print_summary()

    print()

    # voter reward
    voter = Voter(address, vf.votes_for_voter_reward(address), pr.start_height, pr.offset_limit(), pr.preps, sys.stdout)
    voter.calculate()

    print()

    prep = pr.get_prep(address)
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
