"""Enable `python -m impact_gate`, so the installed git hook can invoke the tool by
interpreter path without depending on the `impact-gate` script being on PATH."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
