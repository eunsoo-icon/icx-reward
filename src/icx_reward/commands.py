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

    print(f"## Check reward of {address} at height {t.start_block_height + 1}\n")

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

    print(f"## Fetch all penalties in {et.info()}")
    pf = PenaltyFetcher(uri)
    penalties = pf.run(et.start_block_height, et.end_block_height, progress=True)

    print()

    # prep reward
    pr = PRepReward.from_network(uri, et.start_block_height)
    print(f"## Calculate reward of elected PReps in {et.info()}")
    pr.calculate(vf.votes, penalties)
    pr.print_summary()

    print()

    # voter reward
    voter = Voter(address, vf.votes_for_voter_reward(address), pr.start_height, pr.offset_limit(), pr.preps, sys.stdout)
    voter.calculate()

    print()

    print(f"## Calculated reward")
    prep = pr.get_prep(address)
    reward = (0 if prep is None else prep.reward()) + voter.reward
    print_reward(prep, voter)

    # query iscore from network
    iscore = (int(rpc.query_iscore(address, t.start_block_height + 1).get("iscore", "0x0"), 16)
              - int(rpc.query_iscore(address, t.start_block_height).get("iscore", "0x0"), 16))

    print(f"\n## Queried I-Score is{' not ' if reward != iscore else ' '}same with calculated value")
    if reward != iscore:
        print(f"\tcalculated {format_int(reward)}")
        print(f"\tqueried    {format_int(iscore)}")


@time_info
def estimate(args: dict, height: int, term_: dict):
    uri = args["uri"]
    address = args["address"]
    t = Term.from_dict(term_)
    if t.iiss_version < 4:
        pprint("Support IISS 4 only.")
        return

    rpc = RPC(uri)
    current_height = rpc.sdk.get_block("latest")["height"]
    bond = rpc.get_bond(address, current_height)
    delegation = rpc.get_delegation(address, current_height)
    prep = rpc.get_prep(address, current_height)
    total_votes = int(bond["totalBonded"], 16) + int(delegation["totalDelegated"], 16)
    if prep is None and total_votes == 0:
        print(f"There is no reward. Since {address} is not a P-Rep and has no votes")
        return

    print(f"## Estimate reward of {address} at {current_height}\n")

    # get all vote events
    vf = VoteFetcher(uri)
    print(f"## Fetch all votes in {t.info()}")
    vf.fetch(t.start_block_height, current_height, fp=sys.stdout)
    print()

    print(f"## Fetch all penalties in {t.info()}")
    pf = PenaltyFetcher(uri)
    penalties = pf.run(t.start_block_height, current_height, progress=True)
    print()

    print(f"\n## Status of {address}")
    if prep is not None:
        print("> P-Rep")
        pprint(prep)
    print("> Bond")
    pprint(bond)
    print("> Delegation")
    pprint(delegation)
    print()

    print(f"## Calculate reward\n")

    # prep reward
    pr = PRepReward.from_network(uri, t.start_block_height)
    pr.height = current_height
    pr.calculate(vf.votes, penalties)

    # voter reward
    voter = Voter(address, vf.votes_for_voter_reward(address), pr.start_height, pr.offset_limit(), pr.preps)
    voter.calculate()

    print(f"## Estimated reward")
    prep = pr.get_prep(address)
    print_reward(prep, voter, total_votes, t.period)


def print_reward(prep, voter, total_votes: int = 0, period: int = 0):
    reward = (0 if prep is None else prep.reward()) + voter.reward
    reward_loop = reward // 10 ** 3
    print(f"\t= PRep.commission + PRep.wage + Voter.reward")
    print()
    print(f"\t= {format_int(0 if prep is None else prep.commission)} # PRep.commission")
    print(f"\t+ {format_int(0 if prep is None else prep.wage)} # PRep.wage")
    print(f"\t+ {format_int(voter.reward)} # Voter.reward")
    print()
    print(f"\t= {format_int(reward)} iscore")
    print(f"\t= {format_int(reward_loop)} loop")
    print(f"\t= {format_int(reward_loop / 10 ** 18)} icx")
    if total_votes > 0:
        apy = reward_loop * 365 * 100 * 43200 / (total_votes * period)
        print(f"\n## Estimated APY = {apy} %")


def format_int(value):
    return f"{value:40,}"
