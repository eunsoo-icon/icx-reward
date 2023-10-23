from __future__ import annotations

import json
from copy import deepcopy
from typing import Dict, List, Optional

from icx_reward.address import Address
from icx_reward.bloom import BloomFilter, get_bloom_data, get_score_address_bloom_data
from icx_reward.constants import SYSTEM_ADDRESS
from icx_reward.rlp import rlp_decode
from icx_reward.rpc import RPC
from icx_reward.utils import debug_print, bytes_to_int

REVISION = 24
IISS_VERSION = 4

UNBOND_HEIGHT = "UNBOND_HEIGHT"
TERM_INFO = "TERM_INFO"
VOTE_INFOS = "VOTE_INFOS"
BONDER_LIST = "BONDER_LIST"

SCORE_ADDRESS = get_score_address_bloom_data(Address.from_string(SYSTEM_ADDRESS))
SET_BOND_SIG = "SetBond(Address,bytes)"
SET_DELEGATION_SIG = "SetDelegation(Address,bytes)"
VOTE_SIG = [SET_BOND_SIG, SET_DELEGATION_SIG]
VOTE_SIG_BF_DATA = [
    get_bloom_data(0, SET_BOND_SIG),
    get_bloom_data(0, SET_DELEGATION_SIG),
]


class Vote:
    TYPE_BOND = 0
    TYPE_DELEGATE = 1

    def __init__(self, owner: Address, _type: int, offset: int = 0, data: List[Dict] = []):
        self.__owner = owner
        self.__type = _type
        self.__offset = offset
        self.vote: Dict[str, int] = {}
        for d in data:
            self.vote[d["address"]] = d["value"]

    def __str__(self):
        return f"Vote{self.__dict__}"

    def __deepcopy__(self, memodict={}):
        copy = Vote(_type=self.__type, offset=self.__offset)
        copy.vote = deepcopy(self.vote)
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
        for k, v in vote.vote.items():
            diff.vote[k] = diff.vote.get(k, 0) - v
        return diff

    def merge(self, vote: Vote) -> None:
        self.__offset = vote.__offset
        for k, v in vote.vote.items():
            self.vote[k] = self.vote.get(k, 0) + v

    def to_dict(self) -> dict:
        return {
            "owner": str(self.__owner),
            "type": self.__type,
            "offset": self.__offset,
            "vote": self.vote
        }

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
            _type=Vote.TYPE_BOND if sig == SET_BOND_SIG else Vote.TYPE_DELEGATE,
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


class VoteFetcher:
    def __init__(self, rpc: RPC, start_height: int, end_height: int):
        self.__rpc = rpc
        self.__start_height = start_height
        self.__end_height = end_height
        self.__votes: List[Vote] = []

    @property
    def votes(self) -> List[Vote]:
        return self.__votes

    def run(self):
        height = self.__start_height
        while height <= self.__end_height:
            block = self.__rpc.sdk.get_block(height)
            for i, tx in enumerate(block["confirmed_transaction_list"]):
                if i == 0:
                    continue
                tx_result = self.__rpc.sdk.get_transaction_result(tx["txHash"])
                votes = self.tx_result_to_votes(height - self.__start_height, tx_result)
                if votes is not None:
                    self.__votes.extend(votes)
            height += 1

    def export(self, fp):
        data = {
            "startHeight": self.__start_height,
            "endHeight": self.__end_height,
            "votes": [x.to_dict() for x in self.__votes],
        }
        json.dump(fp=fp, obj=data)

    @staticmethod
    def tx_result_to_votes(offset: int, tx_result: dict) -> Optional[List[Vote]]:
        bf = BloomFilter(bytes_to_int(tx_result["logsBloom"]))

        if SCORE_ADDRESS not in bf:
            return None

        if VOTE_SIG_BF_DATA[0] not in bf and VOTE_SIG_BF_DATA[1] not in bf:
            return None

        votes: List[Vote] = []
        for event in tx_result["eventLogs"]:
            if len(event["indexed"]) != 2 or len(event["data"]) != 1:
                continue
            score_address = event["scoreAddress"]
            sig = event["indexed"][0]
            if score_address != SYSTEM_ADDRESS and sig not in VOTE_SIG:
                continue
            vote = Vote.from_event(offset, event)
            votes.append(vote)
            print(vote.to_dict())

        return votes
