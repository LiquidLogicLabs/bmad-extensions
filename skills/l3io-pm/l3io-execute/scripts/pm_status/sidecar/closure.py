"""pm_status.sidecar.closure -- `epic-close`: a v7 epic's actuals and closure calibration.

BMad v7's `bmad-retrospective` runs l3io's On Complete (wired by `/l3io-doctor wire`,
ADR-0020) after it saves the retrospective document (retro-document.md:41-45). That hook runs
this verb, which records the epic's side of the HARD RULE in the epic's `l3io.toml`:

  [[epic.closure_runs]]  one record per retrospective run: its window, runtime, tokens,
                         `man_hours`, `hitl_hours` and verdict
  [epic.closure]         the closure actual: every run summed, five metrics, `cost` derived
  [epic.actual]          every ticket sidecar under the epic's `tickets/` folder plus the
                         closure, summed -- a parent's actual is its children PLUS its own
                         closure-phase spend (metrics-contract.md §6), never the bare sum
  retro_verdict          the verdict, read from the document's frontmatter

THE WINDOW. The retrospective opens no bracket of its own, so its span inside the session is
found: from `--since` when given, else from the first turn of this Claude session that touched
the retrospective document (it is created as a skeleton when the run starts,
retro-document.md:7). It never reaches back past the end of this epic's previous closure run,
or past the last build of one of this epic's tickets closed in the same session, so a
retrospective re-run after a rejection and the fix builds between the two are never counted
twice. Under Codex, Copilot and `other` there is no transcript to search, so `--since` is
required there, and tokens follow metrics-contract.md §3 exactly as `build-close` takes them.

ONE CLOSURE SAMPLE PER EPIC, taken only when `[epic].estimate` exists and the verdict is
`accepted` or `accepted-with-open-items`: a rejected epic goes back to its tickets, and its
closure is not over. The ratio's numerator is the closure actual itself, measured directly
here, and its denominator is the closure overhead the epic estimate carried over the entries
it was rolled up from (`calibration.closure_ratio`). A metric whose closure actual is zero
or `N/A` is skipped.

IT WRITES NO STATUS. Neither does the retrospective (retro-document.md:39): whether the epic
is `done` is the owner's call after the verdict, made through v7's own store. No v7 file is
written. What this verb wrote is committed (`sidecar.commit`) as
`chore(l3io): epic close <slug>`; the retrospective document itself is v7's and the user's,
and is left exactly as the retrospective left it.

Exit 0; 2 on usage (a missing or unknown verdict, a document naming another epic, no window,
missing typed token counts) with nothing written; 3 when the document does not exist; 1 when
the commit failed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from .. import bracket, nodes, sidecar
from ..core import (
    CALIBRATED_METRIC_FIELDS,
    _actual_metric,
    _die_notfound,
    _die_usage,
    append_event,
    calibration_path,
    events_path,
)
from ..metrics import actuals_usage
from ..metrics.calibration import append_closure_ratios, closure_ratio
from ..metrics.rates import TOKEN_CLASSES
from . import commit, estimate
from . import verbs as sidecar_verbs

AGENT = "bmad-retrospective"
VERDICTS = ("accepted", "accepted-with-open-items", "rejected")
ACCEPTED = VERDICTS[:2]
SAMPLED_MARKER = "calibration_sampled_at"
RUNS_KEY = "closure_runs"


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _aware(raw: str, flag: str) -> datetime:
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        _die_usage(f"{flag} {raw!r} is not an ISO 8601 time")
    if when.tzinfo is None:
        _die_usage(f"{flag} {raw!r} has no UTC offset, so it cannot be ordered against the "
                   "transcript; add one (e.g. Z)")
    return when


def _verdict(retro: str, slug: str) -> str:
    """The verdict from the document's frontmatter (retro-document.md:9-21); exits 2 when it
    is missing or unknown, or when the document names another epic."""
    named = sidecar_verbs.plan_field(retro, "epic")
    if named and named != slug:
        _die_usage(f"{retro} is the retrospective of {named}, not of {slug}")
    verdict = sidecar_verbs.plan_field(retro, "verdict")
    if not verdict:
        _die_usage(f"{retro} carries no verdict in its frontmatter; bmad-retrospective "
                   "writes it there (retro-document.md:9-21)")
    if verdict not in VERDICTS:
        _die_usage(f"{retro}: verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
    return verdict


def _ticket_records(folder: str) -> list:
    """Every ticket sidecar under the epic's tickets folder as dispatch-shaped records:
    its `dispatch` list when it has one (raw tokens per model, as `build-close` wrote them),
    else its `[actual]` turned into one record."""
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(nodes.TICKET_SIDECAR_SUFFIX) or name == nodes.SIDECAR_NAME:
            continue
        side = sidecar.plain(sidecar.load(os.path.join(folder, name)))
        if side.get("dispatch"):
            out.extend(side["dispatch"])
        elif side.get("actual"):
            out.append(_record_of_actual(side["actual"]))
    return out


def _record_of_actual(a: dict) -> dict:
    rec: dict = {m: float(a.get(m) or 0) for m in ("elapsed_hours", "man_hours", "hitl_hours")}
    tk, split = a.get("tokens_k"), a.get("by_model")
    if tk == "N/A":
        rec["tokens"] = "N/A"
    elif isinstance(tk, dict) and isinstance(split, dict) and split:
        rec["runtime"] = "claude"
        rec["tokens"] = {m: {c: round(float(v.get(c) or 0) * 1000) for c in TOKEN_CLASSES}
                         for m, v in split.items()}
    elif isinstance(tk, dict) and a.get("model"):
        rec["runtime"] = "claude"
        rec["tokens"] = {a["model"]: {c: round(float(tk.get(c) or 0) * 1000)
                                      for c in TOKEN_CLASSES}}
    return rec


def _summed(records: list, token_rates: str, what: str, notes: list) -> dict:
    """The validated actual block of `records` summed, `cost` derived. One record with no
    token count makes the sum's tokens `N/A`: a partial sum would read as the whole."""
    unknown = sum(1 for r in records if not isinstance(r.get("tokens"), dict))
    if unknown:
        records = [{**r, "tokens": "N/A"} for r in records]
        notes.append(f"{what} tokens recorded as N/A: {unknown} of {len(records)} part(s) "
                     "carry no token count")
    ns, why = bracket.actual_args(bracket.sum_dispatches(records), token_rates)
    if why:
        notes.append(f"{what}: {why}")
    return actuals_usage.actual_values(ns)


def _floor(state_root: str, folder: str, project_root: str, sid: str, runs: list):
    """The latest moment this run's window may not reach behind: the end of this epic's last
    closure run, and the last build of one of its tickets closed in this session."""
    floors = [datetime.fromisoformat(r["closed_at"]) for r in runs if r.get("closed_at")]
    if sid:
        key = bracket.session_key(sid)
        prefix = sidecar_verbs.plan_rel(folder, project_root) + "/"
        for e in _events(state_root):
            if (e.get("event") == "dispatch_close" and e.get("bracket") == key
                    and e.get("agent") in bracket.AGENTS
                    and str(e.get("plan") or "").startswith(prefix)):
                when = _parse(e.get("ts"))
                if when is not None:
                    floors.append(when)
    return max(floors) if floors else None


def _events(state_root: str) -> list:
    out = []
    try:
        with open(events_path(state_root), encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        return []
    return out


def _parse(raw):
    try:
        when = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return when if when.tzinfo is not None else None


def _sample(state_root: str, doc, entries: dict, verdict: str, closure: dict) -> str:
    """One epic closure sample, or the reason there is none."""
    epic = doc["epic"]
    if verdict not in ACCEPTED:
        return (f"no closure sample: the verdict is {verdict}; the epic goes back to its "
                "tickets, and its closure is not over")
    if epic.get(SAMPLED_MARKER):
        return f"no closure sample: already recorded at {epic[SAMPLED_MARKER]}"
    pest = sidecar.plain(epic.get("estimate") or {})
    if not pest:
        return ("no closure sample: the epic has no [epic].estimate (estimate-entries rolls "
                "it up; an estimate made after the work is not a prediction)")
    children = [{"estimate": v} for v in
                (estimate._effective(doc, entries, i) for i in entries) if v]
    ratios, skipped = {}, {}
    for metric in CALIBRATED_METRIC_FIELDS:
        v = _actual_metric(closure, metric)
        if v is None:
            skipped[metric] = "the closure actual is N/A"
            continue
        if abs(v) <= 1e-9:
            skipped[metric] = ("zero closure actual: a 0.0 sample would train the closure "
                               "component to zero")
            continue
        ratio, why = closure_ratio("epic", metric, v, pest, children)
        if why:
            skipped[metric] = why
        else:
            ratios[metric] = ratio
    summary = "; ".join(f"{m}: {r}" for m, r in skipped.items())
    if not ratios:
        return f"no closure sample: {summary or 'no metrics available'}"
    append_closure_ratios(state_root, "epic", ratios)
    epic[SAMPLED_MARKER] = _iso(datetime.now(UTC))
    return f"closure epic +{len(ratios)} metrics" + (f" (skipped: {summary})" if summary else "")


def cmd_epic_close(args) -> int:
    typed = bracket.typed_tokens(args)
    for flag in ("man_hours", "hitl_hours"):
        if getattr(args, flag) < 0:
            _die_usage(f"--{flag.replace('_', '-')} must be >= 0")
    folder = nodes.v7_tickets_folder(args.epic_dir)
    toml = os.path.join(folder, "tickets.toml")
    if not os.path.isfile(toml):
        _die_usage(f"--epic-dir: {toml} does not exist; name a v7 epic folder")
    slug = estimate._epic_name(folder)
    retro = os.path.abspath(args.retro_file)
    if not os.path.isfile(retro):
        _die_notfound(f"retrospective {retro}")
    verdict = _verdict(retro, slug)
    state_root = nodes.project_state_root(args.project_root)
    path = nodes.entry_sidecar(folder)
    now = datetime.now(UTC)
    sid = args.session_id or os.environ.get(actuals_usage.CLAUDE_SESSION_ENV, "")
    paths = []
    if args.runtime == "claude" and sid:
        paths, sid = actuals_usage.resolve_session_transcript(sid)
    since = _aware(args.since, "--since") if args.since else None
    if since is None and paths:
        since = actuals_usage.first_tool_use_naming(paths, os.path.basename(retro))
    if since is None:
        _die_usage("cannot tell when this retrospective began: "
                   + ("no turn of this session's transcript touched "
                      f"{os.path.basename(retro)}" if args.runtime == "claude"
                      else f"runtime={args.runtime} has no transcript this verb can read")
                   + "; pass --since <ISO 8601 time, with offset, at which it began>")
    assert since is not None  # _die_usage exits; this tells the type checker so
    notes: list = []
    rel = sidecar_verbs.plan_rel(retro, args.project_root)
    entries = sidecar.read_entries(toml)
    tk = sidecar._tomlkit()
    with sidecar.locked(folder):
        doc = sidecar.load(path)
        epic = sidecar.table(doc, "epic")
        runs = sidecar.plain(epic.get(RUNS_KEY) or [])
        floor = _floor(state_root, folder, args.project_root, sid, runs)
        if floor is not None and floor > since:
            since = min(floor, now)
        record = {"agent": AGENT, "runtime": args.runtime, "opened_at": _iso(since),
                  "closed_at": _iso(now), "verdict": verdict, "retro": rel,
                  "elapsed_hours": round(max((now - since).total_seconds(), 0) / 3600.0, 4),
                  "man_hours": args.man_hours, "hitl_hours": args.hitl_hours}
        if typed is not None:
            record["tokens"] = typed
        elif args.runtime != "claude":
            record["tokens"] = "N/A"
        else:
            if paths:
                tokens, why = bracket.window_tokens({"claude_session": sid}, since, now,
                                                    args.model)
            else:
                tokens, why = {}, (f"no transcript for session {sid!r}" if sid else
                                   f"{actuals_usage.CLAUDE_SESSION_ENV} is not set")
            unpriced = bracket.priceable(tokens, args.token_rates)
            if unpriced:
                why = f"no rate card for {unpriced}; add it to modules.l3io-pm.token_rates"
            if why:
                notes.append(f"closure tokens not recorded: {why}")
            else:
                record["tokens"] = tokens
        if RUNS_KEY not in epic:
            epic[RUNS_KEY] = tk.aot()
        item = tk.table()
        for k, v in record.items():
            item[k] = v
        epic[RUNS_KEY].append(item)
        runs.append(record)
        closure = _summed(runs, args.token_rates, "closure", notes)
        actual = _summed(_ticket_records(folder) + runs, args.token_rates, "epic", notes)
        for key, values in (("closure", closure), ("actual", actual)):
            tbl = sidecar.table(doc, "epic", key)
            for k in list(tbl):
                del tbl[k]
            sidecar.put_metrics(tbl, values)
        epic["retro_verdict"] = verdict
        note = _sample(state_root, doc, entries, verdict, closure)
        sidecar.save(path, doc)
    if note:
        notes.append(note)
    common = {"agent": AGENT, "epic": slug, "session": args.session_id,
              "bracket": bracket.session_key(sid) if sid else None, "retro": rel}
    append_event(state_root, {"ts": _iso(since), "event": "dispatch_open", **common})
    append_event(state_root, {"ts": _iso(now), "event": "dispatch_close", "outcome": "closed",
                              "verdict": verdict, **common})
    append_event(state_root, {"ts": _iso(now), "event": "actual", "from": None, "to": None,
                              "session": args.session_id, "node": "epic", "key": slug})
    for n in notes:
        sys.stderr.write(f"pm-status.py: {n}\n")
    written = [path, events_path(state_root), os.path.join(state_root, ".gitignore"),
               calibration_path(state_root), calibration_path(state_root) + ".v1"]
    err = commit.commit_paths(args.project_root, written, f"chore(l3io): epic close {slug}")
    if err:
        sys.stderr.write(f"pm-status.py: recorded, but the commit failed, so the tree is "
                         f"dirty: {err}\n")
        return 1
    sys.stdout.write(f"OK epic-close {slug} verdict={verdict}\n")
    return 0


def register(sub):
    ec = sub.add_parser("epic-close", help="close a v7 epic after its retrospective: epic and "
                                           "closure actuals, verdict, closure sample, commit")
    ec.add_argument("--project-root", dest="project_root", required=True)
    ec.add_argument("--epic-dir", dest="epic_dir", required=True,
                    help="the v7 epic folder the retrospective reviewed, or its tickets/ folder")
    ec.add_argument("--retro-file", dest="retro_file", required=True,
                    help="the retrospective document, epic-<slug>-retrospective.md")
    ec.add_argument("--runtime", required=True, choices=bracket.RUNTIMES)
    ec.add_argument("--model", default="",
                    help="claude: the model for transcript turns that name none; codex: "
                         "the model that priced the typed counts")
    ec.add_argument("--man-hours", dest="man_hours", type=float, required=True,
                    help="counterfactual: what a person would have taken for this "
                         "retrospective by hand")
    ec.add_argument("--hitl-hours", dest="hitl_hours", type=float, required=True,
                    help="human attention this retrospective actually took (0 headless)")
    ec.add_argument("--since", default="",
                    help="ISO 8601 time, with offset, at which the retrospective began; "
                         "required unless runtime=claude finds it in the transcript")
    typed = ("thousands of tokens over this retrospective; codex and copilot only "
             "(metrics-contract.md §3)")
    ec.add_argument("--tokens-input", dest="tokens_input", type=float, default=None, help=typed)
    ec.add_argument("--tokens-output", dest="tokens_output", type=float, default=None,
                    help=typed)
    ec.add_argument("--tokens-cache-read", dest="tokens_cache_read", type=float, default=None,
                    help=typed + "; codex only")
    ec.add_argument("--token-rates", dest="token_rates", default="",
                    help="JSON object of per-model rate overrides")
    ec.add_argument("--session-id", dest="session_id", default=None,
                    help="the Claude session to read; defaults to this one")
    ec.set_defaults(func=cmd_epic_close)
