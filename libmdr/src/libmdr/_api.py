"""ctypes structs and prototypes for the mdr-c ABI."""

from __future__ import annotations

from . import _dll
from ._generated_api import *  # noqa: F403
from ._generated_api import bind as _bind


_bind(_dll.lib())
