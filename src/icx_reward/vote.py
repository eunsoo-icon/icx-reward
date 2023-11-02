from __future__ import annotations

import json
import sys
from copy import deepcopy
from typing import Dict, List

from iconsdk.monitor import EventFilter, EventMonitorSpec
from iconsdk.providers.provider import MonitorTimeoutException

from icx_reward.rpc import RPC
from icx_reward.types.address import Address
from icx_reward.types.bloom import get_bloom_data, get_score_address_bloom_data
from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.event import Event, EventSig
from icx_reward.types.exception import InvalidParamsException
from icx_reward.types.rlp import rlp_decode
from icx_reward.utils import pprint, print_progress

SYSTEM_ADDRESS_BF_DATA = get_score_address_bloom_data(Address.from_string(SYSTEM_ADDRESS))
VOTE_SIG_BF_DATA = [get_bloom_data(0, x) for x in EventSig.VOTE_SIG_LIST]


class Vote:
    TYPE_BOND = 0
    TYPE_DELEGATE = 1

    def __init__(self, owner: str, _type: int, height: int = -1, values: Dict[str, int] = {}):
        self.__owner = owner
        self.__type = _type
        self.__height = height
        self.__values: Dict[str, int] = values

    def __repr__(self):
        return f"Vote('owner': '{self.__owner}', 'type': {self.__type}, 'height': {self.__height}, 'values': {self.__values})"

    def __deepcopy__(self, memodict={}):
        copy = Vote(owner=self.__owner, _type=self.__type, height=self.__height)
        copy.__values = deepcopy(self.__values)
        return copy

    @property
    def owner(self) -> str:
        return self.__owner

    @property
    def type(self) -> int:
        return self.__type

    @property
    def height(self) -> int:
        return self.__height

    @property
    def values(self) -> Dict[str, int]:
        return self.__values

    def offset(self, start_height: int) -> int:
        if self.__height == -1:
            return self.__height
        else:
            return self.__height - start_height

    def diff(self, prev: Vote) -> Vote:
        diff = deepcopy(self)
        if prev is None:
            return diff
        for k, v in prev.__values.items():
            diff.__values[k] = diff.__values.get(k, 0) - v
        return diff

    def to_dict(self) -> dict:
        return {
            "owner": self.__owner,
            "type": self.__type,
            "height": self.__height,
            "values": self.__values
        }

    @staticmethod
    def from_dict(value: dict) -> Vote:
        v = Vote(
            owner=value["owner"],
            _type=value["type"],
            height=value["height"],
        )
        v.__values = value["values"]
        return v

    @staticmethod
    def from_event(offset: int, event: Event) -> Vote:
        if event.score_address != SYSTEM_ADDRESS:
            raise InvalidParamsException(f"invalid scoreAddress {event.score_address}")
        if event.signature not in EventSig.VOTE_SIG_LIST:
            raise InvalidParamsException(f"invalid signature {event.signature}")
        voter = event.indexed[1]
        vote_data = event.data[0][2:]

        data = {}
        vote_bytes = bytes.fromhex(vote_data)
        unpacked = rlp_decode(vote_bytes, {list: [bytes, int]})
        for v in unpacked:
            data[str(Address.from_bytes(v[0]))] = v[1]

        return Vote(
            owner=voter,
            _type=Vote.TYPE_BOND if event.signature == EventSig.SetBond else Vote.TYPE_DELEGATE,
            height=offset,
            values=data,
        )

    @staticmethod
    def from_get_bond(owner: str, value: dict) -> Vote:
        values = {}
        for v in value["bonds"]:
            values[v["address"]] = v["value"] if isinstance(v["value"], int) else int(v["value"], 16)
        return Vote(
            owner=owner,
            _type=Vote.TYPE_BOND,
            values=values,
        )

    @staticmethod
    def from_get_delegation(owner: str, value: dict) -> Vote:
        values = {}
        for v in value["delegations"]:
            values[v["address"]] = v["value"] if isinstance(v["value"], int) else int(v["value"], 16)
        return Vote(
            owner=owner,
            _type=Vote.TYPE_DELEGATE,
            values=values,
        )


class Votes:
    def __init__(self, owner: str):
        self.__owner = owner
        self.__bonds: List[Vote] = []
        self.__delegations: List[Vote] = []

    def __repr__(self):
        return f"Votes('owner': '{self.__owner}', 'bonds': {self.__bonds}, 'delegations': {self.__delegations})"

    @property
    def owner(self) -> str:
        return self.__owner

    @property
    def bonds(self) -> List[Vote]:
        return self.__bonds

    @property
    def delegations(self) -> List[Vote]:
        return self.__delegations

    def append_vote(self, vote: Vote):
        if vote.type == Vote.TYPE_BOND:
            self.__bonds.append(vote)
        else:
            self.__delegations.append(vote)

    def _vote_values_for_prep(self, rpc: RPC, votes: List[Vote], prep: str, start_height: int,
                              offset_limit: int) -> int:
        if len(votes) == 0:
            return 0
        if votes[0].type == Vote.TYPE_BOND:
            prev = Vote.from_get_bond(self.__owner, rpc.get_bond(self.__owner, start_height))
        else:
            prev = Vote.from_get_delegation(self.__owner, rpc.get_delegation(self.__owner, start_height))
        accum_value = 0
        for vote in votes:
            diff = vote.diff(prev)
            period = offset_limit - diff.offset(start_height)
            if prep in diff.values.keys():
                accum_value += period * diff.values[prep]
            prev = vote
        return accum_value

    def accumulated_values_for_prep(self, rpc: RPC, prep: str, start_height: int, offset_limit: int) -> (int, int):
        return (self._vote_values_for_prep(rpc, self.__bonds, prep, start_height, offset_limit),
                self._vote_values_for_prep(rpc, self.__delegations, prep, start_height, offset_limit))

    def to_dict(self) -> dict:
        return {
            "bonds": [x.to_dict() for x in self.__bonds],
            "delegations": [x.to_dict() for x in self.__delegations],
        }

    @staticmethod
    def from_dict(owner: str, value: dict) -> Votes:
        votes = Votes(owner)
        for d in value["bonds"] + value["delegations"]:
            votes.append_vote(Vote.from_dict(d))
        return votes


class VoteFetcher:
    def __init__(self, rpc: RPC, start_height: int, end_height: int, import_fp=None, file=None):
        self.__rpc = rpc
        self.__start_height = start_height
        self.__end_height = end_height
        self.__votes: Dict[str, Votes] = {}
        self.__import_fp = import_fp
        self.__file = file

    def __repr__(self):
        return f"VoteFetcher('startHeight': {self.__start_height}, 'endHeight': {self.__end_height}, 'votes': {self.__votes}"

    @property
    def votes(self) -> Dict[str, Votes]:
        return self.__votes

    def vote_of(self, addr: str):
        return self.__votes[addr]

    def _import(self, fp):
        self._print(f">> Import votes from file {fp.name}")
        data = json.load(fp)
        if self.__start_height != data["startHeight"] or self.__end_height != data["endHeight"]:
            raise InvalidParamsException("Invalid import vote file. check startHeight and endHeight")

        for addr, votes in data["votes"].items():
            self.__votes[addr] = Votes.from_dict(addr, votes)

    def run(self):
        self.__votes.clear()

        if self.__import_fp is not None:
            self._import(self.__import_fp)
            return

        self._print(f">> Fetch votes from {self.__start_height} to {self.__end_height}")
        self._fetch_via_websocket()

    def _fetch_via_websocket(self):
        monitor = self.__rpc.sdk.monitor(
            spec=EventMonitorSpec(
                height=self.__start_height + 1,
                filters=[
                    EventFilter(
                        event=EventSig.SetDelegation,
                        addr=SYSTEM_ADDRESS,
                        indexed=0,
                    ),
                    EventFilter(
                        event=EventSig.SetBond,
                        addr=SYSTEM_ADDRESS,
                        indexed=0,
                    ),
                ],
                logs=True,
                progress_interval=1000,
            ),
        )

        while True:
            try:
                data = monitor.read(timeout=5)
            except MonitorTimeoutException:
                break
            height = int(data.get("height", data.get("progress")), 16) - 1
            if height > self.__end_height:
                self._print_progress(height)
                break
            self._print_progress(height)
            if "progress" in data.keys():
                continue
            self.update_votes([Vote.from_event(height, Event.from_dict(d)) for d in data["logs"]])

    def update_votes(self, votes: List[Vote]):
        for vote in votes:
            key = vote.owner
            if key in self.__votes.keys():
                self.__votes[key].append_vote(vote)
            else:
                votes = Votes(owner=key)
                votes.append_vote(vote)
                self.__votes[key] = votes

    def export(self, fp):
        json.dump(fp=fp, obj=self.to_dict(), indent=2)

    def print_result(self):
        pprint(self.to_dict(), file=self.__file)

    def to_dict(self):
        votes = {}
        for key, value in self.__votes.items():
            votes[key] = value.to_dict()

        return {
            "startHeight": self.__start_height,
            "endHeight": self.__end_height,
            "votes": votes
        }

    def _print(self, msg):
        if self.__file is not None:
            print(msg, file=self.__file)

    def _print_progress(self, height: int):
        if self.__file is None or self.__file != sys.stdout:
            return
        start_height = self.__start_height - 1
        if height > self.__end_height:
            height = self.__end_height
        print_progress(
            iteration=height - start_height,
            total=self.__end_height - start_height,
            prefix="Progress", suffix="Complete",
            decimals=1, bar_length=50,
        )
