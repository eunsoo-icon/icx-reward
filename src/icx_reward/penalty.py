from typing import Dict, List, Optional

from iconsdk.exception import JSONRPCException
from iconsdk.monitor import EventFilter, EventMonitorSpec
from iconsdk.providers.provider import MonitorTimeoutException

from icx_reward.rpc import RPCBase
from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.event import Event, EventSig
from icx_reward.types.exception import InvalidParamsException
from icx_reward.types.prep import PRep
from icx_reward.utils import print_progress
from icx_reward.vote import Vote


class Penalty:
    def __init__(self, height: int, events: List[Event]):
        self.__height = height
        self.__events = events

    def __repr__(self):
        return f"Penalty('height': {self.__height}, 'events': {self.__events})"

    def accumulated_slash_amount(self, end_height: int, bonder_address: str = None) -> int:
        amount = 0
        period = end_height - self.__height
        for event in self.__events:
            if event.indexed[0] == EventSig.Slash and len(event.data) == 2:
                if bonder_address is None or event.data[0] == bonder_address:
                    amount += int(event.data[1], 16) * period
        return amount

    def slash_event_to_vote_diff_list(self) -> List[Vote]:
        vote_list = []
        for event in self.__events:
            if event.indexed[0] == EventSig.Slash and len(event.data) == 2:
                vote_list.append(Vote.from_slash_event(self.__height, event))
        print(f"slash_evnet_to_vote_diff_list {vote_list}")
        return vote_list


class PenaltyFetcher(RPCBase):
    def __init__(self, uri: str):
        super().__init__(uri=uri)

    def _get_prep(self, address: str, height: int = None) -> Optional[PRep]:
        try:
            resp = self.call(
                to=SYSTEM_ADDRESS,
                method="getPRep",
                params={"address": address},
                height=height,
            )
        except JSONRPCException:
            return None
        else:
            return PRep.from_dict(resp)

    def _is_prep(self, address, height: int) -> bool:
        return self._get_prep(address, height) is not None

    @staticmethod
    def _event_filter(address: str = None) -> List[EventFilter]:
        if address is None:
            return [
                EventFilter(event=EventSig.Penalty, addr=SYSTEM_ADDRESS, indexed=0),
                EventFilter(event=EventSig.Slash, addr=SYSTEM_ADDRESS, indexed=0),
            ]
        else:
            return [
                EventFilter(EventSig.Penalty, SYSTEM_ADDRESS, 1, address),
                EventFilter(EventSig.Slash, SYSTEM_ADDRESS, 1, address),
            ]

    def run(self, start_height: int, end_height: int, address: str = None, progress: bool = False) -> Dict[int, Penalty]:
        penalties: Dict[int, Penalty] = {}

        if address is not None and not self._is_prep(address, end_height):
            raise InvalidParamsException(f"{address} is not P-Rep")

        monitor = self.sdk.monitor(
            spec=EventMonitorSpec(
                height=start_height + 1,
                filters=self._event_filter(address),
                logs=True,
                progress_interval=100,
            )
        )

        while True:
            try:
                data = monitor.read(timeout=5)
            except MonitorTimeoutException:
                if progress:
                    self._print_progress(end_height, start_height, end_height)
                break
            height = int(data.get("height", data.get("progress")), 16) - 1
            if height > end_height:
                if progress:
                    self._print_progress(height, start_height, end_height)
                break
            if progress:
                self._print_progress(height, start_height, end_height)
            if "progress" in data.keys():
                continue
            penalties[height] = Penalty(height=height, events=[Event.from_dict(log) for log in data["logs"]])

        monitor.close()

        return penalties

    @staticmethod
    def _print_progress(height: int, start: int, end: int):
        start_height = start - 1
        if height > end:
            height = end
        print_progress(
            iteration=height - start_height,
            total=end - start_height,
            prefix="Progress", suffix="Complete",
            decimals=1, bar_length=50,
        )
