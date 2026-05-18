"""Re-export the multithread_flow modules as a Python package.

The upstream yarnseamless code uses bare cross-module imports
(`split_threads.py` does `import alpha_pipeline`), which only resolve when
this folder is on `sys.path` as a top-level location — that's how
yarnseamless's `web/lama_server.py:31` set things up.

We preserve the source byte-for-byte by replicating that sys.path trick
here in the package __init__. This file runs once on first import of any
submodule and adds this folder to sys.path so the bare imports resolve.

If we ever rewrite `split_threads.py` etc. with relative imports
(`from . import alpha_pipeline`), this whole file becomes a no-op and can
be reduced to an empty marker. Until then, do not delete.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
