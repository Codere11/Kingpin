"""audit.py -- a head-count of what the save is about to write.

The codec already reports any field it cannot write.  This adds the shape of
the job as one line in saves/save.log: how many camps, people, built things
and edited regions there are.  A number that drops to zero between two saves
is the first symptom of a provider that has stopped finding its objects.
"""

from __future__ import annotations

from . import store


def report(g, counts: dict) -> None:
    try:
        parts = "  ".join("%s=%s" % (k, v) for k, v in sorted(counts.items()))
        store.log("snapshot: " + parts)
    except Exception:
        pass
