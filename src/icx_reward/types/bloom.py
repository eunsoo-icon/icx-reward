# source code from
#   https://github.com/ethereum/eth-bloom
#
# changes
#   hash function : keccak() -> sha3_256()

from __future__ import absolute_import

import hashlib
import numbers
import operator
from typing import TYPE_CHECKING, Iterable, Union, TypeVar

from icx_reward.types.constants import DATA_BYTE_ORDER
from icx_reward.types.utils import int_to_bytes
from icx_reward.types.address import Address
from icx_reward.types.exception import InvalidEventLogException


def get_chunks_for_bloom(value_hash: bytes) -> Iterable[bytes]:
    yield value_hash[:2]
    yield value_hash[2:4]
    yield value_hash[4:6]


def chunk_to_bloom_bits(chunk: bytes) -> int:
    high, low = bytearray(chunk)
    return 1 << ((low + (high << 8)) & 2047)


def get_bloom_bits(value: bytes) -> Iterable[int]:
    value_hash = hashlib.sha3_256(value).digest()
    for chunk in get_chunks_for_bloom(value_hash):
        bloom_bits = chunk_to_bloom_bits(chunk)
        yield bloom_bits


class BloomFilter(numbers.Number):
    value = None  # type: int

    def __init__(self, value: int = 0) -> None:
        self.value = value

    def __int__(self) -> int:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def add(self, value: bytes) -> None:
        if not isinstance(value, bytes):
            raise TypeError("Value must be of type `bytes`")
        for bloom_bits in get_bloom_bits(value):
            self.value |= bloom_bits

    def extend(self, iterable: Iterable[bytes]) -> None:
        for value in iterable:
            self.add(value)

    @classmethod
    def from_iterable(cls, iterable: Iterable[bytes]) -> "BloomFilter":
        bloom = cls()
        bloom.extend(iterable)
        return bloom

    def __contains__(self, value: bytes) -> bool:
        if not isinstance(value, bytes):
            raise TypeError("Value must be of type `bytes`")
        return all(self.value & bloom_bits for bloom_bits in get_bloom_bits(value))

    def __index__(self) -> int:
        return operator.index(self.value)

    def _combine(self, other: Union[int, "BloomFilter"]) -> "BloomFilter":
        if not isinstance(other, (int, BloomFilter)):
            raise TypeError(
                "The `or` operator is only supported for other `BloomFilter` instances"
            )
        return type(self)(int(self) | int(other))

    def __or__(self, other: Union[int, "BloomFilter"]) -> "BloomFilter":
        return self._combine(other)

    def __add__(self, other: Union[int, "BloomFilter"]) -> "BloomFilter":
        return self._combine(other)

    def _icombine(self, other: Union[int, "BloomFilter"]) -> "BloomFilter":
        if not isinstance(other, (int, BloomFilter)):
            raise TypeError(
                "The `or` operator is only supported for other `BloomFilter` instances"
            )
        self.value |= int(other)
        return self

    def __ior__(self, other: Union[int, "BloomFilter"]) -> "BloomFilter":
        return self._icombine(other)

    def __iadd__(self, other: Union[int, "BloomFilter"]) -> "BloomFilter":
        return self._icombine(other)


if TYPE_CHECKING:
    # This ensures that our linter catches any missing abstract base methods
    BloomFilter()


BaseType = TypeVar("BaseType", int, str, bytes, Address)


def get_bytes_from_base_type(data: 'BaseType') -> bytes:
    if isinstance(data, str):
        return data.encode('utf-8')
    elif isinstance(data, Address):
        return data.prefix.value.to_bytes(1, DATA_BYTE_ORDER) + data.body
    elif isinstance(data, bytes):
        return data
    elif isinstance(data, int):
        return int_to_bytes(data)
    else:
        raise InvalidEventLogException(f'Invalid data type: {type(data)}, data: {data}')


def get_bloom_data(index: int, data: 'BaseType') -> bytes:
    bloom_data = index.to_bytes(1, DATA_BYTE_ORDER)
    if data is not None:
        bloom_data += get_bytes_from_base_type(data)
    return bloom_data


def get_score_address_bloom_data(address: Address) -> bytes:
    return get_bloom_data(0xff, address)
