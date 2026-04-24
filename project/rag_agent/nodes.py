"""Compatibility facade for historical ``rag_agent.nodes`` imports.

The implementation has been moved to ``legacy_nodes.py`` as part of the node
module split. Explicitly re-export every non-dunder attribute, including private
helpers used by the existing tests, so external behavior remains unchanged.
"""

from . import legacy_nodes as _legacy_nodes


for _name in dir(_legacy_nodes):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy_nodes, _name)

__all__ = [_name for _name in globals() if not _name.startswith("__")]
