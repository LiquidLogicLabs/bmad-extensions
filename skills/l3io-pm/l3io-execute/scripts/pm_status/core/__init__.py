"""pm_status.core -- the dependency root: primitives nothing else in the package is
below.

Constants and the status vocabulary, the ruamel round-trip, atomic file writes, the
`.gitignore` rules that keep lock files out of git, every lock family (including the epic
lock), the error/exit-code contract, the key shapes and canonicalisers, the event-log
WRITER and value helpers. It registers no verb: like `nodes`, it owns none.

It imports nothing from this package, and that is checked rather than asserted: the
boundary measurement resolves every name referenced in these definitions against the rest
of `__main__.py` and reports zero upward edges. Keep it that way -- a single import back
up makes the package a cycle and `__main__.py` unextractable.

CALL STYLE ACROSS MODULES. Five names here are mock.patch targets in the suite:
`_atomic_dump`, `_load`, `_atomic_text_write`, `notices_lock` and `agent_instructions_lock`.
Reach them as `core.<name>` from the module object, never through a
`from .core import <name>` binding -- that binding is a private copy, so a patch on this
module never reaches it and the test passes while guarding nothing. The other names are
re-exported into `__main__` by name for the facade's sake; promote any of them to
module-qualified calls the moment the suite starts patching it.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime

try:
    from ruamel.yaml import YAML
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "pm-status.py: ruamel.yaml is required. Run via `uv run` (auto-provisions it) "
        "or `pip install ruamel.yaml`.\n"
    )
    sys.exit(2)

# --------------------------------------------------------------------------- #
# Version, and the status/metric vocabulary every layer above validates against.
# --------------------------------------------------------------------------- #
# The constant half of the version, which `--version` and `report` print. The other half is
# `__main__.py`'s top-of-file `# pm-status-version:` marker, which the doctor reads off each
# installed copy without running it; check:version finds this declaration by searching the
# package and fails unless the two agree.
PM_STATUS_VERSION = "3.7.1"


METRIC_FIELDS = ("elapsed_hours", "man_hours", "hitl_hours", "tokens_k", "cost")

# The subset of METRIC_FIELDS whose SCOPE ratio is learned. `cost` is derived
# from tokens x rates (Tasks 6/7) rather than entered or actualed on its own,
# so letting it also accumulate a scope-ratio sample would give a derived
# value an independently-learned correction — exactly the drift this rework
# removes. `cost` deliberately stays IN METRIC_FIELDS: it is still stored,
# verified, and reported, just never scope-calibrated. Derived (not restated)
# from METRIC_FIELDS so the two can't drift apart the way separately-typed
# copies did before.
CALIBRATED_METRIC_FIELDS = tuple(m for m in METRIC_FIELDS if m != "cost")


# --------------------------------------------------------------------------- #
# Key shapes: pure string vocabulary, no filesystem knowledge. The event log and the
# ADR register still carry epic and sprint keys, so a key spelled 'E1' and one spelled
# '001' must compare equal.
# --------------------------------------------------------------------------- #


def _norm_num(v, width: int) -> str:
    """Normalize a possibly key-prefixed or unpadded numeric id to a zero-padded digit
    string: 'E1'/'001' -> '001' (width=3); 'S1'/'01' -> '01' (width=2). Falls back to the
    stripped original string when it is not purely numeric, so a malformed stored value
    still compares by equality instead of raising."""
    s = str(v).strip()
    core = s.lstrip("EeSs")
    if core.isdigit():
        return f"{int(core):0{width}d}"
    return s


def canonical_epic_key(v) -> str:
    """'3'/'03'/'003'/'E3'/'e003' -> 'E003'. The KEY form, for files that store keys.

    `events.jsonl` stores key form ('E003') because its story records derive `epic` from
    `parse_story_key`, which yields 'E001'. Normalise to the form the file already uses, and
    never store the caller's spelling.
    """
    return "E" + _norm_num(v, 3)


def canonical_sprint_key(v) -> str:
    """'1'/'01'/'S1'/'s01' -> 'S01'. See canonical_epic_key for why two forms exist."""
    return "S" + _norm_num(v, 2)


# --------------------------------------------------------------------------- #
# YAML round-trip and atomic writes -- the primitives every write in the package goes
# through. _load and _atomic_dump are patch targets: call them as core._load(...)
# from any other module, never through a `from .core import` binding, or a
# mock.patch on this module cannot reach the call.
# --------------------------------------------------------------------------- #
def _yaml() -> YAML:
    y = YAML()  # round-trip mode: preserves comments + key order
    y.preserve_quotes = True
    y.width = 4096  # never line-wrap scalars
    y.indent(mapping=2, sequence=2, offset=0)  # match the flush-dash status-file style
    return y


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: str):
    y = _yaml()
    if not os.path.exists(path):
        return y, None
    with open(path, "r", encoding="utf-8") as f:
        return y, y.load(f)


def _atomic_dump(y: YAML, data, path: str) -> None:
    """Write to a temp file in the same directory, then os.replace (atomic on POSIX)."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pm-status.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            y.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_text_write(path: str, text: str) -> None:
    """Temp file beside the target, fsync, then os.replace. Unlike `_atomic_dump` this takes
    no epic lock -- the target is a user-owned document outside the state tree, so the
    epic-lock invariant does not apply and asserting it would fail every call. `newline=""`
    is load-bearing: the engine already matched the file's CRLF convention, and Python's
    default translation would rewrite every line ending.

    We are a guest in the user's file, so two things are preserved: a symlink (the path is
    resolved first, so the link's real target is what changes and the link survives, with
    the temp file in the RESOLVED directory so os.replace cannot cross devices) and the
    file's mode (mkstemp makes 0600; an existing file's mode is copied, a new file gets
    0666 & ~umask)."""
    path = os.path.realpath(path)
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".l3io-ai-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _atomic_create(path: str, text: str) -> bool:
    """Create `path` with `text` only if it does not already exist -- atomically and without
    ever clobbering: write a temp file in the same directory, fsync it, then os.link it into
    place (link fails with FileExistsError when the path exists, where os.replace would
    overwrite). Returns False when the path already existed. The temp file is removed on
    every path, success or failure."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pm-status.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Lock-file hygiene: one mechanism puts both `*.lock` and the notices ledger into the
# state root's own .gitignore, so neither is ever committed.
# --------------------------------------------------------------------------- #
# State roots whose .gitignore this process has already checked (_ensure_lock_ignore).
_LOCK_IGNORE_CHECKED = set()
_LOCK_IGNORE_LINE = "*.lock"
NOTICES_FILENAME = ".notices.yaml"  # the one-time-ever advisory ledger, keyed on --key
                                     # alone (the `notice` verb, which stays above core) --
                                     # no pruning: a project's set of distinct notice keys
                                     # stays small by construction
# Every filename pm-status.py writes at a state root that must never reach git: the
# per-family lock sidecars (one glob covers all of them) and the notices ledger.
_GITIGNORE_PATTERNS = (_LOCK_IGNORE_LINE, NOTICES_FILENAME)


def _lock_rule_present(text: str, pattern: str = _LOCK_IGNORE_LINE) -> bool:
    """True when git reads `text` (a .gitignore) as ignoring every `pattern`: some line is
    exactly `pattern` and no LATER line is exactly `!pattern`. Parsed as git parses it: split
    on "\\n" only -- never str.splitlines(), which also breaks on U+0085 and other characters
    git keeps inside a line -- and strip exactly one trailing "\\r", then trailing spaces,
    since leading spaces are part of the pattern. The caller decodes with utf-8-sig, so a
    leading UTF-8 BOM is skipped, as git skips it. A narrower negation such as `!keep.lock`
    is a deliberate user choice and is left as written."""
    present = False
    for raw in text.split("\n"):
        line = raw.removesuffix("\r")
        line = line.rstrip(" ")
        if line == pattern:
            present = True
        elif line == "!" + pattern:
            present = False
    return present


def _missing_ignore_patterns(text: str, patterns=_GITIGNORE_PATTERNS):
    """Which of `patterns` git does NOT currently read `text` as ignoring."""
    return [p for p in patterns if not _lock_rule_present(text, p)]


def _ensure_lock_ignore(state_root: str, patterns=_GITIGNORE_PATTERNS) -> None:
    """Make `{state_root}/.gitignore` carry every pattern in `_GITIGNORE_PATTERNS` --
    `*.lock` and `.notices.yaml` -- so neither a lock file nor the notices ledger is ever
    committed.

    Every lock file this script creates is an empty flock target -- the several families in
    the state root and the per-node `.yaml.lock` sidecars below it -- and a run commits the
    whole state root; `.notices.yaml` is the one non-lock file this script writes at the
    state root that is equally advisory and equally not for git. Neither pattern matches the
    state-root directory itself, so a `git check-ignore` of it still passes.

    Called on EVERY lock acquisition inside a state root, not only when a pattern's file is
    first written: a project whose lock files already exist, or that adopts a newer
    pm-status.py that adds a pattern, gets the missing rule(s) on its next lock. A lock
    taken with no state root is skipped, so it never writes a .gitignore into a repo root
    (_file_lock). Memoized per
    process, so each state root is checked at most once. Absent file -> created (no-clobber
    _atomic_create) with one comment line and every pattern. Present -> READ first, and only
    when at least one pattern is missing (as git reads it, _lock_rule_present) is it opened
    for append and flocked, then re-checked under the flock so two processes cannot both
    append it -- only the still-missing patterns are written, so an already-satisfied pattern
    is never duplicated; a read-only .gitignore that already has every pattern is never opened
    for writing. Missing lines are appended after a newline when the file lacks a trailing
    one; existing content is never rewritten or reordered. Best-effort: this runs inside the
    lock path, so an OSError or an undecodable file warns once on stderr and returns -- it
    never raises and never fails the verb.

    `patterns` narrows what is written, for a directory that is not a state root: the
    agent-instruction lock under `_bmad/` needs only `*.lock`, not the notices ledger."""
    root = os.path.realpath(state_root or ".")
    if root in _LOCK_IGNORE_CHECKED:
        return
    _LOCK_IGNORE_CHECKED.add(root)
    path = os.path.join(root, ".gitignore")
    try:
        if not os.path.lexists(path) and _atomic_create(
                path, "# pm-status.py state files -- never commit\n" +
                      "".join(f"{p}\n" for p in patterns)):
            return
        with open(path, "rb") as fh:                # read first: needs no write access
            if not _missing_ignore_patterns(fh.read().decode("utf-8-sig"), patterns):
                return
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            fcntl = None
        with open(path, "a+b") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.seek(0)
                text = fh.read().decode("utf-8-sig")   # re-check under the flock; BOM skipped
                missing = _missing_ignore_patterns(text, patterns)
                if not missing:
                    return
                sep = "" if not text or text.endswith("\n") else "\n"
                fh.write((sep + "".join(f"{p}\n" for p in missing)).encode("utf-8"))
                fh.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except (OSError, UnicodeDecodeError) as e:
        sys.stderr.write(f"pm-status.py: warning -- could not add "
                         f"{', '.join(patterns)} to {path}: {e}\n")


# --------------------------------------------------------------------------- #
# Errors and the exit-code contract.
# --------------------------------------------------------------------------- #
def _die_usage(msg: str):
    sys.stderr.write(f"pm-status.py: {msg}\n")
    sys.exit(2)


def _die_notfound(what: str):
    sys.stderr.write(f"pm-status.py: node not found — {what}\n")
    sys.exit(3)


class PMError(Exception):
    """A refusal or failure raised by a non-exiting core function.

    Core functions never call sys.exit: in-process callers -- promote-issue's
    estimate -- must be able to catch a failure. Only a cmd_
    wrapper turns one into an exit code, through _run_core."""

    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _run_core(fn) -> int:
    """Run a cmd_ body, mapping PMError onto the exit-code contract."""
    try:
        return fn()
    except PMError as e:
        sys.stderr.write(f"pm-status.py: {e.msg}\n")
        return e.code


# --------------------------------------------------------------------------- #
# The event-log WRITER. Its readers (dwell, dispatch windows, the events index) are a
# metrics concern and stay above; appending is a primitive, because every status and
# actuals write reaches it and it must never be able to fail its caller.
# --------------------------------------------------------------------------- #
EVENTS_FILENAME = "events.jsonl"


def events_path(state_root: str) -> str:
    """The one project-level event log. A single log (not one per sprint) keeps the
    progress report a single read and makes cross-epic velocity computable."""
    return os.path.join(state_root, EVENTS_FILENAME)


def append_event(state_root: str, payload: dict) -> None:
    """Append one JSON line under flock. NEVER raises: telemetry must not be able to
    fail a status write, matching the calibration contract in set-actual."""
    try:
        p = events_path(state_root)
        os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
        line = json.dumps(payload, sort_keys=True) + "\n"
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            fcntl = None
        with open(p, "a", encoding="utf-8") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as e:  # noqa: BLE001 - deliberate: never fail the caller
        sys.stderr.write(f"pm-status.py: warning — could not append event: {e}\n")


# --------------------------------------------------------------------------- #
# State-root files that have a lock family, and the lock families themselves. Each path
# function sits with its lock rather than with the code that reads the file: the lock
# needs it first, and every reader goes through the lock.
# --------------------------------------------------------------------------- #
def calibration_path(state_root: str) -> str:
    return os.path.join(state_root, "pm-calibration.yaml")


def adr_register_path(state_root: str) -> str:
    return os.path.join(state_root, "adr-register.yaml")


def notices_path(state_root: str) -> str:
    return os.path.join(state_root, NOTICES_FILENAME)


# Re-entrant within a process: flock is held per open file description, so a
# second open()+LOCK_EX from the same process would deadlock against itself.
# The depth counter lets save_calibration nest inside calibration_lock (which
# is exactly what the record_* paths do) without reacquiring.
_CAL_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def _file_lock(lock_path: str, depth_state: dict, state_root: str | None = None):
    """Exclusive flock over a read-modify-write cycle, reentrant per process.

    Extracted from calibration_lock so the ADR register can hold a lock without a
    second implementation. The reentrancy counter is the part that must not be
    re-derived by hand: a nested acquire that re-opens the file drops the outer
    hold on close, and the failure only appears under real parallelism.

    `depth_state` is a dict private to one lock family (e.g. `_CAL_LOCK` or
    `_ADR_LOCK`) with at least a `"depth"` key; each family gets its own dict so
    a calibration hold and an ADR-register hold never share depth counting.

    `state_root` is the root whose .gitignore gets `*.lock` (_ensure_lock_ignore). The
    calibration and ADR families pass theirs. Without one, no .gitignore is touched: the
    lock's own directory might be the repo root, where `*.lock` would
    silently ignore uv.lock, yarn.lock and Cargo.lock repo-wide.
    """
    if depth_state["depth"] > 0:               # already held by this process
        depth_state["depth"] += 1
        try:
            yield
        finally:
            depth_state["depth"] -= 1
        return
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX
        sys.stderr.write(f"pm-status.py: fcntl unavailable — {lock_path} is not "
                         f"lock-protected (non-POSIX)\n")
        yield
        return
    lock_dir = os.path.dirname(os.path.abspath(lock_path)) or "."
    os.makedirs(lock_dir, exist_ok=True)
    if state_root is not None:
        _ensure_lock_ignore(state_root)
    fh = open(lock_path, "w")  # noqa: SIM115 -- the fd outlives this statement; flock holds it until the finally
    fcntl.flock(fh, fcntl.LOCK_EX)
    depth_state["depth"], depth_state["fh"] = 1, fh
    try:
        yield
    finally:
        depth_state["depth"], depth_state["fh"] = 0, None
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()


@contextlib.contextmanager
def calibration_lock(state_root: str):
    """Hold an exclusive lock over a whole calibration read-modify-write cycle.

    `save_calibration` alone is not enough: load -> mutate -> save is not atomic,
    so two parallel `set-actual` calls could both load the same file and the
    second save would drop the first's sample. Callers that mutate must wrap the
    load AND the save in this.
    """
    with _file_lock(calibration_path(state_root) + ".lock", _CAL_LOCK, state_root):
        yield


_ADR_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def adr_register_lock(state_root: str):
    """Hold an exclusive lock over a whole ADR-register read-modify-write cycle.

    Same reasoning as calibration_lock: load -> mutate -> save is not atomic, and
    this is exactly the register two parallel adr-reserve calls must not race on.
    """
    with _file_lock(adr_register_path(state_root) + ".lock", _ADR_LOCK, state_root):
        yield


_NOTICES_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def notices_lock(state_root: str):
    """Hold an exclusive lock over a whole notices read-modify-write cycle.

    Same reasoning as calibration_lock and adr_register_lock: load -> mutate -> save is
    not atomic, and two concurrent callers -- e.g. `l3io-execute` and `l3io-plan`
    invoked around the same time in one project -- must not both decide the same key has
    not been shown yet and each write their own "now recorded" copy, silently dropping one.
    """
    with _file_lock(notices_path(state_root) + ".lock", _NOTICES_LOCK, state_root):
        yield


_AGENT_INSTR_LOCK = {"depth": 0, "fh": None}


@contextlib.contextmanager
def agent_instructions_lock(project_root: str):
    """Exclusive lock over the whole read-modify-write of an AI instruction file.

    Same reasoning as notices_lock: two skills activating at once must not both read the
    pre-write text and let the second overwrite the first's block. The lock file lives under
    `_bmad/` -- the tool's own directory -- never beside the user's document, and `*.lock`
    is added to `_bmad/.gitignore` on every acquisition (self-healing, additive, via
    `_ensure_lock_ignore`). state_root is None for `_file_lock` because `_bmad/` is not a
    state root and would otherwise also receive the notices pattern.
    """
    bmad = os.path.join(project_root, "_bmad")
    _ensure_lock_ignore(bmad, (_LOCK_IGNORE_LINE,))
    with _file_lock(os.path.join(bmad, ".agent-instructions.lock"),
                    _AGENT_INSTR_LOCK, None):
        yield


# --------------------------------------------------------------------------- #
# Value helpers: parsing, coercion and the estimate/actual accessors. Pure, no I/O
# except the two that read a file's bytes.
# --------------------------------------------------------------------------- #
def _parse_iso(ts):
    """Parse a pm-status timestamp into an aware datetime, or None if unusable."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).strip())
    except (TypeError, ValueError):
        return None


def _hashable_field(v):
    """A hashable stand-in for a field read out of `events.jsonl`.

    Used by every reader over that log that keys a dict on a record field. The log is
    append-only, written by concurrent flock'd writers and documented as possibly torn,
    so a field can hold any JSON type -- and a list or a dict is unhashable, which turns
    `idx[rec["key"]]` into `TypeError: unhashable type` and takes down the reader.

    The readers all guarded the RECORD (`isinstance(rec, dict)`) and none guarded a
    field inside it, so the same defect existed four times over: in
    `_dispatch_identity`, where it crashed `report --watch`; in `build_events_index`,
    where `ev.get("key")` was only truthy-checked and a non-empty list is truthy; and in
    `actual_event_times`, where `k not in idx` raises exactly as a subscript does -- a
    membership test is not the safe alternative to indexing.

    `str()` is a floor that keeps the scan alive and the record distinguishable, not a
    conversion any caller should rely on: a malformed field has no correct value, and
    inventing one would be worse than carrying it through as its own repr.

    Carrying through is right HERE and wrong for an index -- see `_indexable_key`.
    """
    return v if isinstance(v, (str, int, float, bool)) else str(v)


def _indexable_key(v):
    """A node key usable as an index key, or None when the field cannot be one.

    The counterpart to `_hashable_field`, and the difference is the reader's job, not a
    preference. `_dispatch_identity` only needs INTERNAL consistency -- an open and its
    close hashing alike -- so a malformed field carried through under its repr still
    matches its own close, and dropping it would make that dispatch permanently
    uncloseable. An index keyed by node key is looked up BY a real node key, so a value
    that no node could ever have is not a key: carrying it adds a phantom entry
    corresponding to nothing, and dropping it loses nothing real.

    Returns None for a list, a dict, or an empty/whitespace-only string. The caller
    skips the record, which is what "a torn line must not kill the read" has always
    meant one level up.
    """
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        return None
    k = str(v).strip()
    return k or None


def _num_or_none(v):
    """Parse a metric value, tolerating a leading '$' on cost. None if not numeric.

    Normalizing before the numeric guard (rather than after) matters: a
    check-then-lstrip order lets a '$'-prefixed cost fail _is_number and get
    skipped before the lstrip ever runs, silently starving the cost
    component of samples. This is the single normalization both the guard
    and the parse share, so they can't disagree.
    """
    if v is None or _is_na(v):
        return None
    s = str(v).strip().lstrip("$")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _actual_metric(actual: dict, metric: str):
    """A metric's numeric actual. tokens_k is a mapping now — the total is what
    is banded and calibrated; the class split prices cost and nothing else.
    """
    v = (actual or {}).get(metric)
    if metric == "tokens_k" and hasattr(v, "get"):
        v = v.get("total")
    return _num_or_none(v)


def _estimate_metric(est: dict, metric: str):
    """A metric's numeric value from an ESTIMATE block. The single-value
    (story) form of `tokens_k` is a MAPPING (`tokens_block`'s `total` + the
    four per-class counts, since Tasks 6/7) — the same shape `_actual_metric`
    unwraps above, mirrored here for the estimate side.

    EVERY reader of an estimate's tokens_k must go through this, never
    `_num_or_none(est.get(metric))` directly. That direct form is exactly what
    silently zeroed two independent things before Task 10 found and fixed the
    first: `_child_estimate_value` (a sprint/epic roll-up would see zero
    children with a tokens_k estimate, the roll-up would just never emit
    `tokens_k_min`/`tokens_k_max`) and `derive_story_sample` (a story's
    tokens_k scope ratio never accumulated a sample — cold-start forever,
    silently, for the metric the whole cost derivation now hangs off). Both
    call sites now route through here so a fourth instance can't reintroduce
    the same blind spot by hand-duplicating the unwrap.
    """
    v = (est or {}).get(metric)
    if metric == "tokens_k" and hasattr(v, "get"):
        v = v.get("total")
    return _num_or_none(v)


def _iter_count(v):
    """fix_iterations as a non-negative int, or None if it is not one.

    Tolerant on the way in because historical nodes hold strings, and total: an
    unparseable value returns None rather than raising. `int(v)` alone raised
    ValueError on '0.0' -- inside `derive_story_sample` that aborted the whole
    sample, so a story with zero rework contributed nothing instead of the exact
    scope reading it should have.
    """
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != int(f) or f < 0:
        return None
    return int(f)


def _exit_code_or_fail(v) -> int:
    """An exit code that will not parse is a failure, never a pass.

    test_runs is hand-editable YAML, and `_iter_count` already exists here
    because historical nodes hold strings. Same tolerance — but the fallback is
    asymmetric on purpose: an unreadable exit code must never derive
    `tests_passing: true`.
    """
    try:
        return int(v)
    except (TypeError, ValueError):
        return 1


def _mid(est, low_key: str, high_key: str):
    """Midpoint of a range-form estimate. None if either bound is missing/non-numeric."""
    lo, hi = _num_or_none(est.get(low_key)), _num_or_none(est.get(high_key))
    if lo is None or hi is None:
        return None
    return (lo + hi) / 2.0


def _is_na(v) -> bool:
    return isinstance(v, str) and v.strip().upper() in {"N/A", "NA", "NONE", ""}


def _is_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _coerce(field: str, v: str):
    """Numeric metrics become int/float unless N/A. `cost` is derived, not entered;
    the only string it can be here is N/A."""
    if _is_na(v):
        return v
    try:
        f = float(v)
        return int(f) if f.is_integer() and field != "cost" else f
    except ValueError:
        return v
