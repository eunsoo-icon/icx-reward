class RewardFund(dict):
    IGLOBAL = "Iglobal"
    IPREP ="Iprep"
    IWAGE = "Iwage"
    IRELAY = "Irelay"
    ICPS = "Icps"
    DENOM = 10000

    def __setitem__(self, key, value):
        super().__setitem__(key, int(value, 0))

    @staticmethod
    def from_dict(values: dict) -> 'RewardFund':
        ret = RewardFund()
        for k, v in values.items():
            ret[k] = v
        return ret

    def amount_by_key(self, key: str) -> int:
        return self[RewardFund.IGLOBAL] * self[key] // RewardFund.DENOM
