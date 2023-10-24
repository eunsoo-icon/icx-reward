class EventSig:
    Penalty = "PenaltyImposed(Address,int,int)"
    Slash = "Slashed(Address,Address,int)"
    SetBond = "SetBond(Address,bytes)"
    SetDelegation = "SetDelegation(Address,bytes)"
    VOTE_SIG_LIST = [SetBond, SetDelegation]

