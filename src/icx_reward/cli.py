import argparse
import os
import sys
from argparse import ArgumentParser

from icx_reward import commands
from icx_reward.types.argparse_type import IconAddress, non_negative_num_type, num_type


def environ_or_required(key):
    default_value = os.environ.get(key)
    if default_value:
        return {"default": default_value}
    return {"required": True}


def add_uri(subparser):
    subparser.add_argument("--uri", help="URI of endpoint", **environ_or_required("ICON_ENDPOINT_URI"))


def add_address(subparser, required: bool = True):
    subparser.add_argument("--address", type=IconAddress(), help="address of account", required=required, default=None)


def add_address_optional(subparser):
    add_address(subparser, False)


def add_time(subparser):
    subparser.add_argument("--height", type=non_negative_num_type, default=None, help="height of block")
    subparser.add_argument("--term", type=num_type, default=None,
                           help="Sequence of Term. Negative value N means last + N sequence")


def add_export_vote(subparser, required: bool = False):
    subparser.add_argument("--export", help="export vote events to file",
                           type=argparse.FileType('w'), default=None, required=required)


def add_import_vote(subparser, required: bool = False):
    subparser.add_argument("--import", help="import vote events from file",
                           type=argparse.FileType('r'), default=None, required=required)


parser = ArgumentParser(prog="icx-reward")
subparsers = parser.add_subparsers(dest="command", help="Command to execute")

cmds = [
    ("check", "check I-Score of account", [add_uri, add_address, add_time, add_export_vote, add_import_vote]),
    ("fetch-vote", "fetch all vote events in given Term", [add_uri, add_time, add_address_optional, add_export_vote]),
    ("fetch-penalty", "fetch penalties of account in given Term", [add_uri, add_address_optional, add_time]),
    ("query", "query I-Score of account", [add_uri, add_address, add_time]),
    ("term", "get Term information", [add_uri, add_time]),
]
for cmd in cmds:
    p = subparsers.add_parser(cmd[0], help=cmd[1])
    for add_arg_func in cmd[2]:
        add_arg_func(p)


def run():
    args = vars(parser.parse_args())
    if not args["command"]:
        parser.error("no command given")

    if args.get("height") is not None and args.get("term") is not None:
        print(f"Do not set --height and --term together")
        sys.exit(-1)

    func = getattr(commands, args["command"].replace("-", "_"))
    func(args)


if __name__ == '__main__':
    run()
