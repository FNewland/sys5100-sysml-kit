import sys

from .cli import main

try:
    sys.exit(main())
except BrokenPipeError:          # e.g. `reqlint --list-rules | head`
    sys.exit(0)
