from __future__ import annotations

from typing import Dict, List, Optional

from icx_reward.penalty import Penalty, PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.types.constants import ICX_TO_ISCORE_RATE, MONTH_BLOCK, RATE_DENOM
from icx_reward.types.prep import JailInfo, PRep as PRepResp
from icx_reward.utils import debug_print, tab_print
from icx_reward.vote import Vote, Votes


class PRep:
    def __init__(self, enable: bool, address: str, bonded: int, delegated: int, commission_rate: int):
        self.__enable = enable
        self.__address = address
        self.__bonded = bonded
        self.__delegated = delegated
        self.__commission_rate = commission_rate

        self.__accumulated_bonded: int = 0
        self.__accumulated_voted: int = 0
        self.__accumulated_power: int = 0
        self.__commission: int = 0
        self.__voter_reward: int = 0
        self.__wage: int = 0
        self.__penalties: Dict[int, Penalty] = {}

    def __repr__(self):
        return (f"PRep('address': '{self.__address}', 'enable': {self.__enable}, "
                f"'accum_voted': {self.__accumulated_voted}, 'accum_power': {self.__accumulated_power}, "
                f"'reward': {self.reward()}, 'voter_reward': {self.__voter_reward})")

    @property
    def enable(self) -> bool:
        return self.__enable

    @property
    def address(self) -> str:
        return self.__address

    @property
    def accumulated_voted(self) -> int:
        return self.__accumulated_voted

    @property
    def accumulated_power(self) -> int:
        return self.__accumulated_power

    @property
    def voter_reward(self) -> int:
        return self.__voter_reward

    @property
    def penalties(self) -> Dict[int, Penalty]:
        return self.__penalties

    def rewardable(self) -> bool:
        return self.__enable and self.__accumulated_power > 0

    def reward(self) -> int:
        return self.__commission + self.__wage

    def update_enable(self, rpc: RPC, end_height: int):
        prep: PRepResp = rpc.get_prep(self.address, end_height, to_obj=True)
        enable = not prep.in_jail()
        if self.__enable != enable:
            self.__enable = enable

    def update_accumulated_values(self, rpc: RPC, votes: Dict[str, Votes], start_height: int, offset_limit: int,
                                  br: int) -> None:
        self.__accumulated_bonded = self.__bonded * (offset_limit + 1)
        self.__accumulated_voted = (self.__bonded + self.__delegated) * (offset_limit + 1)
        self._update_accumulated_values_with_votes(rpc, votes, start_height, offset_limit)
        self._update_accumulated_values_with_slash(rpc, start_height, start_height + offset_limit)
        self.__accumulated_power = min(self.__accumulated_bonded * RATE_DENOM // br, self.__accumulated_voted)

    def _update_accumulated_values_with_votes(self, rpc: RPC, votes: Dict[str, Votes], start_height: int,
                                              offset_limit: int):
        for v in votes.values():
            accum_bonded, accum_delegated = v.accumulated_values_for_prep(rpc, self.__address, start_height,
                                                                          offset_limit)
            self.__accumulated_bonded += accum_bonded
            self.__accumulated_voted += accum_bonded + accum_delegated

    def _update_accumulated_values_with_slash(self, rpc: RPC, start_height: int, end_height: int):
        if not self.__enable:
            pf = PenaltyFetcher(rpc, self.__address, start_height, end_height)
            pf.run()
            self.__penalties = pf.penalties
            for penalty in self.__penalties.values():
                amount = penalty.accumulated_slash_amount(end_height)
                self.__accumulated_bonded -= amount
                self.__accumulated_voted -= amount

    def calculate_reward(self, total_prep_reward: int, total_accum_power: int, wage: int, min_bond: int):
        if self.rewardable():
            reward = total_prep_reward * self.__accumulated_power // total_accum_power
            self.__commission = reward * self.__commission_rate // RATE_DENOM
            self.__voter_reward = reward - self.__commission
            if self.__bonded >= min_bond:
                self.__wage = wage

    def voter_reward_for(self, accumulated_vote: int) -> int:
        return self.__voter_reward * accumulated_vote // self.__accumulated_voted

    @staticmethod
    def from_get_prep(prep: dict) -> PRep:
        return PRep(
            enable=not JailInfo.from_dict(prep).in_jail(),
            address=prep["address"],
            bonded=int(prep["bonded"], 0),
            delegated=int(prep["delegated"], 0),
            commission_rate=int(prep.get("commissionRate", "0x0"), 0),
        )


class Voter:
    def __init__(self, address: str, votes: Votes, start_height: int, offset_limit: int, preps: Dict[str, PRep]):
        self.__address = address
        self.__votes = votes
        self.__start_height = start_height
        self.__offset_limit = offset_limit
        self.__preps = preps

        self.__accum_vote: Dict[str, int] = {}
        self.__reward = 0
        self.__report = False

    @property
    def address(self) -> str:
        return self.__address

    @property
    def reward(self) -> int:
        return self.__reward

    def _update_accumulated_vote_with_votes(self, votes: List[Vote]):
        for i, vote in enumerate(votes):
            if i == 0:
                prev = None
            else:
                prev = votes[i - 1]
            diff = vote.diff(prev)
            period = self.__offset_limit - diff.offset
            for addr, value in diff.values.items():
                amount = value * period
                if addr in self.__accum_vote.keys():
                    self.__accum_vote[addr] += amount
                else:
                    self.__accum_vote[addr] = amount

    def _update_accumulated_vote_with_slash(self):
        for prep in self.__preps.values():
            if prep.enable:
                continue

            for penalty in prep.penalties.values():
                amount = penalty.accumulated_slash_amount(self.__start_height, self.__address)
                if prep.address in self.__accum_vote.keys():
                    self.__accum_vote[prep.address] -= amount
                else:
                    self.__accum_vote[prep.address] = -amount

    def update_accumulated_vote(self):
        if self.__votes is not None:
            self._update_accumulated_vote_with_votes(self.__votes.bonds)
            self._update_accumulated_vote_with_votes(self.__votes.delegations)
        self._update_accumulated_vote_with_slash()

    def calculate(self):
        self._print(f">> Voter reward of {self.__address} = sum(prep.voter_reward * voter.accum_vote(prep) // prep.accum_voted)")
        for addr, value in self.__accum_vote.items():
            prep = self.__preps.get(addr, None)
            if prep is None:
                self._print(f"\tvote to {addr}: Not elected PRep")
                continue
            reward = prep.voter_reward_for(value)
            self._print(f"\tvote to {addr}: {reward} = {prep.voter_reward} * {value} // {prep.accumulated_voted}")
            self.__reward += reward

    def _print(self, msg: str):
        print(msg)


class PRepCalculator:
    def __init__(self, start: int, end: int, br: int, validator_count: int, min_bond: int, preps: dict,
                 iglobal: int, iprep: int, iwage: int):
        self.__start_height: int = start
        self.__end_height: int = end
        self.__br: int = br
        self.__validator_count: int = validator_count
        self.__min_bond: int = min_bond
        self.__preps: Dict[str, PRep] = preps

        self.__total_prep_reward: int = self._reward_iscore_of_term(iglobal, iprep, self.period())
        self.__total_wage: int = self._reward_iscore_of_term(iglobal, iwage, self.period())
        self.__total_accumulated_power: int = 0

    @staticmethod
    def _reward_iscore_of_term(iglobal: int, rate: int, term_period: int) -> int:
        return (iglobal * rate // RATE_DENOM) * ICX_TO_ISCORE_RATE * term_period // MONTH_BLOCK

    @property
    def start_height(self) -> int:
        return self.__start_height

    def period(self) -> int:
        return self.__end_height + 1 - self.__start_height

    def offset_limit(self) -> int:
        return self.period() - 1

    def get_offset(self, height: int) -> int:
        return height - self.__start_height

    def check_height(self) -> int:
        return self.__start_height + 2 * self.period() + 1

    def next_term_height(self) -> int:
        return self.__start_height + self.period()

    @property
    def min_bond(self) -> int:
        return self.__min_bond

    @property
    def preps(self) -> Dict[str, PRep]:
        return self.__preps

    @property
    def total_prep_reward(self) -> int:
        return self.__total_prep_reward

    @property
    def total_wage(self) -> int:
        return self.__total_wage

    @property
    def total_accumulated_power(self) -> int:
        return self.__total_accumulated_power

    def get_prep(self, addr: str) -> Optional[PRep]:
        if addr not in self.__preps.keys():
            return None
        else:
            return self.__preps[addr]

    def get_prep_reward(self, addr: str) -> int:
        prep = self.get_prep(addr)
        if prep is None:
            return 0
        else:
            return prep.reward()

    def update_enables(self, rpc: RPC):
        debug_print(-1, f"update_enables at {self.__end_height}")
        for prep in self.__preps.values():
            prep.update_enable(rpc, self.__end_height)

    def update_accumulated_values(self, rpc: RPC, votes: Dict[str, Votes]) -> None:
        total_power = 0
        for k, prep in self.__preps.items():
            prep.update_accumulated_values(rpc, votes, self.__start_height, self.offset_limit(), self.__br)
            self.__preps[k] = prep
            total_power += prep.accumulated_power
        self.__total_accumulated_power = total_power

    def calculate_reward(self) -> None:
        wage = self.__total_wage // len(self.__preps)
        for k, prep in self.__preps.items():
            prep.calculate_reward(
                total_prep_reward=self.__total_prep_reward,
                total_accum_power=self.__total_accumulated_power,
                wage=wage,
                min_bond=self.__min_bond,
            )
            self.__preps[k] = prep

    def run(self, rpc: RPC, votes: Dict[str, Votes]):
        print(f">> Calculate PRep reward from {self.__start_height} to {self.__end_height}")
        self.update_enables(rpc)
        self.update_accumulated_values(rpc, votes)
        self.calculate_reward()
        self.print_summary()

    def print_summary(self):
        print(f"PRep reward summary")
        print(f"Total PRep reward: {self.__total_prep_reward} Total wage: {self.__total_wage}")
        print(f"Total accumulated power: {self.__total_accumulated_power}")
        print(f"PReps")
        for i, prep in enumerate(self.__preps.values()):
            print(f"\t#{i}: {prep}")

    @staticmethod
    def from_term(term: dict) -> PRepCalculator:
        preps: Dict[str, PRep] = {}
        for p in term["preps"]:
            prep = PRep.from_get_prep(p)
            preps[prep.address] = prep

        return PRepCalculator(
            start=int(term["startBlockHeight"], 0),
            end=int(term["endBlockHeight"], 0),
            br=int(term["bondRequirement"], 0),
            validator_count=len(term["preps"]),
            preps=preps,
            iglobal=int(term["rewardFund"]["Iglobal"], 0),
            iprep=int(term["rewardFund"]["Iprep"], 0),
            iwage=int(term["rewardFund"].get("Iwage", "0x0"), 0),
            min_bond=int(term.get("minBond", "0x0"), 0),
        )
