"""In-process test helpers (also used by ``repopulse.scripts.benchmark``).

Keeping :func:`make_inmem_orchestrator` under ``src/`` avoids importing the
``tests`` package from production scripts.
"""

from repopulse.testing.inmem import InMemoryState, make_inmem_orchestrator

__all__ = ["InMemoryState", "make_inmem_orchestrator"]
