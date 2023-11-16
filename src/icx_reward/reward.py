from __future__ import annotations

import sys
from typing import Dict, List, Optional

from icx_reward.penalty import Penalty, PenaltyFetcher
from icx_reward.rpc import RPC
from icx_reward.types.constants import ICX_TO_ISCORE_RATE, MONTH_BLOCK, RATE_DENOM
from icx_reward.types.prep import JailInfo, PRep as PRepResp
from icx_reward.vote import Vote, Votes


class PRep:
    def __init__(self, enable: bool, address: str, bonded: int, delegated: int, power: int, commission_rate: int):
        self.__enable = enable
        self.__address = address
        self.__bonded = bonded
        self.__delegated = delegated
        self.__power: int = power
        self.__commission_rate = commission_rate

        self.__accumulated_voted: int = 0
        self.__accumulated_power: int = 0
        self.__commission: int = 0
        self.__voter_reward: int = 0
        self.__wage: int = 0
        self.__penalties: Dict[int, Penalty] = {}

    def __repr__(self):
        return (f"PRep('address': '{self.__address}', 'enable': {self.__enable}, "
                f"'accum_voted': {self.__accumulated_voted}, 'accum_power': {self.__accumulated_power}, "
                f"'commission': {self.__commission}, 'wage': {self.__wage}, 'voter_reward': {self.__voter_reward})")

    @property
    def enable(self) -> bool:
        return self.__enable

    @enable.setter
    def enable(self, value: bool):
        self.__enable = value

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

    @property
    def commission(self) -> int:
        return self.__commission

    @property
    def wage(self) -> int:
        return self.__wage

    def rewardable(self) -> bool:
        return self.__enable and self.__accumulated_power > 0

    def reward(self) -> int:
        return self.__commission + self.__wage

    def init_accumulated_values(self, period: int):
        self.__accumulated_voted = (self.__bonded + self.__delegated) * period
        self.__accumulated_power = self.__power * period

    def update_enable(self, uri: str, end_height: int):
        prep: PRepResp = RPC(uri).get_prep(self.address, end_height, to_obj=True)
        self.__enable = not prep.in_jail()

    def update_penalty(self, uri: str, start_height: int, end_height: int):
        pf = PenaltyFetcher(uri)
        self.__penalties = pf.run(start_height, end_height, self.__address)

    def apply_vote_diff(self, type_: int, value: int, period: int, br: int):
        if type_ == Vote.TYPE_BOND:
            self.__bonded += value
        else:
            self.__delegated += value
        self.__accumulated_voted += value * period

        power = min(self.__bonded * RATE_DENOM // br, self.__bonded + self.__delegated)
        power_diff = power - self.__power
        self.__power = power
        self.__accumulated_power += power_diff * period

    def calculate_reward(self, total_prep_reward: int, total_accum_power: int, wage: int, min_bond: int):
        if self.rewardable():
            reward = total_prep_reward * self.__accumulated_power // total_accum_power
            self.__commission = reward * self.__commission_rate // RATE_DENOM
            self.__voter_reward = reward - self.__commission
            if self.__bonded >= min_bond:
                self.__wage = wage

    def voter_reward_for(self, accumulated_vote: int) -> int:
        return self.__voter_reward * accumulated_vote // self.__accumulated_voted

    def penalties_to_vote_diff_list(self) -> List[Vote]:
        diff: List[Vote] = []
        for penalty in self.__penalties.values():
            diff.extend(penalty.slash_event_to_vote_diff_list())
        return diff

    @staticmethod
    def from_get_prep(prep: dict) -> PRep:
        return PRep(
            enable=not JailInfo.from_dict(prep).in_jail(),
            address=prep["address"],
            bonded=int(prep["bonded"], 16),
            delegated=int(prep["delegated"], 16),
            power=int(prep["power"], 16),
            commission_rate=int(prep.get("commissionRate", "0x0"), 16),
        )


class Voter:
    def __init__(self, address: str, votes: Votes, start_height: int, offset_limit: int, preps: Dict[str, PRep],
                 file=None):
        self.__address = address
        self.__votes = votes
        self.__start_height = start_height
        self.__offset_limit = offset_limit
        self.__preps = preps

        self.__accum_votes: Dict[str, int] = {}
        self.__reward = 0

        self.__file = file

    @property
    def address(self) -> str:
        return self.__address

    @property
    def reward(self) -> int:
        return self.__reward

    def _update_accumulated_votes_with_votes(self):
        if self.__votes is None:
            accum_votes = {}
        else:
            accum_votes = self.__votes.accumulated_votes_for_voter(self.__start_height, self.__offset_limit)
        for addr, amount in accum_votes.items():
            if addr in self.__accum_votes.keys():
                self.__accum_votes[addr] += amount
            else:
                self.__accum_votes[addr] = amount

    def _update_accumulated_votes_with_slash(self):
        for prep in self.__preps.values():
            if prep.enable:
                continue

            for penalty in prep.penalties.values():
                amount = penalty.accumulated_slash_amount(self.__start_height, self.__address)
                if prep.address in self.__accum_votes.keys():
                    self.__accum_votes[prep.address] -= amount
                else:
                    self.__accum_votes[prep.address] = -amount

    def calculate_accumulated_vote(self):
        self.__accum_votes.clear()
        self._update_accumulated_votes_with_votes()
        self._update_accumulated_votes_with_slash()

    def calculate_reward(self):
        self._print(
            f">> Calculate Voter reward of {self.__address} = sum(PRep.voter_reward * Voter.accum_vote(prep) // PRep.accum_voted)")
        for addr, value in self.__accum_votes.items():
            prep = self.__preps.get(addr, None)
            if value == 0:
                continue
            if prep is None:
                self._print(f"\tvote to {addr}: Not elected PRep")
                continue
            reward = prep.voter_reward_for(value)
            self._print(f"\tvote to {addr}: {reward} = {prep.voter_reward} * {value} // {prep.accumulated_voted}")
            self.__reward += reward
        if len(self.__accum_votes) == 0:
            self._print(f"<< {self.__address} has no vote")
        else:
            self._print(f"<< Voter reward: {self.__reward}")

    def calculate(self):
        self.calculate_accumulated_vote()
        self.calculate_reward()

    def _print(self, msg: str):
        if self.__file is not None:
            print(msg, file=self.__file)


class PRepReward:
    def __init__(self, uri: str, start: int, end: int, br: int, validator_count: int, min_bond: int, preps: dict,
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
        self.__rpc = RPC(uri)

    @staticmethod
    def _reward_iscore_of_term(iglobal: int, rate: int, term_period: int) -> int:
        return (iglobal * rate // RATE_DENOM) * ICX_TO_ISCORE_RATE * term_period // MONTH_BLOCK

    @property
    def start_height(self) -> int:
        return self.__start_height

    @property
    def end_height(self) -> int:
        return self.__end_height

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

    def init_accumulated_values(self):
        for prep in self.__preps.values():
            prep.init_accumulated_values(self.period())

    def update_enables(self):
        for prep in self.__preps.values():
            prep.update_enable(self.__rpc.uri, self.__end_height)

    def update_penalties(self):
        for prep in self.__preps.values():
            prep.update_penalty(self.__rpc.uri, self.__start_height, self.__end_height)

    def apply_votes(self, votes: Dict[str, Votes]) -> None:
        # merge setBond, setDelegation and slash event
        vote_diff_list: List[Vote] = []
        for v in votes.values():
            vote_diff_list.extend(v.to_vote_diff_list())
        for prep in self.__preps.values():
            vote_diff_list.extend(prep.penalties_to_vote_diff_list())
        vote_diff_list.sort(key=lambda x: x.height)

        preps_addr = self.__preps.keys()
        # update accumulated value in PRep
        for vote in vote_diff_list:
            for to, value in vote.values.items():
                if to not in preps_addr:
                    continue
                prep = self.__preps[to]
                prep.apply_vote_diff(vote.type, value, self.offset_limit() - vote.offset(self.__start_height), self.__br)
                self.__preps[to] = prep

        # update total_accumulated_power
        total_accum_power = 0
        for prep in self.__preps.values():
            total_accum_power += prep.accumulated_power
        self.__total_accumulated_power = total_accum_power

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

    def calculate(self, votes: Dict[str, Votes]):
        self.init_accumulated_values()
        self.update_enables()
        self.update_penalties()
        self.apply_votes(votes)
        self.calculate_reward()

    def print_summary(self, file=sys.stdout):
        print(f"<< PRep reward summary. {self.__start_height} ~ {self.__end_height}", file=file)
        print(f"Total PRep reward: {self.__total_prep_reward}, Total wage: {self.__total_wage}", file=file)
        print(f"Total accumulated power: {self.__total_accumulated_power}", file=file)
        print(f"Elected PReps", file=file)
        for i, prep in enumerate(self.__preps.values()):
            print(f"\t#{i}: {prep}", file=file)

    @staticmethod
    def from_network(uri: str, height: int) -> PRepReward:
        return PRepReward.from_term(uri, RPC(uri).term(height))

    @staticmethod
    def from_term(uri: str, term: dict) -> PRepReward:
        preps: Dict[str, PRep] = {}
        for p in term["preps"]:
            prep = PRep.from_get_prep(p)
            preps[prep.address] = prep

        return PRepReward(
            uri=uri,
            start=int(term["startBlockHeight"], 0),
            end=int(term["endBlockHeight"], 0),
            br=int(term["bondRequirement"], 0),
            validator_count=len(term["preps"]),
            preps=preps,
            iglobal=int(term["rewardFund"]["Iglobal"], 0),
            iprep=int(term["rewardFund"]["Iprep"], 0),
            iwage=int(term["rewardFund"].get("Iwage", "0x0"), 0),
            min_bond=int(term.get("minimumBond", "0x0"), 0),
        )
