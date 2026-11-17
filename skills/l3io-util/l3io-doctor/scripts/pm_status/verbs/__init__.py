"""pm_status.verbs -- the single-node writes: `import-node`, `set-estimate`, `add-test-run`,
`verify` and `notice`.

`import-node` is the migration's writer and retires with it in Phase 6; `set-estimate`,
`add-test-run` and `verify` keep the 3.x node addressing that migration still writes
through, beside the v7 addressing `sidecar.verbs` routes. Nothing below this module imports
it; only `__main__.py` (the parser and `main`) and `sidecar.verbs` reach these functions.

CALL STYLE ACROSS MODULES. Every name the suite patches is reached through its MODULE OBJECT:
`core._load` / `core._atomic_dump` / `core.notices_lock`, `nodes.save_node`. A by-name
binding here would be a private copy the patch could never reach, and the test would pass
while guarding nothing. Names nothing patches are imported by name. None of the patch
targets is re-exported by this module or by `__main__.py`.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from .. import core, nodes
from ..core import (
    METRIC_FIELDS,
    VALID_EPIC_STATUS,
    VALID_SPRINT_STATUS,
    VALID_STORY_STATUS,
    _die_notfound,
    _die_usage,
    _event_keys,
    _exit_code_or_fail,
    _is_na,
    _is_number,
    _now_iso,
    _num_or_none,
    _yaml,
    append_event,
    node_args,
    notices_path,
    parse_story_key,
)
from ..metrics.rates import TOKEN_CLASSES, cost_matches, rate_overrides
from ..nodes import (
    _epic_write_lock,
    _infer_kind,
    _load_checked,
    _sprint_key_from_dir,
    check_backrefs,
    ensure_node_path,
    list_sprint_dirs,
    list_story_files,
    load_node,
    sprint_file,
    story_file,
)
from ..sidecar import entry_address_args, plan_address_args


def cmd_notice(args) -> int:
    """Record a one-time-ever advisory notice for this project. Exit 0 = emit it now (and
    record it), exit 1 = already emitted for this key, exit 2 = usage error OR an unexpected
    failure while recording (lock/I/O). 2 is deliberately overloaded with "usage error"
    rather than given a new number of its own: a caller that treats any nonzero exit as "do
    not print the pointer" already handles it correctly either way, and the one distinction
    that matters -- 1 means "already said, all is well" -- stays unambiguous. A crash must
    never surface as 1: a caller told "already emitted" says nothing further and moves on,
    so a masked crash would silently and permanently suppress the pointer with nothing to
    show for it.

    Scope is the KEY ALONE, not a session: there is no notion of "session" that outlives one
    skill invocation (`{session_id}` in `step-00-activate.md` is bound fresh per invocation
    and no caller of `notice` is ever a dispatched subagent that could inherit one), so a
    per-session key would never repeat and this would fire every single invocation -- exactly
    the nagging it exists to prevent. A key is recorded at most once, ever, per project: once
    a key has fired, it never fires again for that `--state-root`, which is correct for an
    advisory whose content is static ("this exists, configure it if you want") and whose
    trigger condition (`modules.l3io-pm` being absent) is itself a valid permanent state, not
    a transient one to keep re-flagging.

    An absent or unparseable notices file means nothing has been emitted yet -- a notice is
    advisory only, so a damaged file must never block the caller's real work; it is simply
    treated as empty and rewritten clean on this call. That tolerance covers a bad READ only:
    a failure while actually recording (the lock, or the write itself) is a real failure and
    is reported as one, not folded into "already emitted" or silently swallowed as success.
    """
    key = (args.key or "").strip()
    if not key:
        sys.stderr.write("notice: --key must be non-empty\n")
        return 2
    path = notices_path(args.state_root)
    try:
        os.makedirs(args.state_root, exist_ok=True)
        with core.notices_lock(args.state_root):
            # _load returns (yaml_instance, data) -- data is None when the file is absent
            # or fails to parse the way _load's caller expects. Reuse the returned YAML
            # instance for the dump so round-trip settings (width, indent, quote style)
            # match.
            try:
                y, data = core._load(path)
            except Exception:  # noqa: BLE001 -- a notice ledger that cannot be read is rebuilt, never fatal
                y, data = _yaml(), None
            keys = data.get("keys") if isinstance(data, dict) else None
            if not isinstance(keys, list):
                keys = []
            if key in keys:
                return 1
            keys.append(key)
            core._atomic_dump(y, {"keys": keys}, path)
    except Exception as e:  # noqa: BLE001 -- recording a notice must never fail the command it advises
        sys.stderr.write(f"notice: could not record the notice at {path}: {e}\n")
        return 2
    return 0


# --------------------------------------------------------------------------- #
# import-node: the migration's writer
# --------------------------------------------------------------------------- #
EPIC_KEY_RE = re.compile(r"^E\d{3}$")
STORY_KEY_RE = re.compile(r"^E\d{3}-S\d{2}-\d{3}$")
# status-files.md §11: `depends_on` lives on BOTH an epic node (epic keys) and a story node
# (story keys). Reading only that section's first sentence gives the epic case and silently
# loses the story case, which is the shape the migration fixtures actually carry.
DEPENDS_ON_KEY_RE = {"epic": EPIC_KEY_RE, "story": STORY_KEY_RE}


def cmd_import_node(args) -> int:

    """Create a state node from a migration record (`migrate-engine.py`'s only writer).

    The node, its status, and the scalar and list fields a migration record carries
    (`--goal`, `--superseded-by`, `--depends-on`) land in one write under the epic lock,
    with one `import` event. Every `--depends-on` key is validated before anything is
    written, because a half-applied dependency list is worse than an absent one.

    Idempotent by SKIP, not by overwrite. A migration retried after a partial run must
    not clobber a node a later step already edited, so an existing file is left exactly
    as it is and reported.
    """
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQ

    kind = _infer_kind(args)
    valid = {
        "story": VALID_STORY_STATUS,
        "sprint": VALID_SPRINT_STATUS,
        "epic": VALID_EPIC_STATUS,
    }[kind]
    if args.status not in valid:
        _die_usage(
            f"invalid {kind} status '{args.status}' -- expected one of {sorted(valid)}")

    # blocked_reason gate: a story imported at `status: blocked` must carry a --reason. Migration sources that carry blocked state (bmad-loop
    # is the shape) preserve the reason on the record; a source that reports blocked but
    # cannot preserve the reason is a broken source, not an acceptable import shape.
    # Sprints and epics don't have `blocked` in their status enum, so the guard is
    # story-only by construction.
    reason = str(getattr(args, "reason", "") or "").strip()
    if kind == "story" and args.status == "blocked" and not reason:
        _die_usage("--status blocked requires --reason \"<why>\" -- a blocked story with no "
                   "reason on record is what this flag exists to prevent")
    if kind != "story" and reason:
        _die_usage("--reason is a story-only flag; sprint/epic status sets have no blocked")
    if kind == "story" and args.status != "blocked" and reason:
        _die_usage("--reason is only valid with --status blocked")

    deps = list(getattr(args, "depends_on", None) or [])
    if deps:
        if kind not in DEPENDS_ON_KEY_RE:
            _die_usage(f"depends_on lives on an epic or a story node, not a {kind} "
                       f"(status-files.md §11)")
        self_key = args.epic if kind == "epic" else args.story
        for k in deps:
            if not DEPENDS_ON_KEY_RE[kind].match(k):
                _die_usage(f"--depends-on {k!r} is not a {kind} key (expected "
                           f"{DEPENDS_ON_KEY_RE[kind].pattern}); nothing written")
            if k == self_key:
                _die_usage(f"--depends-on {k!r} is the node itself; nothing written")
    goal = getattr(args, "goal", None)
    superseded_by = getattr(args, "superseded_by", None)

    with _epic_write_lock(args, kind, require_exists=False):
        path, label = ensure_node_path(args.state_root, args, kind, args.status)
        if os.path.exists(path):
            sys.stdout.write(f"SKIP import-node {label} -- already exists\n")
            return 0

        node = {}
        if kind == "epic":
            node["key"] = SQ(args.epic)
            node["title"] = args.title or ""
            node["goal"] = ""
        elif kind == "sprint":
            node["key"] = SQ(args.sprint)
            node["epic"] = SQ(args.epic)
            node["title"] = args.title or ""
        else:
            epic_key, sprint_key, _ = parse_story_key(args.story)
            node["key"] = SQ(args.story)
            node["epic"] = SQ(epic_key)
            node["sprint"] = SQ(sprint_key)
            node["title"] = args.title or ""
            node["classification"] = args.classification or "unknown"

        node["status"] = args.status
        node["updated_at"] = _now_iso()
        if args.origin:
            node["origin"] = args.origin
            node["origin_note"] = args.origin_note or ""
        if kind == "story" and args.status == "blocked":
            node["blocked_reason"] = reason
            # completion_evidence.blocks_seen is a counter of OUR events, not the
            # source's history -- import-node predates our history for a migrated node,
            # so the counter starts at 0.
        if goal is not None:
            node["goal"] = goal
        if superseded_by is not None:
            node["superseded_by"] = superseded_by
        if deps:
            from ruamel.yaml.comments import CommentedSeq
            seq = CommentedSeq()
            for k in deps:
                if SQ(k) not in seq:
                    seq.append(SQ(k))
            node["depends_on"] = seq

        nodes.save_node(_yaml(), node, path, getattr(args, "flock", False))

        if not getattr(args, "no_events", False):
            payload = {
                "ts": _now_iso(), "event": "import", "from": None, "to": args.status,
                "session": getattr(args, "session_id", None),
            }
            payload.update(_event_keys(kind, args))
            append_event(args.state_root, payload)
            # A story imported at blocked gets a paired block_open, so the event log
            # carries the block the way a block recorded live would.
            if kind == "story" and args.status == "blocked":
                bp = {"ts": _now_iso(), "event": "block_open",
                      "story": args.story, "reason": reason,
                      "session": getattr(args, "session_id", None)}
                append_event(args.state_root, bp)

    sys.stdout.write(f"OK import-node {label} -> {args.status}\n")
    return 0


def _maybe_set(d, key: str, val, coerce):
    if val is not None:
        try:
            d[key] = coerce(val)
        except (ValueError, TypeError):
            d[key] = val


def cmd_set_estimate(args) -> int:
    # Rejected before anything else is touched: cost is derived from tokens x
    # rates (cmd_estimate_story / cmd_estimate_rollup), never accepted as
    # direct input. --cost, --cost-low, and --cost-high stay declared (with
    # help=argparse.SUPPRESS) purely so this is a clear usage error instead of
    # an argparse "unrecognized arguments" one.
    if getattr(args, "cost", None) is not None or getattr(args, "cost_low", None) is not None \
            or getattr(args, "cost_high", None) is not None:
        _die_usage("cost is derived from tokens x rates and cannot be set directly — "
                   "fix the token counts or modules.l3io-pm.token_rates instead")

    kind = _infer_kind(args)
    with _epic_write_lock(args, kind):
        return _set_estimate(args, kind)


def _set_estimate(args, kind) -> int:
    """cmd_set_estimate's body; the caller holds the epic lock for an epic node."""
    y, node, path, label = _load_checked(args.state_root, args, kind)

    from ruamel.yaml.comments import CommentedMap
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est
    apply_estimate(est, args, kind)
    nodes.save_node(y, node, path, getattr(args, "flock", False))
    sys.stdout.write(f"OK set-estimate {label}\n")
    return 0


def apply_estimate(est, args, kind) -> None:
    """Write set-estimate's flags into the mapping `est`. A story (and a v7 ticket entry)
    takes single values; a sprint or epic takes low/high ranges."""
    if kind == "story":
        # Stories: single values (not ranges)
        _maybe_set(est, "man_hours", args.man_hours, float)
        _maybe_set(est, "hitl_hours", args.hitl_hours, float)
        _maybe_set(est, "elapsed_hours", args.elapsed_hours, float)
        _maybe_set(est, "tokens_k", args.tokens_k_min, int)
    else:
        # Sprints and epics: low/high ranges
        _maybe_set(est, "man_hours_low", args.man_hours_low, float)
        _maybe_set(est, "man_hours_high", args.man_hours_high, float)
        _maybe_set(est, "hitl_hours_low", args.hitl_hours_low, float)
        _maybe_set(est, "hitl_hours_high", args.hitl_hours_high, float)
        _maybe_set(est, "elapsed_hours_low", args.elapsed_hours_low, float)
        _maybe_set(est, "elapsed_hours_high", args.elapsed_hours_high, float)
        _maybe_set(est, "tokens_k_min", args.tokens_k_min, int)
        _maybe_set(est, "tokens_k_max", args.tokens_k_max, int)

    # Calibration factors: applied to get from base values to the estimate
    _maybe_set(est, "fix_factor", getattr(args, "fix_factor", None), float)
    _maybe_set(est, "scope_ratio", getattr(args, "scope_ratio", None), float)

    # Confidence: explicit arg wins; else derive from completeness
    if args.confidence:
        est["confidence"] = args.confidence
    elif "confidence" not in est:
        # No cost/cost_low/cost_high in EITHER list: set-estimate never writes
        # any of them (cost is derived, not settable — see the rejection above),
        # so requiring one would make the estimate permanently "low" confidence.
        # The story list used to name `cost`, which set-estimate rejects at the
        # top of this function and can therefore never satisfy — so every
        # hand-written story estimate came out `low` no matter how complete it
        # was, and the derivation could only ever report one of its two values.
        range_keys = ["man_hours_low", "man_hours_high", "hitl_hours_low", "hitl_hours_high",
                      "elapsed_hours_low", "elapsed_hours_high",
                      "tokens_k_min", "tokens_k_max"]
        story_keys = ["man_hours", "hitl_hours", "elapsed_hours", "tokens_k"]
        check = story_keys if kind == "story" else range_keys
        est["confidence"] = "medium" if all(k in est for k in check) else "low"


def cmd_add_test_run(args) -> int:
    """Append one executed test command and derive tests_passing from the set.

    The boolean it replaces recorded that the agent was satisfied, not that
    anything passed: a story shipped `tests_passing: true` having broken a
    suite it never ran, and the break surfaced two stories later. A command
    and an exit code are falsifiable by anyone who re-runs them.

    DERIVATION RULE: `tests_passing` is `all(exit_code == 0)` over the **last
    run of each distinct command**, not over every run ever appended. Agents
    are told to record every command they ran, failures included, so the normal
    fix-then-rerun cycle -- `pytest` -> 1, fix, `pytest` -> 0 -- appends both.
    Folding history into the boolean would leave that story permanently
    `tests_passing: false` and punish exactly the behavior the record wants.
    The full history stays in `test_runs`: that is the evidence, and dropping
    the failed run to make the boolean come out right would destroy it. A
    command whose last run is non-zero still derives False, however many green
    runs preceded it.
    """
    if args.exit_code < 0:
        sys.stderr.write("ERROR --exit-code must be >= 0\n")
        return 2
    path = story_file(args.state_root, args.story)
    if path is None:
        _die_notfound(f"story {args.story}")
    y, node = load_node(path)
    if node is None:
        _die_notfound(f"story {args.story} — file {path} is empty")
    from ruamel.yaml.comments import CommentedMap
    ce = node.setdefault("completion_evidence", CommentedMap())
    runs = ce.setdefault("test_runs", [])
    entry = CommentedMap()
    entry["command"] = args.command
    entry["exit_code"] = int(args.exit_code)
    runs.append(entry)
    ce["tests_passing"] = tests_passing(runs)
    nodes.save_node(y, node, path, use_flock=True)
    sys.stdout.write(f"OK {args.story} test run recorded "
                     f"({args.command} -> {args.exit_code}); "
                     f"tests_passing={ce['tests_passing']}\n")
    return 0


def tests_passing(runs) -> bool:
    """cmd_add_test_run's DERIVATION RULE over a test_runs list."""
    # Last run wins per distinct command (see the docstring's DERIVATION RULE).
    # dict keeps insertion order and a re-run overwrites in place, so this is the
    # latest verdict for each command, in the order the commands first appeared.
    latest = {}
    for r in runs:
        if not isinstance(r, dict):
            # A hand-edited list can hold a scalar; an unreadable entry must never
            # derive a pass, and it has no command to key on -- give it its own slot.
            latest[("__malformed__", id(r))] = r
            continue
        latest[r.get("command")] = r
    return all(
        _exit_code_or_fail(r.get("exit_code") if isinstance(r, dict) else None) == 0
        for r in latest.values()
    )


def cmd_verify(args) -> int:
    kind = args.scope  # story | sprint | epic
    if kind == "epic":
        _y, node, _path, label = _load_checked(args.state_root, args, kind)
        failures: list[str] = []
        for sd in list_sprint_dirs(args.state_root, args.epic):
            skey = _sprint_key_from_dir(sd)
            sp = sprint_file(args.state_root, args.epic, skey)
            if sp is None:
                failures.append(f"{skey}: sprint.yaml missing")
            else:
                _, snode = load_node(sp)
                failures += [f"{skey}: {p}" for p in check_backrefs(snode, args.epic)]
            for stf in list_story_files(args.state_root, args.epic, skey):
                _, stnode = load_node(stf)
                if stnode is None:
                    failures.append(f"{os.path.basename(stf)}: empty")
                    continue
                failures += [f"{stnode.get('key', '?')}: {p}"
                             for p in check_backrefs(stnode, args.epic, skey)]
        if failures:
            for f in failures:
                sys.stderr.write(f"FAIL {f}\n")
            return 4
        sys.stdout.write(f"PASS epic {args.epic}\n")
        return 0

    _y, node, _path, label = _load_checked(args.state_root, args, kind)
    return verify_node(args, node, label, kind)


def verify_node(args, node, label, kind, judge_status=True) -> int:
    """verify's completeness verdict on one loaded node; prints PASS/FAIL, returns 0 or 4.
    A v7 ticket passes judge_status=False: its status is the plan's, written by v7."""
    problems: list[str] = []
    if judge_status and node.get("status") != "done":
        problems.append(f"status={node.get('status')!r} (expected done)")

    actual = node.get("actual") or {}
    required = list(METRIC_FIELDS)
    for m in required:
        if m not in actual:
            problems.append(f"actual.{m} absent")
            continue
        val = actual[m]
        # Numeric fields must be numeric; token/cost may be N/A only under non-claude runtime.
        if m in ("elapsed_hours", "man_hours", "hitl_hours"):
            if _is_na(val) or not _is_number(val):
                problems.append(f"actual.{m}={val!r} (must be numeric)")
        else:  # tokens_k, cost
            if _is_na(val):
                copilot_cost_na = (args.runtime == "copilot" and m == "cost")
                if not copilot_cost_na and (
                    args.require_tokens or args.runtime in ("claude", "codex", "copilot")
                ):
                    problems.append(
                        f"actual.{m}=N/A (forbidden under runtime={args.runtime} "
                        f"/ --require-tokens)")

    # tokens_k, once structured, is self-verifying: its total must equal the sum
    # of its four classes, and its cost must equal what those tokens price out to
    # under its own recorded model. A hand-edited cost is exactly the failure
    # this closes — without it, a bogus number survives in committed state
    # indefinitely because nothing ever recomputes it.
    tk = actual.get("tokens_k")
    if hasattr(tk, "get"):
        parts = sum(_num_or_none(tk.get(c)) or 0.0 for c in TOKEN_CLASSES)
        total = _num_or_none(tk.get("total"))
        # Unlike cost (below), total and parts are NOT on the same rounding grid:
        # `total` was rounded to 2dp once at write time (tokens_block), but
        # `parts` here is an unrounded re-sum of the class values. That write-time
        # rounding alone can separate a legitimate total from its exact sum by up
        # to half the last decimal place (0.005) with no error involved at all —
        # so tightening this to cost's 0.005 would risk failing correctly-rounded
        # data. 0.01 keeps a safe margin above that rounding noise while still
        # catching any genuine (typically integer-scale, since counts are whole
        # thousands of tokens) divergence.
        if total is None or abs(total - parts) > 0.01:
            problems.append(f"actual.tokens_k.total={total!r} != sum of classes ({parts})")
        model = actual.get("model")
        by_model = actual.get("by_model")
        if by_model is not None:
            # A mixed-model actual: tokens_k is the per-class sum of by_model, and cost
            # is each model's tokens at that model's own rates.
            if not hasattr(by_model, "items") or not by_model:
                problems.append(f"actual.by_model={by_model!r} is not a non-empty mapping")
                by_model = None
            else:
                for c in TOKEN_CLASSES:
                    s = sum(_num_or_none((v or {}).get(c)) or 0.0 for v in by_model.values())
                    have = _num_or_none(tk.get(c)) or 0.0
                    if abs(s - have) > 0.01 * len(by_model):
                        problems.append(f"actual.tokens_k.{c}={have!r} != sum of "
                                        f"by_model ({s})")
        if not model:
            problems.append("actual.model absent (cost cannot be verified)")
        elif by_model is not None or "by_model" not in actual:
            got = _num_or_none(actual.get("cost"))
            try:
                # The current card, or any card RATE_HISTORY records for the model: a
                # corrected rate must not fail actuals priced before the correction.
                ok, expect = cost_matches(got, tk, str(model), rate_overrides(args),
                                          dict(by_model) if by_model else None)
            except KeyError as e:
                # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
                # which would double-wrap a message that already reads as prose.
                problems.append(e.args[0])
            else:
                # Both sides are rounded to cents, so the smallest genuine divergence is
                # one cent; cost_matches' half-cent tolerance fires on it while still
                # absorbing float-summation noise.
                if not ok:
                    problems.append(f"actual.cost={got!r} != derived {expect} for "
                                    + ("each model in by_model" if by_model
                                       else f"model {model}"))
    elif "tokens_k" in actual and not _is_na(tk):
        # A bare scalar tokens_k has no class split, so the cost invariant above
        # cannot run at all — `tokens_k: 500` next to `cost: 9999.99` used to
        # return PASS. Design §4.3 says a hand-edited cost cannot survive verify;
        # keeping the pre-rework scalar shape was a one-line way around it. The
        # scalar form stays legitimate under runtime=other (set-estimate writes
        # it, and a runtime with no per-class visibility has nothing better), so
        # this fires only where exact per-class capture is required.
        if args.require_tokens or args.runtime in ("claude", "codex"):
            problems.append(
                f"actual.tokens_k={tk!r} is not the per-class mapping — cost cannot be "
                f"verified against it. Re-capture with set-actual "
                f"--tokens-input/--tokens-output/--tokens-cache-write/--tokens-cache-read "
                f"and --model (metrics-contract.md §3)")

    if kind == "story" and "completion_evidence" not in node:
        problems.append("completion_evidence absent")

    est_model = (node.get("estimate") or {}).get("model")
    act_model = actual.get("model")
    if est_model and act_model and est_model != act_model:
        sys.stdout.write(
            f"WARN {label}: estimate.model={est_model!r} ≠ actual.model={act_model!r}"
            f" — estimate cost denominated in {est_model} rates\n"
        )
    if problems:
        sys.stdout.write(f"FAIL {label}: " + "; ".join(problems) + "\n")
        return 4
    sys.stdout.write(f"PASS {label}\n")
    return 0


# --------------------------------------------------------------------------- #
# CLI registration -- this module's five verbs (design §3.2; the contract and the reason
# are in core's own register section). Order within this function is the order they appear
# in `pm-status.py --help`.
# --------------------------------------------------------------------------- #
def register(sub):
    imp = sub.add_parser("import-node",
                         help="create a state node from a migration record")
    imp.add_argument("--state-root", required=True)
    imp.add_argument("--epic")
    imp.add_argument("--sprint")
    imp.add_argument("--story")
    imp.add_argument("--status", required=True)
    imp.add_argument("--title", default="")
    imp.add_argument("--classification", default="unknown")
    imp.add_argument("--origin", choices=["inferred"],
                     help="mark the node as reconstructed rather than read")
    imp.add_argument("--origin-note", default="",
                     help="why the node was inferred; recorded beside --origin")
    imp.add_argument("--reason", default="",
                     help="required when importing a story at --status blocked; "
                          "recorded on the node as blocked_reason and in the paired "
                          "block_open event so a future exit-from-blocked can derive "
                          "duration. Rejected on any other kind or status.")
    imp.add_argument("--goal", default=None, help="the source's goal text, kept verbatim")
    imp.add_argument("--superseded-by", dest="superseded_by", default=None,
                     help="the key that superseded this node in the source")
    imp.add_argument("--depends-on", dest="depends_on", action="append", metavar="KEY",
                     help="repeatable: epic keys on an epic node, story keys on a story node")
    imp.add_argument("--no-events", action="store_true")
    imp.add_argument("--session-id")
    imp.set_defaults(func=cmd_import_node)

    v = sub.add_parser("verify", help="read-back gate; nonzero exit on any gap")
    v.add_argument("--state-root", help="path to {implementation_artifacts}/state")
    v.add_argument("--scope", required=True, choices=["story", "sprint", "epic"])
    node_args(v)
    plan_address_args(v)
    v.add_argument("--require-tokens", action="store_true")
    v.add_argument("--runtime", choices=["claude", "codex", "copilot", "other"], default="other")
    v.add_argument("--token-rates", dest="token_rates", default="",
                   help="JSON object of per-model rate overrides")
    v.set_defaults(func=cmd_verify)

    se = sub.add_parser("set-estimate", help="write estimate block to a story, sprint, or epic node")
    se.add_argument("--state-root", help="path to {implementation_artifacts}/state")
    node_args(se)
    entry_address_args(se)
    # Range fields (sprint/epic)
    se.add_argument("--man-hours-low", dest="man_hours_low")
    se.add_argument("--man-hours-high", dest="man_hours_high")
    se.add_argument("--hitl-hours-low", dest="hitl_hours_low")
    se.add_argument("--hitl-hours-high", dest="hitl_hours_high")
    se.add_argument("--elapsed-hours-low", "--time-hours-low", dest="elapsed_hours_low")
    se.add_argument("--elapsed-hours-high", "--time-hours-high", dest="elapsed_hours_high")
    se.add_argument("--tokens-k-min", dest="tokens_k_min")
    se.add_argument("--tokens-k-max", dest="tokens_k_max")
    # --cost / --cost-low / --cost-high are declared but SUPPRESSed from --help
    # and rejected in cmd_set_estimate: cost is derived from tokens x rates,
    # never accepted as direct input (see the rejection at the top of
    # cmd_set_estimate). Declaring them here — rather than leaving them
    # unrecognized — turns that rejection into a clear usage error instead of
    # argparse's generic "unrecognized arguments".
    se.add_argument("--cost-low", dest="cost_low", help=argparse.SUPPRESS)
    se.add_argument("--cost-high", dest="cost_high", help=argparse.SUPPRESS)
    # Single-value fields (story)
    se.add_argument("--man-hours", dest="man_hours")
    se.add_argument("--hitl-hours", dest="hitl_hours",
                    help="human attention actually spent supervising (hours)")
    se.add_argument("--elapsed-hours", "--time-hours", dest="elapsed_hours",
                    help="--time-hours is a deprecated alias")
    se.add_argument("--tokens-k", dest="tokens_k_min")  # alias to tokens_k_min for story use
    se.add_argument("--cost", dest="cost", help=argparse.SUPPRESS)
    se.add_argument("--confidence", choices=["low", "medium", "high"])
    se.add_argument("--fix-factor", dest="fix_factor",
                    help="fix multiplier applied; required for the scope/fix split")
    se.add_argument("--scope-ratio", dest="scope_ratio",
                    help="calibrated scope ratio applied (1.0 when cold-start)")
    se.add_argument("--flock", action="store_true", help="acquire exclusive flock before write")
    se.set_defaults(func=cmd_set_estimate)

    a = sub.add_parser("add-test-run", help="record one executed test command and its exit code")
    a.add_argument("--state-root", help="path to {implementation_artifacts}/state")
    a.add_argument("--story")
    plan_address_args(a)
    a.add_argument("--command", required=True, help="the test command actually executed")
    a.add_argument("--exit-code", dest="exit_code", type=int, required=True)
    a.set_defaults(func=cmd_add_test_run)

    nt = sub.add_parser("notice",
                        help="record a one-time-ever advisory notice; exit 1 if already shown")
    nt.add_argument("--state-root", required=True)
    nt.add_argument("--key", required=True)
    nt.set_defaults(func=cmd_notice)
