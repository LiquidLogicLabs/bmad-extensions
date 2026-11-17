"""pm_status.verbs -- `notice`, and the value logic `sidecar.verbs` writes with:
`apply_estimate`, `tests_passing` and `verify_node`.

The 3.x node verbs that lived here (`import-node`, and the node arms of `set-estimate`,
`add-test-run` and `verify`) retired with the 3.x tree in Phase 6; the v7 handlers are
`sidecar.verbs`. Nothing below this module imports it; only `__main__.py` (the parser) and
`sidecar.verbs` reach these functions.

CALL STYLE ACROSS MODULES. Every name the suite patches is reached through its MODULE OBJECT:
`core._load` / `core._atomic_dump` / `core.notices_lock`. A by-name
binding here would be a private copy the patch could never reach, and the test would pass
while guarding nothing. Names nothing patches are imported by name. None of the patch
targets is re-exported by this module or by `__main__.py`.
"""
from __future__ import annotations

import os
import sys

from .. import core
from ..core import (
    METRIC_FIELDS,
    _exit_code_or_fail,
    _is_na,
    _is_number,
    _num_or_none,
    _yaml,
    notices_path,
)
from ..metrics.rates import TOKEN_CLASSES, cost_matches, rate_overrides


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


def _maybe_set(d, key: str, val, coerce):
    if val is not None:
        try:
            d[key] = coerce(val)
        except (ValueError, TypeError):
            d[key] = val


def apply_estimate(est, args) -> None:
    """Write set-estimate's flags into the mapping `est`: a v7 ticket entry takes single
    values, one per metric."""
    _maybe_set(est, "man_hours", args.man_hours, float)
    _maybe_set(est, "hitl_hours", args.hitl_hours, float)
    _maybe_set(est, "elapsed_hours", args.elapsed_hours, float)
    _maybe_set(est, "tokens_k", args.tokens_k, int)

    # Calibration factors: applied to get from base values to the estimate
    _maybe_set(est, "fix_factor", getattr(args, "fix_factor", None), float)
    _maybe_set(est, "scope_ratio", getattr(args, "scope_ratio", None), float)

    # Confidence: explicit arg wins; else derive from completeness. `cost` is not in the
    # list: set-estimate never writes it (it is derived), so requiring it would make every
    # hand-written estimate come out `low`.
    if args.confidence:
        est["confidence"] = args.confidence
    elif "confidence" not in est:
        story_keys = ["man_hours", "hitl_hours", "elapsed_hours", "tokens_k"]
        est["confidence"] = "medium" if all(k in est for k in story_keys) else "low"


def tests_passing(runs) -> bool:
    """`completion_evidence.tests_passing` derived from a test_runs list.

    The boolean it replaces recorded that the agent was satisfied, not that anything
    passed: a story shipped `tests_passing: true` having broken a suite it never ran. A
    command and an exit code are falsifiable by anyone who re-runs them.

    DERIVATION RULE: `all(exit_code == 0)` over the **last run of each distinct command**,
    not over every run ever appended, so the normal fix-then-rerun cycle -- `pytest` -> 1,
    fix, `pytest` -> 0 -- closes green while the failed run stays in `test_runs` as
    evidence. A command whose last run is non-zero still derives False, however many green
    runs preceded it."""
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
# CLI registration -- `notice`. set-estimate, add-test-run and verify are registered by
# `sidecar.verbs`, which owns their handlers (design §3.2; the contract and the reason are
# in core's own register section).
# --------------------------------------------------------------------------- #
def register(sub):
    nt = sub.add_parser("notice",
                        help="record a one-time-ever advisory notice; exit 1 if already shown")
    nt.add_argument("--state-root", required=True)
    nt.add_argument("--key", required=True)
    nt.set_defaults(func=cmd_notice)
