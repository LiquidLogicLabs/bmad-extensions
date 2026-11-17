#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# ///
"""
state-record.py -- the normalised record every doctor reader emits.

Why this exists
----------------
Migration procedures once each parsed their own source shape AND wrote state directly, in
prose, so none of them was reachable by a test. Readers that emit ONE record shape make the
parsing testable and leave exactly one writer, migrate-engine.py, which carries each record
into l3io's v7 sidecars. This module is that shape, plus the two rules that must hold once
rather than per reader: validation, and the dedupe rule.

The dedupe rule has its own history. An epic shell and its full epic used to merge
into two records with one key, landing in two status folders -- on BOTH source paths,
and only one of them was ever filed. The rule now lives here, applied once where the
lists are joined, so a new reader cannot reintroduce it.

This is single-consumer code for l3io-doctor (ADR-0001) -- it is NOT shared, and
must not be added to skills/_shared/.
"""
from __future__ import annotations

KINDS = ("epic", "sprint", "story")

VALID_STATUS = {
    "epic": {"backlog", "in-progress", "done"},
    "sprint": {"backlog", "in-progress", "review", "done"},
    "story": {"backlog", "ready-for-dev", "in-progress", "review", "done", "blocked"},
}

# Ordered worst -> best. dedupe() keeps the record carrying the most information, and a
# status further along this list is later in the lifecycle -- the one a shell record
# could not have invented.
_STATUS_RANK = {
    "backlog": 0, "ready-for-dev": 1, "in-progress": 2, "blocked": 2, "review": 3, "done": 4,
}


def make_record(kind, key, status, title, source, origin=None, origin_note=None,
                classification=None, extras=None) -> dict:
    """Build a record. `origin` is omitted entirely unless given -- absent means
    'read directly from the source', which is why no schema version bump is needed.

    `classification` is top-level: it becomes a v7 entry's `class`. Only meaningful
    for stories.

    `extras` carries the fields in KNOWN_EXTRAS the source holds. Absent or empty means
    the source carried nothing beyond the typed record."""
    rec = {
        "kind": kind,
        "key": key,
        "status": status,
        "title": title,
        "source": source,
    }
    if origin is not None:
        rec["origin"] = origin
        rec["origin_note"] = origin_note or ""
    if classification:
        rec["classification"] = classification
    if extras:
        rec["extras"] = dict(extras)
    return rec


# Fields a reader surfaces in `extras`. migrate-engine.py carries L3IO_EXTRAS into l3io's v7
# sidecars and reports V7_EXTRAS as v7's: method's own migration writes a ticket's `after`,
# goal and supersession from `epics.md`, so they are listed in the plan, never written by us.
L3IO_EXTRAS = ("estimate", "actual", "orchestration", "completion_evidence", "lane",
               "previous_keys", "calibration_sampled_at", "orchestration_sampled_at",
               "blocked_reason")
V7_EXTRAS = ("goal", "superseded_by", "depends_on")
KNOWN_EXTRAS = L3IO_EXTRAS + V7_EXTRAS


def collect_extras(node: dict) -> dict:
    """Extract the subset of `node`'s fields that belong in a record's `extras`.

    Values that are empty (None, empty string, empty list, empty mapping) are
    dropped -- an empty depends_on is not information worth carrying.
    """
    out = {}
    for k in KNOWN_EXTRAS:
        v = node.get(k)
        if v is None:
            continue
        if isinstance(v, (str, list, dict)) and not v:
            continue
        out[k] = v
    return out


def validate(rec: dict) -> list:
    """Return a list of problem strings; empty means valid."""
    problems = []
    kind = rec.get("kind")
    if kind not in KINDS:
        problems.append(f"unknown kind {kind!r}")
    if not str(rec.get("key", "")).strip():
        problems.append("key is empty")
    if kind in VALID_STATUS:
        status = rec.get("status")
        if status not in VALID_STATUS[kind]:
            problems.append(
                f"invalid {kind} status {status!r} -- expected one of "
                f"{sorted(VALID_STATUS[kind])}"
            )
    if not str(rec.get("source", "")).strip():
        problems.append("source is empty")
    return problems


def _richness(rec: dict) -> tuple:
    """How much information a record carries. Higher wins a merge.

    A later-lifecycle status is what makes a full record beat a shell (backlog
    vs done). Title presence separates a stub from a real epic. Extras field
    count is the third dimension so a shell with extras (from one source) does
    not lose its data when it merges with a fuller record from another source
    that happens to carry more title/status but no extras.
    """
    return (
        1 if str(rec.get("title", "")).strip() else 0,
        _STATUS_RANK.get(rec.get("status"), -1),
        len(rec.get("extras") or {}),
    )


def dedupe(records: list) -> list:
    """Merge records sharing (kind, key), keeping the richest. Order-independent.

    One rule, applied once, where the lists are joined. An epic shell (no title,
    status backlog) and its full epic are ONE node, not two -- and must not land in
    two status folders.
    """
    best = {}
    order = []
    for rec in records:
        ident = (rec.get("kind"), rec.get("key"))
        if ident not in best:
            best[ident] = rec
            order.append(ident)
        elif _richness(rec) > _richness(best[ident]):
            best[ident] = rec
    return [best[i] for i in order]
