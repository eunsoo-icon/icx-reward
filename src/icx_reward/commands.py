import sys
from functools import wraps

from icx_reward.penalty import PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.reward import PRepReward, Voter
from icx_reward.types.term import Term
from icx_reward.types.exception import InvalidParamsException
from icx_reward.utils import pprint
from icx_reward.vote import VoteFetcher


def time_info(f):
    @wraps(f)
    def wrapper(args):
        rpc = RPC(args["uri"])
        height = args.get("height", None)
        seq_in = args.get("term", None)
        term_ = rpc.term()
        if height is not None:
            term_ = rpc.term(height=height)
        elif seq_in is not None:
            seq_last = int(term_["sequence"], 16)
            if seq_in > seq_last:
                raise InvalidParamsException(f"Too big Term sequence {seq_in}")
            elif seq_in == seq_last:
                height = int(term_["startBlockHeight"], 16)
            else:
                if seq_in < 0:
                    diff = -seq_in
                else:
                    diff = seq_last - seq_in
                period = int(term_["period"], 16)
                start_height = int(term_["startBlockHeight"], 16)
                height = start_height - period * diff
                print(f"in {seq_in} diff {diff} height {height}")
                term_ = rpc.term(height=height)
        else:
            height = int(term_["startBlockHeight"], 16)

        return f(args, height, term_)

    return wrapper


@time_info
def query(args: dict, height: int, term_: dict):
    rpc = RPC(args["uri"])
    resp = rpc.query_iscore(
        address=args["address"],
        height=height,
    )
    pprint(resp)


@time_info
def term(args: dict, height: int, term_: dict):
    pprint(term_)


@time_info
def fetch_vote(args: dict, height: int, term_: dict):
    uri = args["uri"]
    export_fp = args.get("export")
    address = args["address"]
    t = Term.from_dict(term_)

    if t.iiss_version < 4:
        pprint("Can't fetch vote. Support IISS 4 only.")
        return

    pprint(f"## Fetch votes of {'all' if address is None else address} in {t.info()}")
    vf = VoteFetcher(uri)
    vf.fetch(t.start_block_height, t.end_block_height, address, fp=sys.stdout)
    if export_fp is not None:
        print(f"## Export result to {export_fp.name}")
        vf.export(export_fp)
    else:
        vf.print_result()


@time_info
def fetch_penalty(args: dict, height: int, term_: dict):
    address = args["address"]
    t = Term.from_dict(term_)

    pprint(f"## Fetch penalties of {'all' if address is None else address} in {t.info()}")
    pf = PenaltyFetcher(args["uri"])
    try:
        penalties = pf.run(t.start_block_height, t.end_block_height, address, True)
    except InvalidParamsException as e:
        pprint(f"{e}")
        return

    print()
    for height, penalty in penalties.items():
        pprint(f"{penalty}")


@time_info
def check(args: dict, height: int, term_: dict):
    uri = args["uri"]
    address = args["address"]
    import_fp = args["import"]
    t = Term.from_dict(term_)

    if t.iiss_version < 4:
        pprint("Support IISS 4 only.")
        return

    rpc = RPC(uri)
    et = Term.from_dict(rpc.term(t.start_block_height - 2 * t.period))

    print(f"## Check reward of {address} at height {height}\n")

    # get all vote events
    vf = VoteFetcher(uri)
    if import_fp is None:
        print(f"## Fetch all votes in {et.info()}")
        vf.fetch(et.start_block_height, et.end_block_height, fp=sys.stdout)
    else:
        print(f"## Import votes from {import_fp.name}")
        vf.import_from_file(import_fp)
    vf.update_votes_for_reward()

    print()

    # prep reward
    pr = PRepReward.from_network(uri, et.start_block_height)
    print(f"## Calculate reward of elected PReps in {et.info()}")
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
    iscore = (int(rpc.query_iscore(address, t.start_block_height + 1).get("iscore", "0x0"), 16)
              - int(rpc.query_iscore(address, t.start_block_height).get("iscore", "0x0"), 16))

    print(f"\n## Queried I-Score: {iscore}")

    if reward != iscore:
        print(f"!!!!! ERROR: Calculated and queried reward are not same. {reward} != {iscore}")
