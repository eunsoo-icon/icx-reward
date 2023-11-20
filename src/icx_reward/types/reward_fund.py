class RewardFund(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, int(value, 0))

    @staticmethod
    def from_dict(values: dict) -> 'RewardFund':
        ret = RewardFund()
        for k, v in values.items():
            ret[k] = v
        return ret
