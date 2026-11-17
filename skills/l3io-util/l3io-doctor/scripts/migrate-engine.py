#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18", "tomlkit>=0.13"]
# ///
"""
migrate-engine.py -- l3io 3.x -> 4.x: carry l3io's data into its sidecars beside v7's tree.

    detect -> read -> resolve -> plan -> GATE -> write -> verify -> dispose

`l3io-pm`'s `migration-1.toml` runs this under `bmad migrate`, after method's own migration
has turned the v6 planning and implementation folders into a v7 initiative. Method's
migration owns the work-item tree -- `tickets.toml`, leaves, plans, status. This engine owns
only what l3io recorded about that work, and writes it where 4.x keeps it (status-files.md
§12): estimates and classes in the epic's `tickets/l3io.toml`, actuals and completion
evidence in `<plan-stem>.l3io.toml` beside each plan, lanes in the initiative's
`tickets/l3io.toml`, and calibration, events, the ADR register and the reorg log in
`{state_root}` = `<main checkout>/<core.output_folder>/l3io/`. It never writes a v7 file
(ADR-0015); a plan a datum needs and v7 lacks is named, with v7's own writer, and refused.

The gate sits BEFORE the write, and that position is the point: a parse that produced
nothing, a 3.x key that maps to no ticket or to two, a sidecar value v7-era work already
set, a project-wide file that already differs -- each refuses with nothing written. The
source is kept until the write verifies against the plan; only then, and only with
--dispose, is it renamed aside, never deleted.

Source layouts (LAYOUTS): the 3.x sharded tree under `{implementation_artifacts}/state/`,
and the three older l3io layouts -- a flat `sprint-status.yaml` with an `epics:` list (also
where method's migration archived it, `initiative-*/archive-v6/`), its three-file split,
and the per-epic `_bmad/state/`. A flat file in BMad's own schema is method's, not ours.

Usage:
  migrate-engine.py --project-root P [--artifacts DIR] [--map FILE] --detect
  migrate-engine.py --project-root P [--artifacts DIR] [--map FILE] --plan [--format json|text]
  migrate-engine.py --project-root P [--artifacts DIR] [--map FILE] --apply [--dispose]

--detect exits 0 when the migration applies, 1 when it does not; --plan exits 0; --apply
exits 0 on a verified write, 1 on a refusal or a failed verify, 2 on usage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

sys.dont_write_bytecode = True
_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load("state_record", "state-record.py")
_sharded = _load("read_sharded", "read-sharded.py")
_flat = _load("read_l3io_flat", "read-l3io-flat.py")
_per_epic = _load("read_per_epic", "read-per-epic.py")
_split = _load("read_split", "read-split.py")

# The l3io-util copy of pm_status, installed beside this file by `bmad setup l3io-util`.
sys.path.insert(0, _HERE)
from pm_status import nodes, sidecar
from pm_status.sidecar.estimate import CLASSES, fingerprint

LAYOUTS = ("sharded", "l3io-flat", "split", "per-epic")
PROJECT_FILES = ("pm-calibration.yaml", "adr-register.yaml", "reorg-log.yaml",
                 "events.jsonl", ".notices.yaml")
# A project-wide file that must arrive byte-identical, or the migration refuses: these are
# learned or allocated state, and two differing copies cannot be merged without guessing.
EXACT_FILES = ("pm-calibration.yaml", "adr-register.yaml", "reorg-log.yaml")
# BMad 6.12 shims v7 does not ship and does not retire, so `bmad setup` never offers to
# remove them (spec §13.5); a 3.x step file preferred each when installed (Review Focus 2).
V6_SHIMS = ("bmad-create-story", "bmad-dev-story", "bmad-review-adversarial-general")
SKILL_ROOTS = (".agents/skills", ".claude/skills")
# 3.x story status -> the v7 plan status `tickets.py mark` takes (tickets.py STATUSES :56).
PLAN_STATUS = {"backlog": "draft", "ready-for-dev": "ready-for-dev",
               "in-progress": "in-progress", "review": "in-review", "done": "done",
               "blocked": "blocked"}
PLAN_DATA = ("actual", "completion_evidence", "calibration_sampled_at")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
LEAF_TYPES = ("story", "spike", "bug")


# ------------------------------------------------------------------------- paths
def output_folder(root: str) -> str:
    value = nodes.resolve_config_key(root, "core.output_folder") or "{project-root}/_bmad-output"
    value = value.replace("{project-root}", root)
    return os.path.normpath(value if os.path.isabs(value) else os.path.join(root, value))


def artifacts_folder(root: str, out: str, given: str | None) -> str:
    if given:
        return os.path.abspath(given)
    for key in ("modules.l3io-pm.implementation_artifacts",
                "modules.bmm.implementation_artifacts"):
        value = nodes.resolve_config_key(root, key)
        if isinstance(value, str) and value.strip():
            value = value.replace("{project-root}", root).replace("{output_folder}", out)
            return os.path.normpath(value if os.path.isabs(value) else os.path.join(root, value))
    return os.path.join(out, "implementation-artifacts")


class Ctx:
    def __init__(self, root: str, artifacts: str | None, map_file: str | None):
        self.root = os.path.realpath(root)
        self.out = output_folder(self.root)
        self.art = artifacts_folder(self.root, self.out, artifacts)
        self.mapping = {}
        if map_file:
            with open(map_file, encoding="utf-8") as fh:
                self.mapping = {str(k): str(v) for k, v in json.load(fh).items()}
        self._state_root = None

    @property
    def state_root(self) -> str:
        if self._state_root is None:
            self._state_root = nodes.project_state_root(self.root)
        return self._state_root

    def flat_files(self) -> list:
        """Every l3io-schema flat status file: in the artifact folder, and where method's
        migration archived it."""
        from_flat = [Path(self.art) / "sprint-status.yaml"]
        from_flat += sorted(Path(self.out).glob("initiative-*/archive-v6/sprint-status.yaml"))
        return [p for p in from_flat if p.is_file() and _flat_schema(p) == "l3io"]


def _flat_schema(path: Path) -> str:
    from ruamel.yaml import YAML

    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- an unreadable file is simply not ours
        return "unreadable"
    if isinstance(data, dict) and isinstance(data.get("development_status"), dict):
        return "bmad"
    if isinstance(data, dict) and isinstance(data.get("epics"), list):
        return "l3io"
    return "unreadable"


# ------------------------------------------------------------------------ detect
def sources(ctx: Ctx) -> dict:
    """{layout: [source paths]} for every l3io layout present."""
    art = Path(ctx.art)
    found = {}
    if _sharded.is_sharded(art / "state"):
        found["sharded"] = [art / "state"]
    split = [art / n for n in _split.SPLIT_FILES[1:] if (art / n).is_file()]
    flats = ctx.flat_files()
    if split:
        found["split"] = [p for p in [art / "sprint-status.yaml", *split] if p.is_file()]
        flats = [p for p in flats if p.parent != art]
    if flats:
        found["l3io-flat"] = flats
    per_epic = Path(ctx.root) / "_bmad" / "state"
    if per_epic.is_dir() and any(per_epic.glob("*.yaml")):
        found["per-epic"] = [per_epic]
    return found


def initiatives(ctx: Ctx) -> list:
    return sorted(p.parent.parent for p in Path(ctx.out).glob("initiative-*/tickets/tickets.toml"))


def detect(ctx: Ctx) -> dict:
    found = sources(ctx)
    inis = initiatives(ctx)
    plan_md = Path(ctx.out) / "migration-v6-v7" / "migration-v6-v7.md"
    method_status = _frontmatter(plan_md).get("status") if plan_md.is_file() else None
    if not found:
        applies, reason = False, "no l3io 3.x source: nothing of l3io's to migrate"
    elif not inis:
        applies, reason = False, ("v7's initiative layout is absent: method's migration "
                                  "(`bmad migrate`, method migration-1) has not run yet")
    elif method_status not in (None, "done"):
        applies, reason = False, (f"method's migration is still in progress "
                                  f"(migration-v6-v7.md reads status: {method_status})")
    else:
        applies, reason = True, "l3io 3.x data beside a v7 initiative"
    return {"applies": applies, "reason": reason, "layouts": [k for k in LAYOUTS if k in found],
            "sources": {k: [str(p) for p in v] for k, v in found.items()},
            "initiatives": [str(p) for p in inis], "artifacts": ctx.art}


# -------------------------------------------------------------------------- read
def gather(ctx: Ctx) -> list:
    recs = []
    for layout, paths in sources(ctx).items():
        for p in paths:
            if layout == "sharded":
                recs += _sharded.read(p)
            elif layout == "per-epic":
                recs += _per_epic.read(p)
            elif layout == "split":
                recs += _flat.read(p)
            else:
                recs += _flat.read(p)
    return sr.dedupe(recs)


def project_files(ctx: Ctx) -> dict:
    """{name: source path} for each project-wide file, from the first home holding it."""
    homes = [Path(ctx.art) / "state", Path(ctx.art), Path(ctx.root) / "_bmad" / "state",
             Path(ctx.root) / "_bmad"]
    out = {}
    for name in PROJECT_FILES:
        for h in homes:
            if (h / name).is_file():
                out[name] = h / name
                break
    return out


# ---------------------------------------------------------------------- v7 tree
def _frontmatter(path: Path) -> dict:
    from ruamel.yaml import YAML

    try:
        m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8-sig"))
        data = YAML(typ="safe").load(m.group(1)) if m else None
    except Exception:  # noqa: BLE001 -- a malformed file joins nothing
        return {}
    return data if isinstance(data, dict) else {}


def _norm(title: str, epic: bool = False) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", str(title).casefold()).strip()
    return re.sub(r"^epic \d+ ", "", t) if epic else t


def _toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def v7_tree(ctx: Ctx) -> dict:
    """Every v7 epic and its tickets, read only: {"epics": [...], "tickets": [...]}."""
    epics, tickets = [], []
    for ini in initiatives(ctx):
        for e in _toml(ini / "tickets" / "tickets.toml").get("epic", []):
            slug = str(e.get("slug", ""))
            folder = ini / "tickets" / slug
            title = e.get("title") or _frontmatter(folder / f"{slug}.md").get("title") or slug
            epics.append({"slug": slug, "title": str(title), "initiative": ini, "folder": folder})
            tdir = folder / "tickets"
            leaves, plans = {}, {}
            for md in sorted(tdir.glob("*.md")) if tdir.is_dir() else []:
                fm = _frontmatter(md)
                if fm.get("type") in LEAF_TYPES and fm.get("id") is not None:
                    leaves[str(fm["id"])] = fm
                elif "ticket" in fm:
                    plans.setdefault(str(fm["ticket"]), []).append(md)
            for en in _toml(tdir / "tickets.toml").get("entry", []):
                tid = str(en.get("id"))
                prev = en.get("previous_keys") or []
                tickets.append({
                    "epic": slug, "id": tid, "folder": folder, "entry": en,
                    "title": str(leaves.get(tid, {}).get("title") or en.get("title", "")),
                    "keys": {str(k) for k in [en.get("v6_key"), *prev] if k},
                    "plans": plans.get(tid, []),
                })
    return {"epics": epics, "tickets": tickets}


# ------------------------------------------------------------------------ resolve
def _by_ref(tree: dict, ref: str):
    slug, _, tid = ref.partition("/")
    if tid:
        return [t for t in tree["tickets"] if t["epic"] == slug and t["id"] == tid]
    return [e for e in tree["epics"] if e["slug"] == slug]


def resolve(records: list, tree: dict, ctx: Ctx) -> tuple:
    """({3.x key: v7 ticket or epic}, [refusals], [notes]). Never guesses: a key with no
    candidate or more than one is a refusal when it carries data, a note when it does not."""
    resolved, refusals, notes = {}, [], []
    stories = [r for r in records if r["kind"] == "story"]
    epics = [r for r in records if r["kind"] == "epic"]

    def settle(rec, hits, how):
        key, data = rec["key"], _carries_data(rec)
        if len(hits) == 1:
            resolved[key] = hits[0]
            return
        what = "no v7 ticket" if rec["kind"] == "story" else "no v7 epic"
        if hits:
            names = ", ".join(_name(h) for h in hits)
            msg = f"{rec['kind']} {key} ({rec.get('title', '')!s}) matches more than one: {names}"
        else:
            msg = f"{rec['kind']} {key} ({rec.get('title', '')!s}) matches {what} ({how})"
        (refusals if data else notes).append(msg + ("" if data else " -- carries no l3io data"))

    for rec in stories:
        key = rec["key"]
        if key in ctx.mapping:
            settle(rec, _by_ref(tree, ctx.mapping[key]), "map file")
            continue
        keys = {key, *[str(k) for k in (rec.get("extras") or {}).get("previous_keys", [])]}
        hits = [t for t in tree["tickets"] if t["keys"] & keys]
        if not hits:
            hits = [t for t in tree["tickets"] if _norm(t["title"]) == _norm(rec.get("title", ""))]
        settle(rec, hits, "by v6_key, previous_keys or title")
    for rec in epics:
        key = rec["key"]
        if key in ctx.mapping:
            settle(rec, _by_ref(tree, ctx.mapping[key]), "map file")
            continue
        homes = {resolved[s["key"]]["epic"] for s in stories
                 if s["key"].startswith(key + "-") and s["key"] in resolved}
        hits = [e for e in tree["epics"] if e["slug"] in homes] if len(homes) == 1 else []
        if not hits and len(homes) > 1:
            hits = [e for e in tree["epics"] if e["slug"] in homes]
        if not hits:
            hits = [e for e in tree["epics"]
                    if _norm(e["title"], True) == _norm(rec.get("title", ""), True)]
        settle(rec, hits, "by its stories or title")
    return resolved, refusals, notes


def _name(hit) -> str:
    return f"{hit['epic']}/{hit['id']}" if "id" in hit else hit["slug"]


def _extras(rec) -> dict:
    return {k: v for k, v in (rec.get("extras") or {}).items() if k in sr.L3IO_EXTRAS}


def _carries_data(rec) -> bool:
    ex = _extras(rec)
    ex.pop("previous_keys", None)
    ex.pop("blocked_reason", None)
    return bool(ex) or bool(rec.get("classification")) or rec["kind"] == "sprint"


# ---------------------------------------------------------------------------- plan
def _clean(v):
    """Plain, TOML-safe values: None dropped (TOML has no null; absence is the same datum)."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items() if x is not None}
    if isinstance(v, list | tuple):
        return [_clean(x) for x in v if x is not None]
    return v


def build_plan(ctx: Ctx) -> dict:
    records = gather(ctx)
    tree = v7_tree(ctx)
    resolved, refusals, notes = resolve(records, tree, ctx)
    writes, needs_plan = {}, []
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def put(path, table, values):
        writes.setdefault(str(path), {}).setdefault(tuple(table), {}).update(_clean(values))

    for rec in records:
        problems = sr.validate(rec)
        if problems:
            refusals += [f"{rec['kind']} {rec['key']}: {p} ({rec['source']})" for p in problems]
            continue
        ex = _extras(rec)
        shed = sorted(k for k in (rec.get("extras") or {}) if k in sr.V7_EXTRAS)
        if shed:
            notes.append(f"{rec['kind']} {rec['key']}: {', '.join(shed)} not carried -- v7's "
                         "(method's migration writes after and goals from epics.md)")
        if rec["kind"] == "story" and rec["key"] in resolved:
            t = resolved[rec["key"]]
            tdir = t["folder"] / "tickets"
            entry = {"migrated_from": rec["key"]}
            cls = rec.get("classification")
            if cls in CLASSES:
                entry["class"] = cls
            elif cls:
                notes.append(f"story {rec['key']}: classification {cls!r} is not one of "
                             f"{', '.join(CLASSES)}; carried as migrated_class")
                entry["migrated_class"] = cls
            if ex.get("previous_keys"):
                entry["previous_keys"] = [str(k) for k in ex["previous_keys"]]
            if ex.get("estimate"):
                entry["estimate"] = ex["estimate"]
                entry["fingerprint"] = fingerprint(t["entry"])
                entry["estimated_at"] = now
            if len(entry) > 1:
                put(tdir / "l3io.toml", ["entry", t["id"]], entry)
            ticket = {k: ex[k] for k in PLAN_DATA if k in ex}
            ce = dict(ticket.get("completion_evidence") or {})
            if "fix_iterations" in ce:
                ticket["fix_iterations"] = ce.pop("fix_iterations")
                if ce:
                    ticket["completion_evidence"] = ce
                else:
                    ticket.pop("completion_evidence", None)
            plan_status = PLAN_STATUS.get(rec["status"], "draft")
            if len(t["plans"]) > 1:
                refusals.append(f"story {rec['key']}: {_name(t)} has more than one plan: "
                                + ", ".join(p.name for p in t["plans"]))
                continue
            if ticket and not t["plans"]:
                blocked = (f" --blocked {json.dumps(str(ex.get('blocked_reason', '')))}"
                           if plan_status == "blocked" else "")
                needs_plan.append(f"story {rec['key']} -> {_name(t)} has actuals or evidence "
                                  f"and v7 has no plan for it; v7 writes plans: run `uv run "
                                  f"{{project-root}}/_bmad/method/scripts/tickets.py --project-root "
                                  f"{{project-root}} mark {t['folder']} {t['id']} {plan_status}"
                                  f"{blocked}` (repo store), then plan again")
                continue
            if t["plans"]:
                pstatus = str(_frontmatter(t["plans"][0]).get("status", ""))
                if pstatus != plan_status:
                    notes.append(f"story {rec['key']}: 3.x status {rec['status']!r}, v7 plan "
                                 f"{pstatus!r} -- v7's stands (status is v7's)")
            if ticket:
                ticket["migrated_from"] = rec["key"]
                put(nodes.ticket_sidecar(str(t["plans"][0])), [], ticket)
        elif rec["kind"] == "epic" and rec["key"] in resolved:
            e = resolved[rec["key"]]
            data = {k: ex[k] for k in ("estimate", "actual", "orchestration",
                                       "calibration_sampled_at", "orchestration_sampled_at")
                    if k in ex}
            if data:
                put(e["folder"] / "tickets" / "l3io.toml", ["epic"],
                    {**data, "migrated_from": rec["key"]})
            if "lane" in ex:
                put(e["initiative"] / "tickets" / "l3io.toml", ["epic", e["slug"]],
                    {"lane": ex["lane"]})
        elif rec["kind"] == "sprint":
            ekey, _, skey = rec["key"].partition("-")
            e = resolved.get(ekey)
            data = {k: ex[k] for k in ("estimate", "actual", "orchestration") if k in ex}
            if e is None:
                if data:
                    refusals.append(f"sprint {rec['key']} carries l3io data and its epic "
                                    f"{ekey} maps to no v7 epic")
                continue
            # ADR-0016: v7 has no sprint. A 3.x sprint's own numbers (its closure overhead
            # is in no story) are kept in its epic's sidecar as history.
            if data:
                put(e["folder"] / "tickets" / "l3io.toml", ["sprint", skey],
                    {"title": rec.get("title", ""), "status": rec["status"], **data,
                     "migrated_from": rec["key"]})
    refusals += needs_plan
    copies = _plan_copies(ctx, refusals)
    for pw, tables in writes.items():
        _conflicts(pw, tables, refusals)
    shims = [str(Path(r) / n) for r in SKILL_ROOTS for n in V6_SHIMS
             if (Path(ctx.root) / r / n / "SKILL.md").is_file()]
    counts = {k: sum(1 for r in records if r["kind"] == k) for k in sr.KINDS}
    return {"layouts": detect(ctx)["layouts"], "counts": counts, "records": records,
            "writes": writes, "copies": copies, "refusals": refusals, "notes": notes,
            "leftover_shims": shims}


def _plan_copies(ctx: Ctx, refusals: list) -> list:
    out = []
    for name, src in project_files(ctx).items():
        dst = Path(ctx.state_root) / name
        mode = "copy"
        if dst.is_file():
            same = dst.read_bytes() == src.read_bytes()
            if same:
                mode = "same"
            elif name == "events.jsonl":
                mode = "union"
            elif name == ".notices.yaml":
                mode = "keep"
            else:
                refusals.append(f"{dst} exists and differs from {src}: {name} is learned or "
                                "allocated state and two copies are not merged; reconcile by "
                                "hand, then plan again")
                mode = "conflict"
        out.append({"name": name, "src": str(src), "dst": str(dst), "mode": mode})
    return out


def _conflicts(path: str, tables: dict, refusals: list) -> None:
    """A value already in the sidecar that differs from the one planned: v7-era work set it,
    and the migration never overwrites."""
    have = sidecar.plain(sidecar.load(path)) if os.path.isfile(path) else {}
    skip = {"fingerprint", "estimated_at"}
    for table, values in tables.items():
        cur = have
        for k in table:
            cur = cur.get(k, {}) if isinstance(cur, dict) else {}
        for k, v in values.items():
            if k in cur and k not in skip and _canon(cur[k]) != _canon(v):
                where = ".".join([*table, k]) if table else k
                refusals.append(f"{path}: {where} already holds {cur[k]!r}; the 3.x value "
                                f"{v!r} would overwrite it")


def _canon(v) -> str:
    return json.dumps(_clean(sidecar.plain(v)), sort_keys=True, default=str)


def render(plan: dict, ctx: Ctx) -> str:
    c = plan["counts"]
    layouts = ", ".join(plan["layouts"]) or "none"
    tables = sum(len(t) for t in plan["writes"].values())
    lines = [f"MIGRATION PLAN -- l3io 3.x -> 4.x; source layout(s): {layouts}", "=" * 64,
             f"  read     {c['epic']} epic(s), {c['sprint']} sprint(s), {c['story']} story(ies)",
             f"  write    {tables} table(s) in {len(plan['writes'])} sidecar(s)"]
    lines += [f"  {cp['mode']:<8} {cp['name']} -> {cp['dst']}" for cp in plan["copies"]]
    for title, key in (("REFUSALS (nothing will be written):", "refusals"),
                       ("NOTES:", "notes")):
        if plan[key]:
            lines += ["", title] + [f"  - {x}" for x in plan[key]]
    if plan["leftover_shims"]:
        lines += ["", ("LEFTOVER BMAD 6.12 SHIMS (v7 does not retire them; remove each from "
                       "version control when you choose -- the migration never deletes one):")]
        lines += [f"  - {s}" for s in plan["leftover_shims"]]
    return "\n".join(lines + ["=" * 64]) + "\n"


# ---------------------------------------------------------------------------- gate
def gate(plan: dict, ctx: Ctx):
    found = detect(ctx)
    if not found["applies"]:
        return f"BLOCKED: {found['reason']}. Nothing has been written."
    if not plan["records"] and not plan["copies"]:
        return ("BLOCKED: the source holds content but the plan is empty -- nothing would be "
                f"migrated. Sources: {found['sources']}. Nothing has been written.")
    if plan["refusals"]:
        listed = "\n".join(f"  - {r}" for r in plan["refusals"])
        return (f"BLOCKED: {len(plan['refusals'])} item(s) cannot be migrated without a "
                f"guess:\n{listed}\nA key that maps to no ticket or to two is settled with "
                "--map FILE (JSON: {\"E001-S01-003\": \"epic-<slug>/<id>\", \"E001\": "
                "\"epic-<slug>\"}). Nothing has been written and the source is untouched.")
    return None


# --------------------------------------------------------------------------- write
def _fill(doc, table: tuple, values: dict) -> None:
    tbl = sidecar.table(doc, *table) if table else doc
    for k, v in values.items():
        if isinstance(v, dict) and k in ("estimate", "actual", "orchestration"):
            sub = sidecar.table(doc, *table, k)
            for old in list(sub):
                del sub[old]
            sidecar.put_metrics(sub, v)
        elif k in ("fingerprint", "estimated_at") and k in tbl:
            continue
        else:
            tbl[k] = v


def write(plan: dict, ctx: Ctx) -> None:
    for path, tables in plan["writes"].items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with sidecar.edit(path) as doc:
            for table, values in tables.items():
                _fill(doc, table, values)
    os.makedirs(ctx.state_root, exist_ok=True)
    for cp in plan["copies"]:
        src, dst = Path(cp["src"]), Path(cp["dst"])
        if cp["mode"] == "copy":
            shutil.copy2(src, dst)
        elif cp["mode"] == "union":
            ours = src.read_text(encoding="utf-8").splitlines()
            theirs = dst.read_text(encoding="utf-8").splitlines()
            seen = set(ours)
            merged = ours + [ln for ln in theirs if ln not in seen]
            tmp = dst.with_suffix(".jsonl.migrating")
            tmp.write_text("\n".join(merged) + "\n", encoding="utf-8")
            os.replace(tmp, dst)


# -------------------------------------------------------------------------- verify
def verify(plan: dict, ctx: Ctx) -> list:
    """Read every target back and compare it with THE PLAN, datum by datum."""
    problems = []
    for path, tables in plan["writes"].items():
        if not os.path.isfile(path):
            problems.append(f"{path}: planned but absent")
            continue
        have = sidecar.plain(sidecar.load(path))
        for table, values in tables.items():
            cur = have
            for k in table:
                cur = cur.get(k, {}) if isinstance(cur, dict) else {}
            for k, v in values.items():
                if k in ("fingerprint", "estimated_at"):
                    if k not in cur:
                        problems.append(f"{path}: {'.'.join([*table, k])} absent")
                    continue
                if _canon(cur.get(k)) != _canon(v):
                    problems.append(f"{path}: {'.'.join([*table, k])} is {cur.get(k)!r}, "
                                    f"planned {v!r}")
    for cp in plan["copies"]:
        src, dst = Path(cp["src"]), Path(cp["dst"])
        if not dst.is_file():
            problems.append(f"{dst}: planned but absent")
        elif cp["mode"] in ("copy", "same") and dst.read_bytes() != src.read_bytes():
            problems.append(f"{dst}: differs from {src}")
        elif cp["mode"] == "union":
            have = set(dst.read_text(encoding="utf-8").splitlines())
            lost = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln not in have]
            if lost:
                problems.append(f"{dst}: {len(lost)} source event(s) missing")
    return problems


# ------------------------------------------------------------------------- dispose
def dispose(ctx: Ctx) -> list:
    """Rename every source aside as `<name>.legacy`. Never deletes. Method's own archive
    (`archive-v6/`) is left as method left it."""
    moved = []
    for paths in sources(ctx).values():
        for p in paths:
            if "archive-v6" in p.parts:
                continue
            dest = p.with_name(p.name + ".legacy")
            if dest.exists():
                continue
            p.rename(dest)
            moved.append(f"{p} -> {dest}")
    for src in project_files(ctx).values():
        if src.exists() and src.parent != Path(ctx.art) / "state":
            dest = src.with_name(src.name + ".legacy")
            if not dest.exists():
                src.rename(dest)
                moved.append(f"{src} -> {dest}")
    return moved


# ---------------------------------------------------------------------------- main
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="l3io 3.x -> 4.x migration engine")
    p.add_argument("--project-root", required=True)
    p.add_argument("--artifacts", help="the 3.x implementation_artifacts folder "
                                       "(default: resolved from config, else "
                                       "{output_folder}/implementation-artifacts)")
    p.add_argument("--map", dest="map_file", help="JSON {3.x key: 'epic-<slug>[/<id>]'}")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--detect", action="store_true")
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--format", choices=["json", "text"], default="text")
    p.add_argument("--dispose", action="store_true",
                   help="after a verified write, rename the source aside as .legacy")
    args = p.parse_args(argv)
    if args.dispose and not args.apply:
        p.error("--dispose needs --apply")
    ctx = Ctx(args.project_root, args.artifacts, args.map_file)

    if args.detect:
        found = detect(ctx)
        sys.stdout.write(json.dumps(found, indent=2) + "\n")
        return 0 if found["applies"] else 1

    found = detect(ctx)
    if args.apply and not found["applies"]:
        sys.stderr.write(f"BLOCKED: {found['reason']}. Nothing has been written.\n")
        return 1
    if args.plan:
        plan = build_plan(ctx)
        if args.format == "json":
            out = {k: v for k, v in plan.items() if k not in ("records", "writes")}
            out["writes"] = {path: {".".join(t) or "(top)": vals for t, vals in tables.items()}
                             for path, tables in plan["writes"].items()}
            sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(render(plan, ctx))
        return 0

    plan = build_plan(ctx)
    sys.stdout.write(render(plan, ctx))
    refusal = gate(plan, ctx)
    if refusal:
        sys.stderr.write(refusal + "\n")
        return 1
    write(plan, ctx)
    problems = verify(plan, ctx)
    if problems:
        sys.stderr.write("FAILED verification against the plan -- source untouched:\n")
        sys.stderr.writelines(f"  {x}\n" for x in problems)
        return 1
    sys.stdout.write(f"OK wrote {sum(len(t) for t in plan['writes'].values())} sidecar "
                     f"table(s) and {len(plan['copies'])} project file(s); verified against "
                     "the plan.\n")
    if args.dispose:
        for line in dispose(ctx):
            sys.stdout.write(f"  retired {line}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
