#!/usr/bin/env python3
"""Start the local GUI, or check its runtime without opening a window."""
import argparse
import importlib
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='check runtime and core imports; no windows')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        print('Python 3.11+ is required. Set XLS_PYTHON to a compatible Python executable.', file=sys.stderr)
        return 1
    sys.dont_write_bytecode = True
    try:
        tk = importlib.import_module('tkinter')
    except (ImportError, OSError):
        print('Tk 8.6+ is required. Install Tk support for this Python, or set XLS_PYTHON '
              'to a Python 3.11+ executable that includes Tk.', file=sys.stderr)
        return 1
    try:
        if tk.TkVersion < 8.6:
            raise RuntimeError('Tk 8.6+ is required; this Python includes an older Tk.')
        sys.path.insert(0, str(Path(__file__).resolve().parent / 'suite' / 'multi-device'))
        gui = importlib.import_module('gui')
        if sys.platform == 'win32':
            print('Native Windows full material/build flow is not validated. WSL2 is recommended for the full flow.')
        if args.check:
            print('Runtime check passed: Python {}.{}; Tk {}; tool core imports OK. '
                  'No window opened; external build/extraction tools were not checked.'.format(
                sys.version_info.major, sys.version_info.minor, tk.TkVersion))
            return 0
        gui.main()
    except (ImportError, OSError, RuntimeError, tk.TclError) as error:
        print('Cannot start XiaomiLocalSuite: {}\nUse Python 3.11+ with Tk 8.6+; '
              'set XLS_PYTHON to its executable. On Linux, a graphical desktop is needed to open the GUI.'.format(error),
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
