from enum import auto, IntFlag


class Penalty(IntFlag):
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
        return Penalty(int(penalty, 16))

