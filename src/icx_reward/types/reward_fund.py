from icx_reward.types.rate import Rate


class RewardFund(dict):
    IGLOBAL = "Iglobal"
    IPREP ="Iprep"
    IWAGE = "Iwage"
    IRELAY = "Irelay"
    ICPS = "Icps"

    def __setitem__(self, key, value):
        if key == self.IGLOBAL:
            super().__setitem__(key, int(value, 0))
        else:
            super().__setitem__(key, Rate(int(value, 0)))

    @staticmethod
    def from_dict(values: dict) -> 'RewardFund':
        ret = RewardFund()
        for k, v in values.items():
            ret[k] = v
        return ret

    def amount_by_key(self, key: str) -> int:
        value = self.get(key, None)
        if isinstance(value, Rate):
            return value.multiply_int(self[RewardFund.IGLOBAL])
        elif value is None:
            return 0
        else:
            raise Exception("Unexpected value type")
