import hashlib
from enum import IntEnum
from typing import Optional

from icx_reward.types.constants import DATA_BYTE_ORDER
from icx_reward.types.utils import int_to_bytes, is_lowercase_hex_string
from icx_reward.types.exception import InvalidParamsException

EOA_ADDRESS_PREFIX = "hx"
CONTRACT_ADDRESS_PREFIX = "cx"


class AddressPrefix(IntEnum):
    """
    Enumeration of Address prefix

    - CONTRACT: Contract Account
    - EOA: Externally Owned Account


    """

    EOA = 0
    CONTRACT = 1

    def __str__(self) -> str:
        if self == AddressPrefix.EOA:
            return EOA_ADDRESS_PREFIX
        if self == AddressPrefix.CONTRACT:
            return CONTRACT_ADDRESS_PREFIX

    @staticmethod
    def from_string(prefix: str):
        """
        Returns address prefix enumerator

        :param prefix: 2-byte address prefix (hx or cx)
        :return: (AddressPrefix) address prefix enumerator
        """
        if prefix == "hx":
            return AddressPrefix.EOA
        if prefix == "cx":
            return AddressPrefix.CONTRACT

        raise InvalidParamsException('Invalid address prefix')


class Address(object):
    """Address class
    """

    BODY_SIZE = 20
    BYTE_SIZE = 21

    def __init__(self,
                 address_prefix: AddressPrefix,
                 address_body: bytes, ignore_length_validate: bool = False) -> None:
        """Constructor

        :param address_prefix: address prefix enumerator
        :param address_body: 20-byte address body
        """

        if not isinstance(address_prefix, AddressPrefix):
            raise InvalidParamsException('Invalid address prefix type')
        if not isinstance(address_body, bytes):
            raise InvalidParamsException('Invalid address body type')

        if not ignore_length_validate:
            if len(address_body) != Address.BODY_SIZE:
                raise InvalidParamsException('Address length is not 20 in bytes')

        self.__prefix = address_prefix
        self.__body = address_body

    @property
    def prefix(self) -> AddressPrefix:
        """Returns address prefix part

        :return: :class:`.AddressPrefix` AddressPrefix.EOA(0) or AddressPrefix.CONTRACT(1)
        """
        return self.__prefix

    @property
    def body(self) -> bytes:
        """Returns 20-byte address body part

        :return: 20 byte data standing for address
        """
        return self.__body

    def __eq__(self, other) -> bool:
        """operator == overriding

        :return: bool
        """
        return \
            isinstance(other, Address) \
            and self.__prefix == other.prefix \
            and self.__body == other.body

    def __ne__(self, other) -> bool:
        """operator != overriding

        :return: (bool)
        """
        return not self.__eq__(other)

    def __str__(self) -> str:
        """operator str() overriding

        returns prefix(2) + 40-char hexadecimal address

        :return: (str) 42-char address
        """
        return f'{str(self.prefix)}{self.body.hex()}'

    def __repr__(self) -> str:
        return self.__str__()

    def __hash__(self) -> int:
        """Returns a hash value for this object

        :return: hash value
        """
        return hash(self.__prefix.to_bytes(1, DATA_BYTE_ORDER) + self.__body)

    @property
    def is_contract(self) -> bool:
        """
        Whether the address is SCORE

        :return: True(contract) False(Not contract)
        """
        return self.prefix == AddressPrefix.CONTRACT

    @staticmethod
    def from_string(address: str):
        """
        creates an address object from given 42-char string `address`

        :return: :class:`.Address`
        """

        if not is_icon_address_valid(address):
            raise InvalidParamsException('Invalid address')

        prefix, body = split_icon_address(address)

        address_prefix = AddressPrefix.from_string(prefix)
        address_body = bytes.fromhex(body)

        return Address(address_prefix, address_body)

    @staticmethod
    def from_data(prefix: AddressPrefix, data: bytes) -> Optional['Address']:
        """
        creates an address object using given body bytes

        :param prefix: address prefix
        :param data: 20-bytes address body
        :return: :class:`.Address`
        """
        try:
            hash_value = hashlib.sha3_256(data).digest()
            return Address(prefix, hash_value[-20:])
        except:
            return None

    @staticmethod
    def from_bytes(buf: bytes) -> Optional['Address']:
        """Create Address object from bytes data

        :param buf: :class:`.bytes` bytes data including Address information
        :return: :class:`.Address`
        """
        if not isinstance(buf, bytes):
            return None

        size: int = len(buf)
        if size not in (Address.BODY_SIZE, Address.BYTE_SIZE):
            return None

        if size == Address.BYTE_SIZE:
            prefix: 'AddressPrefix' = AddressPrefix(buf[0])
            return Address(prefix, buf[1:])
        else:
            return Address(AddressPrefix.EOA, buf)

    def to_bytes(self) -> bytes:
        """
        Returns data as bytes from the address object

        :return: :class:`.bytes` data including information of Address object
        """
        if self.__prefix == AddressPrefix.EOA:
            return self.__body
        else:
            return self.__prefix.to_bytes(1, DATA_BYTE_ORDER) + self.__body

    @staticmethod
    def from_bytes_including_prefix(buf: bytes) -> Optional['Address']:
        try:
            return Address(address_prefix=AddressPrefix(buf[0]), address_body=buf[1:])
        except:
            return None

    def to_bytes_including_prefix(self) -> bytes:
        return self.__prefix.to_bytes(1, DATA_BYTE_ORDER) + self.__body

    @staticmethod
    def from_prefix_and_int(prefix: 'AddressPrefix', num: int):
        num_bytes = int_to_bytes(num)
        zero_size = 20 - len(num_bytes)
        if zero_size < 0:
            raise InvalidParamsException(f'num_bytes is over 20 bytes num: {num}')
        return Address(prefix, b'\x00' * zero_size + num_bytes)


def is_icon_address_valid(address: str) -> bool:
    """Check whether address is in icon address format or not

    :param address: (str) address string including prefix
    :return: (bool)
    """
    try:
        if isinstance(address, str) and len(address) == 42:
            prefix, body = split_icon_address(address)
            if prefix == EOA_ADDRESS_PREFIX or prefix == CONTRACT_ADDRESS_PREFIX:
                return is_lowercase_hex_string(body)
    finally:
        pass

    return False


def split_icon_address(address: str) -> (str, str):
    """Split icon address into 2-char prefix and 40-char address body

    :param address: 42-char address string
    :return: prefix, body
    """
    return address[:2], address[2:]
