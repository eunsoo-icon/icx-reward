from enum import auto, IntEnum, IntFlag

from icx_reward.types.address import Address
from icx_reward.types.rate import Rate


class Status(IntEnum):
    """
    Enumerate of PRep status
    """
    Active = 0
    Unregistered = 1
    Disqualified = 2
    NotReady = 3

    def __str__(self) -> str:
        return repr(self)

    @staticmethod
    def from_string(status: str):
        return Status(int(status, 16))


class Grade(IntEnum):
    """
    Enumerate of PRep grade
    """
    Main = 0
    Sub = 1
    Candidate = 2
    NONE = 3

    def __str__(self) -> str:
        return repr(self)

    def rewardable(self) -> bool:
        return self < self.Candidate

    @staticmethod
    def from_string(grade: str):
        return Grade(int(grade, 16))


class PenaltyFlag(IntFlag):
    """
    Enumerate of PRep penalty
    """
    PrepDisqualification = 2
    AccumulatedValidationFailure = auto()
    ValidationFailure = auto()
    MissedNetworkProposalVote = auto()
    DoubleSign = auto()

    def __str__(self) -> str:
        return repr(self)

    @staticmethod
    def from_string(penalty: str):
        return PenaltyFlag(int(penalty, 16))


class JailFlags(IntFlag):
    Jail = 1
    Unjail = auto()
    AccumulatedValidationFailure = auto()
    DoubleSign = auto()

    def __str__(self):
        return repr(self)

    def in_jail(self) -> bool:
        return self & JailFlags.Jail == JailFlags.Jail

    def unjailing(self) -> bool:
        return self & JailFlags.Unjail == JailFlags.Unjail

    def unjailable(self) -> bool:
        return self.in_jail() and not self.unjailing()

    @staticmethod
    def from_string(jail_flags: str):
        return JailFlags(int(jail_flags, 16))


class JailInfo(object):
    def __init__(self, jail_flags: str, unjail_request_height: str, min_double_sign_height: str):
        self._jail_flags = JailFlags.from_string(jail_flags)
        self._unjail_request_height = int(unjail_request_height, 16)
        self._min_double_sign_height = int(min_double_sign_height, 16)

    def __str__(self):
        return f'JailInfo{{{self._jail_flags}, unjail_request_height:{self._unjail_request_height}, min_double_sign_height:{self._min_double_sign_height}}}'

    @property
    def jail_flags(self) -> JailFlags:
        return self._jail_flags

    @property
    def unjail_request_height(self) -> int:
        return self._unjail_request_height

    @property
    def min_double_sign_height(self) -> int:
        return self._min_double_sign_height

    def in_jail(self) -> bool:
        return self._jail_flags.in_jail()

    @staticmethod
    def from_dict(values: dict):
        return JailInfo(
            jail_flags=values.get("jailFlags", "0x0"),
            unjail_request_height=values.get("unjailRequestHeight", "0x0"),
            min_double_sign_height=values.get("minDoubleSignHeight", "0x0"),
        )


class PRepSummary(object):
    """PRep class for getMainPReps and getSubPReps
    """

    def __init__(self, name: str, address: str, delegated: str, power: str):
        self._name = name
        self._address = Address.from_string(address)
        self._delegated = int(delegated, 16)
        self._power = int(power, 16)

    def __str__(self):
        return f'name:{self._name}, address:{self._address}, delegated:{self._delegated}, power:{self._power}'

    def __repr__(self):
        return self.__str__()

    @property
    def name(self) -> str:
        return self._name

    @property
    def address(self) -> Address:
        return self._address

    @property
    def delegated(self) -> int:
        return self._delegated

    @property
    def power(self) -> int:
        return self._power

    @staticmethod
    def from_dict(values: dict):
        return PRepSummary(
            name=values.get("name"),
            address=values.get("address"),
            delegated=values.get("delegated"),
            power=values.get("power"),
        )


class PRep(PRepSummary):
    """PRep class
    """

    def __init__(self, status: Status, grade: Grade, penalty: PenaltyFlag, jail_info: JailInfo, has_pub_key: bool,
                 bonded: str, last_height: str,
                 commission_rate: str, max_commission_rate: str, max_commission_change_rate: str,
                 name: str, address: str, delegated: str, power: str):
        super().__init__(name, address, delegated, power)
        self._jail_info = jail_info
        self._status = status
        self._grade = grade
        self._penalty = penalty
        self._has_pub_key = has_pub_key
        self._bonded = int(bonded, 16)
        self._last_height = int(last_height, 16)
        self._commission_rate = Rate(int(commission_rate, 16))
        self._max_commission_rate = Rate(int(max_commission_rate, 16))
        self._max_commission_change_rate = Rate(int(max_commission_change_rate, 16))

        self._apy = 0
        self._remain_vote = 0

    def __str__(self):
        return (f'PRep{{{self._status}, {self._grade}, {self._penalty}, bonded:{self._bonded}, '
                f'last_height:{self._last_height}, '
                f'commission_rate:{self._commission_rate.value}, '
                f'max_commission_rate:{self._max_commission_rate.value}, '
                f'max_commission_change_rate:{self._max_commission_change_rate.value}, '
                f'{self._jail_info}, has_pub_key:{self._has_pub_key}, {super().__str__()}}}')

    @property
    def status(self) -> Status:
        return self._status

    @property
    def grade(self) -> Grade:
        return self._grade

    @property
    def penalty(self) -> PenaltyFlag:
        return self._penalty

    @property
    def jail_info(self) -> JailInfo:
        return self._jail_info

    @property
    def has_pub_key(self) -> bool:
        return self._has_pub_key

    @property
    def bonded(self) -> int:
        return self._bonded

    def voted(self) -> int:
        return self._bonded + self._delegated

    @property
    def last_height(self) -> int:
        return self._last_height

    @property
    def commission_rate(self) -> Rate:
        return self._commission_rate

    @property
    def max_commission_rate(self) -> Rate:
        return self._max_commission_rate

    @property
    def max_commission_change_rate(self) -> Rate:
        return self._max_commission_change_rate

    def in_jail(self) -> bool:
        return self._jail_info.jail_flags.in_jail()

    def unjailing(self) -> bool:
        return self._jail_info.jail_flags.unjailing()

    def unjailable(self) -> bool:
        return self._jail_info.jail_flags.unjailable()

    def bond_rate(self) -> float:
        return round(self._bonded * 100 / self.voted(), 2)

    @property
    def remain_vote(self) -> int:
        return self._remain_vote

    @property
    def apy(self) -> float:
        return self._apy

    def calculate_apy(self, total_reward_for_preps: int, total_power: int, br: Rate) -> float:
        if self.grade.rewardable():
            reward_for_prep = total_reward_for_preps * self._power * 12 // total_power
            reward_for_voter = reward_for_prep * (1 - self._commission_rate.value / self._commission_rate.denom)
            self._apy = round(reward_for_voter * 100 / self.voted(), 3)
        else:
            self._apy = float(0)
        self._remain_vote = br.divide_int(self._bonded) - self.voted()
        return self._apy

    def apy_sort_key(self):
        return (Grade.Candidate > self.grade), self._apy, self._remain_vote

    @staticmethod
    def from_dict(values: dict):
        return PRep(
            status=Status.from_string(values.get("status", "0x0")),
            grade=Grade.from_string(values.get("grade", "0x0")),
            penalty=PenaltyFlag.from_string(values.get("penalty", "0x0")),
            has_pub_key=True if values.get("hashPublicKey", "0x1") == "0x1" else False,
            jail_info=JailInfo.from_dict(values),
            bonded=values.get("bonded"),
            last_height=values.get("lastHeight"),
            name=values.get("name"),
            address=values.get("address"),
            delegated=values.get("delegated"),
            power=values.get("power"),
            commission_rate=values.get("commissionRate", "0x0"),
            max_commission_rate=values.get("maxCommissionRate", "0x0"),
            max_commission_change_rate=values.get("maxCommissionChangeRate", "0x0"),
        )
