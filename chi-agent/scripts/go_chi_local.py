"""Hold the existing Go development history lock during local CHI use.

The caller must select the real, fixed local development root, not a new empty
path. For an external evaluation with no local development history this helper
is not applicable; that separation does not prove prior account usage is zero.
"""
from pathlib import Path

from opencode_go_provider import GoJournal, source_identity


def acquire_existing_history(root: Path) -> GoJournal:
    """Audit all Q runs and keep its lock until the caller closes the result."""
    return GoJournal(Path(root), "chi-maintenance", source_identity(), maintenance=True)
