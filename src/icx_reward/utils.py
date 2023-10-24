import json
import sys

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


def print_progress(iteration, total, prefix='', suffix='', decimals=1, bar_length=100):
    format_str = "{0:." + str(decimals) + "f}"
    percent = format_str.format(100 * (iteration / float(total)))
    filled_length = int(round(bar_length * iteration / float(total)))
    bar = '#' * filled_length + '-' * (bar_length - filled_length)
    sys.stdout.write('\r%s |%s| %s%s %s' % (prefix, bar, percent, '%', suffix)),
    if iteration == total:
        sys.stdout.write('\n')
    sys.stdout.flush()
