from __future__ import annotations

import json
import sys
from copy import deepcopy
from typing import Dict, List, Optional

from icx_reward.rpc import RPC
from icx_reward.types.address import Address
from icx_reward.types.bloom import BloomFilter, get_bloom_data, get_score_address_bloom_data
from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.event import EventSig
from icx_reward.types.exception import InvalidParamsException
from icx_reward.types.rlp import rlp_decode
from icx_reward.types.utils import bytes_to_int
from icx_reward.utils import pprint, print_progress

SYSTEM_ADDRESS_BF_DATA = get_score_address_bloom_data(Address.from_string(SYSTEM_ADDRESS))
VOTE_SIG_BF_DATA = [get_bloom_data(0, x) for x in EventSig.VOTE_SIG_LIST]


class Vote:
    TYPE_BOND = 0
    TYPE_DELEGATE = 1

    def __init__(self, owner: str, _type: int, offset: int = 0, data: List[Dict] = []):
        self.__owner = owner
        self.__type = _type
        self.__offset = offset
        self.values: Dict[str, int] = {}
        for d in data:
            self.values[d["address"]] = d["value"] if isinstance(d["value"], int) else int(d["value"], 16)

    def __repr__(self):
        return f"Vote('owner': '{self.__owner}', 'type': {self.__type}, 'offset': {self.__offset}, 'values': {self.values})"

    def __deepcopy__(self, memodict={}):
        copy = Vote(owner=self.__owner, _type=self.__type, offset=self.__offset)
        copy.values = deepcopy(self.values)
        return copy

    @property
    def owner(self) -> str:
        return self.__owner

    @property
    def type(self) -> int:
        return self.__type

    @property
    def offset(self) -> int:
        return self.__offset

    @offset.setter
    def offset(self, offset: int):
        self.__offset = offset

    def diff(self, prev: Vote) -> Vote:
        diff = deepcopy(self)
        if prev is None:
            return diff
        for k, v in prev.values.items():
            diff.values[k] = diff.values.get(k, 0) - v
        return diff

    def to_dict(self) -> dict:
        return {
            "owner": self.__owner,
            "type": self.__type,
            "offset": self.__offset,
            "vote": self.values
        }

    @staticmethod
    def from_dict(value: dict) -> Vote:
        v = Vote(
            owner=value["owner"],
            _type=value["type"],
            offset=value["offset"],
        )
        v.values = value["vote"]
        return v

    @staticmethod
    def from_event(offset: int, event: dict) -> Vote:
        sig = event["indexed"][0]
        voter = event["indexed"][1]
        vote_data = event["data"][0][2:]

        data = []
        vote_bytes = bytes.fromhex(vote_data)
        unpacked = rlp_decode(vote_bytes, {list: [bytes, int]})
        for v in unpacked:
            data.append({"address": str(Address.from_bytes(v[0])), "value": v[1]})

        return Vote(
            owner=voter,
            _type=Vote.TYPE_BOND if sig == EventSig.SetBond else Vote.TYPE_DELEGATE,
            offset=offset,
            data=data,
        )

    @staticmethod
    def from_block_tx(tx: dict, offset: int) -> Optional[Vote]:
        if tx["to"] == SYSTEM_ADDRESS and tx["dataType"] == "call" and \
                tx["data"]["method"] in ["setDelegation", "setBond"]:
            _type = Vote.TYPE_BOND
            votes = "bonds"
            if tx["data"]["method"] != "setBond":
                _type = Vote.TYPE_DELEGATE
                votes = "delegations"
            vote = Vote(
                _type=_type,
                offset=offset,
                data=tx["data"]["params"][votes],
            )
            return vote
        return None

    @staticmethod
    def from_tx(tx: dict, start_height: int) -> Optional[Vote]:
        return Vote.from_block_tx(tx, tx["blockHeight"] - start_height)

    @staticmethod
    def from_get_bond(owner: str, value: dict) -> Vote:
        return Vote(
            owner=owner,
            _type=Vote.TYPE_BOND,
            offset=-1,
            data=value["bonds"],
        )

    @staticmethod
    def from_get_delegation(owner: str, value: dict) -> Vote:
        return Vote(
            owner=owner,
            _type=Vote.TYPE_DELEGATE,
            offset=-1,
            data=value["delegations"],
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

    def _vote_values_for_prep(self, rpc: RPC, votes: List[Vote], prep: str, start_height: int, offset_limit: int) -> int:
        if len(votes) == 0:
            return 0
        if votes[0].type == Vote.TYPE_BOND:
            prev = Vote.from_get_bond(self.__owner, rpc.get_bond(self.__owner, start_height))
        else:
            prev = Vote.from_get_delegation(self.__owner, rpc.get_delegation(self.__owner, start_height))
        accum_value = 0
        for vote in votes:
            diff = vote.diff(prev)
            period = offset_limit - diff.offset
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
        if self.__import_fp is not None:
            self._import(self.__import_fp)
            return

        self._print(f">> Fetch votes from {self.__start_height} to {self.__end_height}")
        height = self.__start_height
        while height <= self.__end_height:
            self._print_progress(height)
            block = self.__rpc.sdk.get_block(height)
            for i, tx in enumerate(block["confirmed_transaction_list"]):
                if i == 0:
                    continue
                tx_result = self.__rpc.sdk.get_transaction_result(tx["txHash"])
                votes = self.tx_result_to_votes(height - self.__start_height, tx_result)
                self.update_votes(votes)
            height += 1

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

    @staticmethod
    def tx_result_to_votes(offset: int, tx_result: dict, owner: str = None) -> List[Vote]:
        votes: List[Vote] = []
        bf = BloomFilter(bytes_to_int(tx_result["logsBloom"]))

        if SYSTEM_ADDRESS_BF_DATA not in bf:
            return votes

        pass_sig = False
        for data in VOTE_SIG_BF_DATA:
            if data in bf:
                pass_sig = True
                break
        if not pass_sig:
            return votes

        for event in tx_result["eventLogs"]:
            if len(event["indexed"]) != 2 or len(event["data"]) != 1:
                continue
            score_address = event["scoreAddress"]
            sig = event["indexed"][0]
            if score_address != SYSTEM_ADDRESS and sig not in EventSig.VOTE_SIG_LIST:
                continue
            if owner is not None and event["indexed"][1] != owner:
                continue
            vote = Vote.from_event(offset, event)
            votes.append(vote)

        return votes

    def _print(self, msg):
        if self.__file is not None:
            print(msg, file=self.__file)

    def _print_progress(self, height: int):
        if self.__file is None or self.__file != sys.stdout:
            return
        print_progress(
            iteration=height - self.__start_height,
            total=self.__end_height - self.__start_height,
            prefix="Progress", suffix="Complete",
            decimals=1, bar_length=50,
        )
