import os
from argparse import ArgumentParser

from . import commands
from .argparse_type import IconAddress, non_negative_num_type


def environ_or_required(key):
    default_value = os.environ.get(key)
    if default_value:
        return {"default": default_value}
    return {"required": True}


def add_uri(subparser):
    subparser.add_argument("--uri", help="URI of endpoint", **environ_or_required("ICON_ENDPOINT_URI"))


def add_address(subparser):
    subparser.add_argument("--address", type=IconAddress(), help="address of account")


def add_height(subparser):
    subparser.add_argument("--height", type=non_negative_num_type, default=None, help="height of block")


parser = ArgumentParser(prog="icx-reward")
subparsers = parser.add_subparsers(dest="command", help="Command to execute")

cmds = [
    ("query", "query I-Score of account", [add_uri, add_address, add_height]),
    ("term", "get Term information", [add_uri, add_height]),
    ("check", "check I-Score of account", [add_uri, add_address, add_height]),
]
for cmd in cmds:
    p = subparsers.add_parser(cmd[0], help=cmd[1])
    for func in cmd[2]:
        func(p)


def run():
    args = vars(parser.parse_args())
    if not args["command"]:
        parser.error("no command given")

    func = getattr(commands, args["command"].replace("-", "_"))
    func(args)
