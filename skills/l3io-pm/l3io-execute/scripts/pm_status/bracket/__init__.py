"""pm_status.bracket -- `build-open` and `build-close`: measurement around every v7 build.

BMad v7's `bmad-build` and `bmad-build-auto` run l3io's hooks (wired by `/l3io-doctor wire`,
ADR-0020): `activation_steps_prepend` runs `build-open`, `on_complete` runs `build-close`.
Between the two is one build of one ticket, and these verbs turn that span into the
ticket's actuals, a dispatch pair in `events.jsonl` and, when the ticket was estimated
beforehand, one calibration sample.

THE TREE STAYS CLEAN. `bmad-build-auto` refuses a dirty tree at its first step and checks
again after finalizing, so neither verb may leave a tracked or untracked file behind:

  build-open   writes ONLY `{state_root}/.inflight/<key>.json`. The spool directory ignores
               itself (a `.gitignore` of `*` inside it), so the open is invisible to git.
               It appends no event: an event is a tracked write.
  build-close  writes the events, the ticket sidecar and the calibration sample, then
               commits each path it wrote that lies inside the current worktree, as
               `chore(l3io): actuals <ticket>`, and nothing else the tree holds.

The bracket key is the session: `--session-id`, else the Claude session id in the
environment, else the agent plus the worktree, so the open and the close of one build agree
without either being told the other's name. A second open under the same key, or for the
same plan, retires the first as `abandoned` (an interactive `bmad-build` runs On Complete on
success only, so a build the user walked away from never closes); its events are written at
the next close, the first moment a tracked write is allowed.

Tokens follow metrics-contract.md §3 per runtime. Under Claude they are read from the
session's own transcript over the bracket's window (`actuals_usage.read_transcript_usage`)
and never typed. Codex and Copilot expose counts the agent can read but this verb cannot,
so the close takes them as flags -- input, output and cached input with `--model` under
Codex; input and output under Copilot, whose `cost` is `N/A` -- and refuses to record `N/A`
in their place, exactly as `set-actual` does, before anything is written. `other` records
`N/A`. `cost` is derived, as everywhere.

Each close appends one record to the sidecar's `dispatch` list, and `[actual]` is the sum
over that list, so a ticket built in two runs (blocked, then resumed) carries both. The
calibration sample is taken once per ticket, when its plan reads `built` or `done`: a
blocked run's partial spend is not a measurement of the ticket's size.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

from .. import nodes, sidecar
from ..core import (
    _atomic_text_write,
    _die_usage,
    _ensure_lock_ignore,
    append_event,
    calibration_path,
    events_path,
)
from ..metrics import actuals_usage
from ..metrics.calibration import record_story_sample
from ..metrics.rates import TOKEN_CLASSES, resolve_rates
from ..sidecar import verbs as sidecar_verbs

AGENTS = ("bmad-build", "bmad-build-auto")
RUNTIMES = ("claude", "codex", "copilot", "other")
ABANDONED_PREFIX = "abandoned-"
# A plan status at which the build delivered what the ticket asked for.
SAMPLED_STATUSES = ("built", "done")
SAMPLED_MARKER = "calibration_sampled_at"
EXIT_NO_OPEN = 4
_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(cwd: str, *argv) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *argv], capture_output=True, text=True,
                          check=False)


def _toplevel(path: str):
    """The worktree `path` is in, or None outside git."""
    try:
        r = _git(path, "rev-parse", "--show-toplevel")
    except OSError:
        return None
    return os.path.realpath(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _bracket_key(args) -> str:
    sid = args.session_id or os.environ.get(actuals_usage.CLAUDE_SESSION_ENV, "")
    if sid:
        return _SAFE_RE.sub("_", sid)
    where = _toplevel(args.project_root) or os.path.realpath(args.project_root)
    return f"{args.agent}-{hashlib.sha1(where.encode()).hexdigest()[:12]}"


def _spool(state_root: str) -> str:
    d = nodes.inflight_dir(state_root)
    os.makedirs(d, exist_ok=True)
    _ensure_lock_ignore(d, patterns=("*",))
    return d


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def _plan_rel(plan_file: str, project_root: str) -> str:
    return sidecar_verbs.plan_rel(os.path.abspath(plan_file), project_root) if plan_file else ""


# --------------------------------------------------------------------------- #
# build-open
# --------------------------------------------------------------------------- #
def cmd_build_open(args) -> int:
    state_root = nodes.project_state_root(args.project_root)
    spool = _spool(state_root)
    key = _bracket_key(args)
    now = datetime.now(UTC)
    plan = _plan_rel(args.plan_file, args.project_root)
    retired = []
    with sidecar.locked(spool):
        for name in sorted(os.listdir(spool)):
            if not name.endswith(".json") or name.startswith(ABANDONED_PREFIX):
                continue
            path = os.path.join(spool, name)
            rec = _read_json(path) or {}
            if name == f"{key}.json" or (plan and rec.get("plan") == plan):
                rec["abandoned_at"] = now.isoformat()
                _atomic_text_write(os.path.join(spool, f"{ABANDONED_PREFIX}{name[:-5]}-"
                                                f"{now.strftime('%Y%m%dT%H%M%S%f')}.json"),
                                   json.dumps(rec, sort_keys=True) + "\n")
                os.unlink(path)
                retired.append(rec.get("agent") or name[:-5])
        _atomic_text_write(os.path.join(spool, f"{key}.json"), json.dumps({
            "agent": args.agent, "key": key, "opened_at": now.isoformat(), "plan": plan,
            "claude_session": os.environ.get(actuals_usage.CLAUDE_SESSION_ENV, ""),
            "session": args.session_id,
        }, sort_keys=True) + "\n")
    for who in retired:
        sys.stderr.write(f"pm-status.py: an earlier {who} bracket never closed; it is "
                         "recorded as abandoned at the next build-close\n")
    sys.stdout.write(f"OK build-open {args.agent} (bracket {key})\n")
    return 0


# --------------------------------------------------------------------------- #
# build-close
# --------------------------------------------------------------------------- #
def _claim(spool: str, key: str) -> tuple:
    """(this bracket's open record or None, every abandoned record), each removed from the
    spool under its lock so two concurrent closes never both write one bracket's events."""
    opened, abandoned = None, []
    with sidecar.locked(spool):
        for name in sorted(os.listdir(spool)):
            path = os.path.join(spool, name)
            if name == f"{key}.json":
                opened = _read_json(path) or {}
            elif name.startswith(ABANDONED_PREFIX) and name.endswith(".json"):
                abandoned.append(_read_json(path) or {})
            else:
                continue
            os.unlink(path)
    return opened, abandoned


def _parse_test_runs(raw: list) -> list:
    runs = []
    for item in raw or []:
        cmd, sep, code = item.rpartition("=")
        if not sep or not cmd.strip():
            _die_usage(f"--test-run takes 'COMMAND=EXIT_CODE', got {item!r}")
        try:
            runs.append((cmd.strip(), int(code)))
        except ValueError:
            _die_usage(f"--test-run {item!r}: the exit code after the last '=' must be a "
                       "whole number")
    return runs


def _window_tokens(opened: dict, since: datetime, until: datetime, model: str) -> tuple:
    """({model: {class: tokens}} read from the Claude transcript over [since, until], note).
    Tokens a record names no model for are put on `model`, else on the model that served
    the most; an empty dict when the transcript cannot be read or names no model at all."""
    sid = opened.get("claude_session") or os.environ.get(actuals_usage.CLAUDE_SESSION_ENV, "")
    paths, sid = actuals_usage.resolve_session_transcript(sid)
    if not paths:
        return {}, (f"no transcript for Claude session {sid!r}" if sid else
                    f"{actuals_usage.CLAUDE_SESSION_ENV} is not set")
    res = actuals_usage.read_transcript_usage(paths, since=since, until=until)
    served = {m: t for m, t in res["by_model"].items() if sum(t.values())}
    unnamed = served.pop("", None)
    if unnamed:
        target = model or (max(sorted(served), key=lambda m: sum(served[m].values()))
                           if served else "")
        if not target:
            return {}, "the transcript names no model; pass --model"
        acc = served.setdefault(target, {c: 0 for c in TOKEN_CLASSES})
        for c in TOKEN_CLASSES:
            acc[c] += unnamed[c]
    return served, ""


def _sum_dispatches(dispatches: list) -> dict:
    """The ticket's actual: every closed bracket summed. Per-model tokens (Claude, Codex),
    Copilot's input/output totals, and whether any bracket recorded `N/A`."""
    out = {"elapsed_hours": 0.0, "man_hours": 0.0, "hitl_hours": 0.0}
    tokens: dict = {}
    copilot = {"input": 0, "output": 0}
    runtimes: set = set()
    na = False
    for d in dispatches:
        for m in out:
            out[m] += float(d.get(m) or 0)
        t = d.get("tokens")
        if isinstance(t, dict) and d.get("runtime") == "copilot":
            runtimes.add("copilot")
            for c in copilot:
                copilot[c] += t.get(c, 0)
        elif isinstance(t, dict):
            runtimes.add(d.get("runtime") or "claude")
            for model, counts in t.items():
                acc = tokens.setdefault(model, {c: 0 for c in TOKEN_CLASSES})
                for c in TOKEN_CLASSES:
                    acc[c] += counts.get(c, 0)
        elif t == "N/A":
            na = True
    return {**{m: round(v, 4) for m, v in out.items()}, "tokens": tokens,
            "copilot": copilot, "runtimes": runtimes, "na": na}


def _actual_args(total: dict, token_rates: str) -> tuple:
    """(set-actual's flags for a summed actual, a note or ""), so `actual_values` validates
    and prices it under the runtime that measured it, as it does a hand-typed one."""
    ns = argparse.Namespace(
        elapsed_hours=total["elapsed_hours"], man_hours=total["man_hours"],
        hitl_hours=total["hitl_hours"], tokens_na=False, model="", runtime="other",
        token_rates=token_rates, tokens_by_model=None,
        **{f"tokens_{c}": None for c in TOKEN_CLASSES})
    tokens, runtimes = total["tokens"], total["runtimes"]
    if "copilot" in runtimes and tokens:
        ns.tokens_na = True
        return ns, ("tokens recorded as N/A: this ticket's brackets mix Copilot, which has "
                    "no class split, with per-class runtimes, and one actual cannot hold both")
    if "copilot" in runtimes:
        ns.runtime = "copilot"
        ns.tokens_input = round(total["copilot"]["input"] / 1000.0, 3)
        ns.tokens_output = round(total["copilot"]["output"] / 1000.0, 3)
    elif len(tokens) == 1:
        (model, counts), = tokens.items()
        ns.runtime = "claude" if "claude" in runtimes else "codex"
        ns.model = model
        for c in TOKEN_CLASSES:
            setattr(ns, f"tokens_{c}", round(counts[c] / 1000.0, 3))
    elif tokens:
        ns.runtime = "claude" if "claude" in runtimes else "codex"
        ns.tokens_by_model = json.dumps({m: {c: round(v[c] / 1000.0, 3) for c in TOKEN_CLASSES}
                                         for m, v in sorted(tokens.items())})
    elif total["na"]:
        ns.tokens_na = True
    return ns, ""


# The counts each runtime exposes to the agent (metrics-contract.md §3), as build-close flags.
TYPED_TOKENS = {"codex": ("input", "output", "cache_read"), "copilot": ("input", "output")}


def _typed_tokens(args):
    """The bracket's tokens as typed for a runtime this verb cannot read: per-model counts
    under Codex, {input, output} under Copilot, None otherwise. Exits 2, before anything is
    written, on counts a runtime does not take or on missing ones."""
    given = {c: getattr(args, f"tokens_{c}", None) for c in ("input", "output", "cache_read")}
    given = {c: v for c, v in given.items() if v is not None}
    need = TYPED_TOKENS.get(args.runtime)
    if need is None:
        if given:
            _die_usage(f"runtime={args.runtime} takes no typed token counts: "
                       + ("they are read from this session's transcript"
                          if args.runtime == "claude" else "it records tokens as N/A"))
        return None
    flag = {c: "--tokens-" + c.replace("_", "-") for c in TYPED_TOKENS["codex"]}
    extra = [flag[c] for c in given if c not in need]
    if extra:
        _die_usage(f"runtime={args.runtime} does not expose {', '.join(extra)}")
    missing = [flag[c] for c in need if c not in given]
    if missing:
        _die_usage(f"runtime={args.runtime} forbids tokens=N/A: pass {', '.join(missing)} "
                   "(thousands of tokens over this build; see metrics-contract.md §3)")
    if any(v < 0 for v in given.values()):
        _die_usage("token counts must be >= 0")
    raw = {c: round(v * 1000) for c, v in given.items()}
    if args.runtime == "copilot":
        return raw
    if not args.model:
        _die_usage("runtime=codex needs --model: the same tokens price differently per model")
    unpriced = _priceable({args.model: None}, args.token_rates)
    if unpriced:
        _die_usage(f"no rate card for {unpriced}; add it to modules.l3io-pm.token_rates")
    return {args.model: {"input": raw["input"], "output": raw["output"], "cache_write": 0,
                         "cache_read": raw["cache_read"]}}


def _priceable(tokens: dict, token_rates: str) -> str:
    overrides = json.loads(token_rates) if token_rates else None
    for m in tokens:
        try:
            resolve_rates(m, overrides)
        except KeyError:
            return m
    return ""


def _sample(state_root: str, plan: str, ticket: str, sidecar_path: str) -> str:
    """One calibration sample for the ticket, or the reason there is none (on stderr)."""
    status = sidecar_verbs.plan_field(plan, "status") or ""
    if status not in SAMPLED_STATUSES:
        return f"no calibration sample: the plan reads {status or 'no status'!r}, not built"
    side = sidecar.plain(sidecar.load(sidecar_path))
    if side.get(SAMPLED_MARKER):
        return f"no calibration sample: already recorded at {side[SAMPLED_MARKER]}"
    folder = os.path.dirname(plan)
    ours = (sidecar.plain(sidecar.load(nodes.entry_sidecar(folder)))
            .get("entry", {}).get(ticket, {}))
    if not ours.get("estimate"):
        return (f"no calibration sample: entry {ticket} has no estimate in "
                f"{nodes.entry_sidecar(folder)} (an estimate made after the build is not "
                "a prediction)")
    eff = sidecar.effective_estimate(folder, ticket)
    node = {"key": ticket, "classification": eff.get("class") or "standard",
            "estimate": eff["values"], "actual": side.get("actual", {}),
            "completion_evidence": {"fix_iterations": side.get("fix_iterations")}}
    try:
        note = record_story_sample(state_root, node)
    except Exception as e:  # noqa: BLE001 -- derived data never fails the actuals write
        return f"no calibration sample: {e}"
    if note.startswith("no sample"):
        return f"no calibration sample: {note}"
    with sidecar.edit(sidecar_path) as doc:
        doc[SAMPLED_MARKER] = _iso(datetime.now(UTC))
    return ""


def _commit(project_root: str, paths: list, message: str) -> str:
    """Commit each of `paths` that lies inside the current worktree and is not ignored, and
    nothing else. Returns an error message, or "" (including when there was nothing)."""
    top = _toplevel(project_root)
    if top is None:
        return ""
    inside = []
    for p in dict.fromkeys(paths):
        real = os.path.realpath(p)
        if not os.path.exists(real) or not real.startswith(top + os.sep):
            continue
        if _git(top, "check-ignore", "-q", "--", real).returncode == 0:
            continue
        inside.append(os.path.relpath(real, top))
    if not inside:
        return ""
    r = _git(top, "add", "--", *inside)
    if r.returncode == 0 and _git(top, "status", "--porcelain", "--", *inside).stdout.strip():
        r = _git(top, "commit", "-q", "-m", message, "--", *inside)
    return "" if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip())


def cmd_build_close(args) -> int:
    runs = _parse_test_runs(args.test_run)
    typed = _typed_tokens(args)
    for flag in ("man_hours", "hitl_hours"):
        v = getattr(args, flag)
        if v < 0:
            _die_usage(f"--{flag.replace('_', '-')} must be >= 0")
    plan = sidecar_path = ticket = ""
    if args.plan_file:
        plan, sidecar_path = sidecar_verbs._plan_or_die(args.plan_file)
        ticket = sidecar_verbs._ticket_of(plan)
    state_root = nodes.project_state_root(args.project_root)
    spool = _spool(state_root)
    key = _bracket_key(args)
    now = datetime.now(UTC)
    opened, abandoned = _claim(spool, key)
    if opened is not None and not opened.get("opened_at"):
        opened = None                                   # an unreadable open is no open
    rel = _plan_rel(plan, args.project_root)
    base = {"agent": args.agent, "session": args.session_id, "bracket": key}

    for rec in abandoned:
        at = rec.get("opened_at") or rec.get("abandoned_at")
        common = {"agent": rec.get("agent"), "session": rec.get("session"),
                  "bracket": rec.get("key"), "plan": rec.get("plan") or None}
        if at:
            append_event(state_root, {"ts": _iso(datetime.fromisoformat(at)),
                                      "event": "dispatch_open", **common})
        append_event(state_root, {"ts": _iso(datetime.fromisoformat(
            rec.get("abandoned_at") or now.isoformat())), "event": "dispatch_close",
            "outcome": "abandoned", **common})

    ticket_fields = {"ticket": ticket, "plan": rel} if plan else {}
    if opened is None:
        append_event(state_root, {"ts": _iso(now), "event": "dispatch_close",
                                  "outcome": "unmatched", "unmatched": True, **base,
                                  **ticket_fields})
        sys.stderr.write(f"pm-status.py: no open {args.agent} bracket under {key}: the close is "
                         "recorded as unmatched, with no elapsed time and no tokens\n")
        since = None
    else:
        since = datetime.fromisoformat(opened["opened_at"])
        append_event(state_root, {"ts": _iso(since), "event": "dispatch_open", **base,
                                  **ticket_fields})
        append_event(state_root, {"ts": _iso(now), "event": "dispatch_close",
                                  "outcome": "closed", **base, **ticket_fields,
                                  "status": sidecar_verbs.plan_field(plan, "status")
                                  if plan else None})

    written = [events_path(state_root), os.path.join(state_root, ".gitignore")]
    notes = []
    if plan:
        record = {"agent": args.agent, "bracket": key, "runtime": args.runtime,
                  "closed_at": _iso(now), "outcome": "closed" if since else "unmatched",
                  "man_hours": args.man_hours, "hitl_hours": args.hitl_hours,
                  "elapsed_hours": round((now - since).total_seconds() / 3600.0, 4)
                  if since else 0.0}
        if since:
            record["opened_at"] = _iso(since)
        if typed is not None:
            record["tokens"] = typed
        elif args.runtime != "claude":
            record["tokens"] = "N/A"
        elif since:
            tokens, why = _window_tokens(opened, since, now, args.model)
            unpriced = _priceable(tokens, args.token_rates)
            if unpriced:
                why, tokens = (f"no rate card for {unpriced}; add it to "
                               "modules.l3io-pm.token_rates"), {}
            if tokens:
                record["tokens"] = tokens
            else:
                notes.append(f"tokens not recorded: {why}")
        fix = sidecar_verbs.plan_field(plan, "review_loop_iteration")
        tk = sidecar._tomlkit()
        with sidecar.edit(sidecar_path) as doc:
            if fix is not None and fix.isdigit():
                doc["fix_iterations"] = int(fix)
            if "dispatch" not in doc:
                doc["dispatch"] = tk.aot()
            item = tk.table()
            for k, v in record.items():
                item[k] = v
            doc["dispatch"].append(item)
            dispatches = sidecar.plain(doc["dispatch"])
        summed, why = _actual_args(_sum_dispatches(dispatches), args.token_rates)
        if why:
            notes.append(why)
        provided = actuals_usage.actual_values(summed)
        sidecar_verbs.write_ticket_actual(sidecar_path, provided)
        append_event(state_root, {"ts": _iso(now), "event": "actual", "from": None,
                                  "to": None, "session": args.session_id, "node": "ticket",
                                  "key": ticket, "plan": rel})
        for command, code in runs:
            sidecar_verbs.record_test_run(sidecar_path, command, code)
        if since:
            why = _sample(state_root, plan, ticket, sidecar_path)
            if why:
                notes.append(why)
        written += [sidecar_path, calibration_path(state_root),
                    calibration_path(state_root) + ".v1"]
    elif runs:
        notes.append("--test-run ignored: there is no plan file to record it on")

    for n in notes:
        sys.stderr.write(f"pm-status.py: {n}\n")
    subject = f"actuals {ticket}" if plan else f"build bracket {args.agent}"
    err = _commit(args.project_root, written, f"chore(l3io): {subject}")
    if err:
        sys.stderr.write(f"pm-status.py: recorded, but the commit failed, so the tree is "
                         f"dirty: {err}\n")
        return 1
    sys.stdout.write(f"OK build-close {args.agent}"
                     + (f" ticket {ticket}" if plan else " (no plan file: events only)")
                     + ("" if since else " [unmatched: no open bracket]") + "\n")
    return 0 if since else EXIT_NO_OPEN


def register(sub):
    bo = sub.add_parser("build-open", help="open the measurement bracket of one v7 build "
                                           "(writes only a gitignored spool file)")
    bo.add_argument("--project-root", dest="project_root", required=True)
    bo.add_argument("--agent", required=True, choices=AGENTS)
    bo.add_argument("--plan-file", dest="plan_file", default="",
                    help="the ticket's plan, when the build already knows it")
    bo.add_argument("--session-id", dest="session_id", default=None,
                    help="bracket key; defaults to the Claude session id, else the agent "
                         "and worktree")
    bo.set_defaults(func=cmd_build_open)

    bc = sub.add_parser("build-close", help="close a build's bracket: actuals, events, "
                                            "calibration sample, and a commit of them")
    bc.add_argument("--project-root", dest="project_root", required=True)
    bc.add_argument("--agent", required=True, choices=AGENTS)
    bc.add_argument("--plan-file", dest="plan_file", default="",
                    help="the ticket's plan; omit to close the bracket and record events only")
    bc.add_argument("--runtime", required=True, choices=RUNTIMES)
    bc.add_argument("--model", default="",
                    help="claude: the model for transcript turns that name none; codex: "
                         "the model that priced the typed counts")
    bc.add_argument("--man-hours", dest="man_hours", type=float, required=True,
                    help="counterfactual: what a developer would have taken by hand")
    bc.add_argument("--hitl-hours", dest="hitl_hours", type=float, required=True,
                    help="human attention the build actually took (0 under bmad-build-auto)")
    bc.add_argument("--test-run", dest="test_run", action="append", default=[],
                    metavar="CMD=EXIT", help="one executed verification command and its "
                                             "exit code; repeatable")
    for c in TYPED_TOKENS["codex"]:
        bc.add_argument("--tokens-" + c.replace("_", "-"), dest=f"tokens_{c}", type=float,
                        default=None, help="thousands of tokens over this build; codex and "
                                           "copilot only (metrics-contract.md §3)")
    bc.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    bc.add_argument("--session-id", dest="session_id", default=None,
                    help="bracket key, as given to build-open")
    bc.set_defaults(func=cmd_build_close)
