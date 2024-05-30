class Rate:
    DENOM = 10_000
    DENOM_OLD = 100

    def __init__(self, value: int, denom: int = 10_000):
        self.value = value
        self.denom = denom

    def __repr__(self):
        return f"Rate({self.value}, {self.denom})"

    def percent(self) -> float:
        return self.value * 100 / self.denom

    def multiply_int(self, value) -> int:
        return value * self.value // self.denom

    def multiply_float(self, value) -> float:
        return value * self.value / self.denom

    def divide_int(self, value) -> int:
        return value * self.denom // self.value

    def divide_float(self, value) -> float:
        return value * self.denom / self.value
