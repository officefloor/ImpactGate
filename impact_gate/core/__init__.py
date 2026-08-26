"""Self-contained structural change-impact core.

Vendored so the tool is standalone — no dependency on the (concluded) Surveyor
bug-finding experiment. Importing this package registers the default lizard plugin.
"""
from .units import Unit, get_plugin, register        # noqa: F401
from . import lizard_plugin                           # noqa: F401  (registers default plugin)
from .impact import FileImpact, UnitImpact, compute_file_impact  # noqa: F401
from .config import MeasureConfig                     # noqa: F401
from .gitplumb import GitRepo, parse_diff             # noqa: F401
