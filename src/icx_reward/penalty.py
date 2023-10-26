from typing import Dict, List, Optional

from iconsdk.exception import JSONRPCException

from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.event import EventSig
from icx_reward.types.exception import InvalidParamsException
from icx_reward.types.prep import PenaltyFlag, PRep
from icx_reward.rpc import RPC


class Penalty:
    def __init__(self, height: int, flag: PenaltyFlag, events: List[Dict]):
        self.__height = height
        self.__flag = flag
        self.__events = events

    def accumulated_slash_amount(self, end_height: int, bonder_address: str = None) -> int:
        amount = 0
        period = end_height - self.__height
        for event in self.__events:
            if event["indexed"][0] == EventSig.Slash and len(event["data"]) == 2:
                if bonder_address is None or event["data"][0] == bonder_address:
                    amount += int(event["data"][1], 16) * period
        return amount

    def print(self):
        print(f"At block height {self.__height}: {self.__flag}")
        for e in self.__events:
            print(f"\t{e}")


class PenaltyFetcher:
    def __init__(self, rpc: RPC, address: str, start_height: int, end_height: int):
        self.__rpc = rpc
        self.__address = address
        self.__start_height = start_height
        self.__end_height = end_height
        self.__penalties: Dict[int, Penalty] = {}
        if not self._is_prep(self.__end_height):
            raise InvalidParamsException(f"{self.__address} is not P-Rep")

    @property
    def address(self):
        return self.__address

    @property
    def penalties(self) -> Dict[int, Penalty]:
        return self.__penalties

    def _get_prep(self, height: int) -> Optional[PRep]:
        try:
            prep = self.__rpc.get_prep(self.__address, height, to_obj=True)
        except JSONRPCException:
            return None
        else:
            return prep

    def _is_prep(self, height: int) -> bool:
        return self._get_prep(height) is not None

    def _get_penalty_flag(self, height: int) -> PenaltyFlag:
        return self._get_prep(height).penalty

    def run(self):
        low, high = self.__start_height, self.__end_height
        cur_penalty = self._get_penalty_flag(low)
        target_penalty = self._get_penalty_flag(high)

        if cur_penalty == target_penalty:
            return

        # find penalties
        while low <= high:
            mid = (low + high) // 2
            penalty = self._get_penalty_flag(mid)
            if cur_penalty != penalty:
                prev_penalty = self._get_penalty_flag(mid - 1)
                if cur_penalty == prev_penalty:
                    # mid-1 is penalty height
                    self._add_penalty(mid - 1, ~cur_penalty & penalty)
                    if target_penalty == penalty:
                        break
                    # find again from mid
                    low = mid + 1
                    high = self.__end_height
                    cur_penalty = penalty
                    continue
                else:
                    high = mid - 1
            else:
                low = mid + 1

    def _add_penalty(self, height, flag: PenaltyFlag):
        self.__penalties[height] = Penalty(
            height=height,
            flag=flag,
            events=self._get_events(self.__rpc, height, self.__address, [EventSig.Penalty, EventSig.Slash]),
        )

    @staticmethod
    def _get_events(rpc: RPC, height: int, address: str, signatures: List[str]) -> List[dict]:
        events = []
        block = rpc.sdk.get_block(height)
        tx_result = rpc.sdk.get_transaction_result(block["confirmed_transaction_list"][0]["txHash"])
        for event in tx_result["eventLogs"]:
            indexed = event["indexed"]
            if event["scoreAddress"] == SYSTEM_ADDRESS and indexed[0] in signatures and indexed[1] == address:
                events.append(event)
        return events

    def print_result(self):
        print(f"## Penalties of {self.__address}")
        for pi in self.__penalties.values():
            pi.print()
