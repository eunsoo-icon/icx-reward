from __future__ import annotations

import json
from copy import deepcopy
from typing import Dict, List, Optional

from icx_reward.rpc import RPC
from icx_reward.types.address import Address
from icx_reward.types.bloom import BloomFilter, get_bloom_data, get_score_address_bloom_data
from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.event import EventSig
from icx_reward.types.rlp import rlp_decode
from icx_reward.types.utils import bytes_to_int
from icx_reward.utils import debug_print, pprint, print_progress

SYSTEM_ADDRESS_BF_DATA = get_score_address_bloom_data(Address.from_string(SYSTEM_ADDRESS))
VOTE_SIG_BF_DATA = [get_bloom_data(0, x) for x in EventSig.VOTE_SIG_LIST]


class Vote:
    TYPE_BOND = 0
    TYPE_DELEGATE = 1

    def __init__(self, owner: Address, _type: int, offset: int = 0, data: List[Dict] = []):
        self.__owner = owner
        self.__type = _type
        self.__offset = offset
        self.values: Dict[str, int] = {}
        for d in data:
            self.values[d["address"]] = d["value"]

    def __str__(self):
        return f"Vote{self.__dict__}"

    def __deepcopy__(self, memodict={}):
        copy = Vote(_type=self.__type, offset=self.__offset)
        copy.values = deepcopy(self.values)
        return copy

    @property
    def owner(self) -> Address:
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

    def diff(self, vote: Vote) -> Vote:
        diff = deepcopy(self)
        if vote is None:
            return diff
        for k, v in vote.values.items():
            diff.values[k] = diff.values.get(k, 0) - v
        return diff

    def merge(self, vote: Vote) -> None:
        self.__offset = vote.__offset
        for k, v in vote.values.items():
            self.values[k] = self.values.get(k, 0) + v

    def to_dict(self) -> dict:
        return {
            "owner": str(self.__owner),
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
            owner=Address.from_string(voter),
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
            debug_print(-1, f"Vote.from_tx() {vote} from {tx['txHash']}")
            return vote
        return None

    @staticmethod
    def from_tx(tx: dict, start_height: int) -> Optional[Vote]:
        return Vote.from_block_tx(tx, tx["blockHeight"] - start_height)

    @staticmethod
    def from_get_bond(value: dict) -> Vote:
        return Vote(
            _type=Vote.TYPE_BOND,
            offset=-1,
            data=value["bonds"],
        )

    @staticmethod
    def from_get_delegation(value: dict) -> Vote:
        return Vote(
            _type=Vote.TYPE_DELEGATE,
            offset=-1,
            data=value["delegations"],
        )


class Votes:
    def __init__(self):
        self.__bonds: List[Vote] = []
        self.__delegations: List[Vote] = []

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

    def to_dict(self) -> dict:
        return {
            "bonds": [x.to_dict() for x in self.__bonds],
            "delegations": [x.to_dict() for x in self.__delegations],
        }

    @staticmethod
    def from_dict(value: dict) -> Votes:
        votes = Votes()
        for d in value["bonds"] + value["delegations"]:
            votes.append_vote(Vote.from_dict(d))
        return votes


class VoteFetcher:
    def __init__(self, rpc: RPC, start_height: int, end_height: int, import_fp=None):
        self.__rpc = rpc
        self.__start_height = start_height
        self.__end_height = end_height
        self.__votes: Dict[str, Votes] = {}
        if import_fp is not None:
            self._load_from_fp(import_fp)

    @property
    def votes(self) -> Dict[str, Votes]:
        return self.__votes

    def _print_progress(self, height: int):
        print_progress(
            iteration=height - self.__start_height,
            total=self.__end_height - self.__start_height,
            prefix="Progress", suffix="Complete",
            decimals=1, bar_length=50,
        )

    def _load_from_fp(self, fp):
        data = json.load(fp)
        self.__start_height = data["startHeight"]
        self.__end_height = data["endHeight"]
        for addr, votes in data["votes"].items():
            self.__votes[addr] = Votes.from_dict(votes)
        print(f"{self.__votes.items()}")

    def run(self):
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
            key = str(vote.owner)
            if key in self.__votes.keys():
                self.__votes[key].append_vote(vote)
            else:
                votes = Votes()
                votes.append_vote(vote)
                self.__votes[key] = votes

    def export(self, fp):
        json.dump(fp=fp, obj=self.to_dict(), indent=2)

    def print_result(self):
        pprint(self.to_dict())

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
