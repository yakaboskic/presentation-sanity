"""`python -m presentation_sanity` — the same CLI, for environments without the script."""

import sys

from .cli import main

sys.exit(main())
