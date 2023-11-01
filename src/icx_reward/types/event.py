from typing import List


class EventSig:
    Penalty = "PenaltyImposed(Address,int,int)"
    Slash = "Slashed(Address,Address,int)"
    SetBond = "BondSet(Address,bytes)"
    SetDelegation = "DelegationSet(Address,bytes)"
    VOTE_SIG_LIST = [SetBond, SetDelegation]


class Event:
    def __init__(self, score_address: str, indexed: List[str], data: List[str]):
        self.__score_address = score_address
        self.__indexed = indexed
        self.__data = data

    def __repr__(self):
        return f"Event('scoreAddress': '{self.__score_address}', 'indexed': '{self.__indexed}', 'data': '{self.__data}'"

    @property
    def score_address(self) -> str:
        return self.__score_address

    @property
    def indexed(self) -> List[str]:
        return self.__indexed

    @property
    def data(self) -> List[str]:
        return self.__data

    @property
    def signature(self) -> str:
        return self.__indexed[0]

    @staticmethod
    def from_dict(values: dict):
        return Event(
            score_address=values.get("scoreAddress"),
            indexed=values.get("indexed"),
            data=values.get("data"),
        )
