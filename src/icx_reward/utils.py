import json

DEBUG = False
TAB = "\t"


def debug_print(level: int, msg: str):
    tab_print(DEBUG, level, msg)


def tab_print(enable: bool, level: int, msg: str):
    if not enable:
        return
    if level < 0:
        print(msg)
    else:
        print(f"{TAB * level}[{level}] {msg}")


def pprint(data):
    if isinstance(data, dict):
        print(json.dumps(data, indent=4))
    else:
        print(data)
