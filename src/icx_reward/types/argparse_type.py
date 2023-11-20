import re
from argparse import ArgumentTypeError


def is_lowercase_hex_string(value: str) -> bool:
    """Check whether value is hexadecimal format or not

    :param value: text
    :return: True(lowercase hexadecimal) otherwise False
    """

    try:
        result = re.match('[0-9a-f]+', value)
        return len(result.group(0)) == len(value)
    except:
        pass

    return False


def is_icon_address_valid(address: str) -> bool:
    """Check whether address is in icon address format or not

    :param address: (str) address string including prefix
    :return: (bool)
    """
    try:
        if isinstance(address, str) and len(address) == 42:
            prefix, body = address[:2], address[2:]
            if prefix == "hx" or prefix == "cx":
                return is_lowercase_hex_string(body)
    finally:
        pass

    return False


class IconAddress(str):
    def __init__(self, prefix: str = 'all'):
        self._prefix = prefix

    def __call__(self, string: str) -> str:
        # check prefix of given address (string). if not 'cx' or 'hx', raise error
        if not is_icon_address_valid(string):
            raise ArgumentTypeError(f"Invalid address '{string}'")

        if self._prefix != 'all':
            if self._prefix != string[:2]:
                raise ArgumentTypeError(f"Invalid address '{string}'. Address must start with '{self._prefix}'")

        return string


def is_valid_hash(_hash: str) -> bool:
    """Check hash is valid.

    :param _hash:
    :return:
    """
    if isinstance(_hash, str) and len(_hash) == 66:
        prefix, body = _hash[:2], _hash[2:]
        return prefix == '0x' and is_lowercase_hex_string(body)

    return False


def hash_type(string: str) -> str:
    # check hash's length, prefix, lowercase.
    if not is_valid_hash(string):
        raise ArgumentTypeError(f"Invalid hash '{string}'")

    return string


def num_type(string: str) -> int:
    try:
        value = int(string, 10)
    except ValueError:
        try:
            value = int(string, 16)
        except ValueError:
            raise ArgumentTypeError(f"Invalid integer value '{string}'. Hexadecimal and decimal values are allowed")
    except TypeError as e:
        raise ArgumentTypeError(f'Invalid type. {e}')
    return value


def non_negative_num_type(string: str) -> int:
    value = num_type(string)
    if value < 0:
        raise ArgumentTypeError(f"Invalid non-negative number '{value}'")
    return value

