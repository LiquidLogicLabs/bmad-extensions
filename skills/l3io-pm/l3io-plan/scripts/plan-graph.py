#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["networkx>=3.6"]
# ///
"""plan-graph.py -- the graph questions over a BMad v7 initiative. Read-only.

Two modes read what v7's own `tickets.py status` prints for an initiative (or, for `waves`,
a parent initiative), from a file or `-` for stdin:

    tickets.py status <initiative> | plan-graph.py waves --status-json -
    tickets.py status <initiative> | plan-graph.py lanes --status-json - --lanes-toml T

Neither assembles a path of its own, which is why they can live here rather than inside
pm-status.py. `lanes` reads the one file it is handed: the initiative's `l3io.toml`.

WHY networkx AND NOT pm-status.py. networkx does the topological generations and the
modularity split `lanes` proposes. Its import alone costs ~616 ms, irrelevant once per plan
and ruinous in pm-status.py, which runs from every hook. So the dependency lives here and
pm-status.py takes no graph library at all. Do not "consolidate" them.
"""
import argparse
import json
import sys


def _digraph(edges: dict):
    """{node: [things it depends on]} -> DiGraph with dependency -> dependent edges.

    Edge direction is EXECUTION order, so a path reads in the order work happens and
    `dag_longest_path` returns it that way round. Dependencies on nodes outside the set
    (active, archived, dangling) are dropped here -- they are reported separately and are not
    this graph's to order.
    """
    import networkx as nx
    g = nx.DiGraph()
    g.add_nodes_from(edges)
    g.add_edges_from((d, n) for n, deps in edges.items() for d in deps if d in edges)
    return g


def partition(plan: dict, lane_count: int) -> dict:
    """Propose which lane owns which epic. Emits a proposal; assigns nothing.

    WHEN THIS IS ASKED FOR. `lane_count > 1` — a CONFIGURED answer from setup, never inferred
    from the tree. A project set up for three lanes that has not assigned any yet looks
    exactly like a single-developer project if you only scan epics, and they must not get the
    same answer.

    TWO OBJECTIVES, REPORTED SEPARATELY, because they are not the same thing. Minimising
    cross-lane edges keeps lanes independent; keeping every lane busy is about phase coverage.
    A partition that is perfect by connectivity can hand one lane only late-phase epics and
    leave it idle until another finishes, so both numbers are reported and neither is silently
    traded for the other.

    OVER-PARTITIONING HAS A PRICE, AND SAYING SO IS THE POINT. Asking for more lanes than the
    work supports forces splits through real dependencies. On an eight-epic fixture with two
    natural clusters, k=2 costs zero cross-lane edges and k=3 costs two. A lead deciding
    whether to put a third person on this needs that before assigning, not after.
    """
    import networkx as nx
    from networkx.algorithms import community as nxc

    epics = {e["key"]: e for e in plan.get("planned", [])}
    if not epics:
        return {"lanes": [], "note": "no planned epics to partition"}
    k = max(1, min(int(lane_count), len(epics)))

    edges = {k2: [d for d in (v.get("depends_on") or []) if d in epics]
             for k2, v in epics.items()}
    g = _digraph(edges)
    # UNDIRECTED for the split: an edge that crosses a lane boundary costs the same whichever
    # way it points -- one lane waits on the other either way.
    groups = ([set(epics)] if k == 1
              else [set(c) for c in nxc.greedy_modularity_communities(
                  g.to_undirected(), best_n=k, cutoff=k)])

    lane_of = {e: i + 1 for i, grp in enumerate(groups) for e in grp}
    crossing = [(u, v) for u, v in g.edges if lane_of[u] != lane_of[v]]

    gens = ([] if not nx.is_directed_acyclic_graph(g)
            else [set(x) for x in nx.topological_generations(g)])
    lanes = []
    for i, grp in enumerate(sorted(groups, key=lambda s: sorted(s)), start=1):
        idx = lane_of[next(iter(grp))]
        phases = [n for n, gen in enumerate(gens, 1) if gen & grp]
        lanes.append({
            "lane": idx,
            "epics": sorted(grp),
            "phases": phases,
            "idle_phases": [n for n in range(1, len(gens) + 1) if n not in phases],
        })
    out = {
        "lanes": sorted(lanes, key=lambda x: x["lane"]),
        "lane_count": k,
        "cross_lane_edges": len(crossing),
        "crossings": [{"from": u, "to": v} for u, v in sorted(crossing)],
    }
    if k < int(lane_count):
        out["note"] = (f"only {len(epics)} planned epic(s), so {lane_count} lanes cannot each "
                       f"own one; proposing {k}")
    return out


# --------------------------------------------------------------------------- #
# BMad v7: waves and lanes over `tickets.py status`
# --------------------------------------------------------------------------- #
#
# THREE KINDS OF EDGE, ONE SORT. An epic waits on another through its `[[epic]] after` in the
# initiative's `tickets.toml` (each with the `needs` reason v7 asks the author for), through an
# entry `after` that names a ticket or an epic elsewhere, and through its own epic file's
# `after` (`gated_by` in the status rows). All three order the waves. They differ in what
# releases them, and that is what `gates` reports: tickets.py meets a ticket's `after` naming
# another ticket once that ticket is in review (`built`), but a ticket's `after` naming an EPIC,
# and anything in an epic file's own `after`, waits for `done` (`classify`, tickets.py:581-606),
# which is written at the prerequisite epic's closure, on the user's word. A declaration alone releases nothing: it is pinned by
# entries (`unpinned_after` says when it is not), so it orders the waves and gates nothing.
#
# On a parent initiative every child's `after` waits for the prerequisite to be done
# (`parent_view`), so every prerequisite of a later wave is a gate.
#
# A `done` epic is finished work: it leaves the waves and its edges are met. A `dropped` one
# leaves the waves too, but an edge into it is kept and marked, because tickets.py never meets
# it -- the dependent waits until someone repoints its `after` (board.md, Close, drop, move).
_FINISHED = ("done", "dropped")


def _load_status(path: str):
    """`tickets.py status` JSON from a file, or stdin for `-`. (status, error)."""
    try:
        if path == "-":
            return json.load(sys.stdin), None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except OSError as e:
        return None, f"cannot read --status-json {path}: {e}"
    except json.JSONDecodeError as e:
        return None, (f"--status-json {path} is not valid JSON ({e}). Pass what "
                      f"`tickets.py status <initiative>` prints.")


def _status_scope(status) -> str:
    if isinstance(status, dict) and isinstance(status.get("initiatives"), list):
        return "parent"
    if isinstance(status, dict) and isinstance(status.get("epics"), list):
        return "initiative"
    return ""


def _target_epic(ref, by_id: dict, slugs: set):
    """The epic an entry's `after` ref points into, and whether it names the epic itself.

    tickets.py prints a ref as a sibling's id (same epic), `<epic id>.<entry id>` in another
    epic, an epic's slug, or `<slug>/<file>` for a ticket with no id (`ref`, :633-645)."""
    text = str(ref)
    if text in slugs:
        return text, True
    head, dot, _tail = text.partition(".")
    if dot and head in by_id:
        return by_id[head], False
    head, slash, _tail = text.partition("/")
    if slash and head in slugs:
        return head, False
    return None, False


def _initiative_edges(status: dict):
    """(order, state, edges): epic slugs in build order, each one's container status, and
    {(waiting, prerequisite): {"needs", "via", "gate"}}."""
    rows = [e for e in status["epics"] if isinstance(e, dict) and e.get("slug")]
    order = [str(e["slug"]) for e in rows]
    slugs = set(order)
    by_id = {str(e.get("id")): str(e["slug"]) for e in rows if e.get("id") is not None}
    state = {str(e["slug"]): str(e.get("status") or "") for e in rows}
    edges: dict = {}

    def add(waiting, prereq, needs="", via=None, gate=False):
        if waiting == prereq or waiting not in slugs or prereq not in slugs:
            return
        rec = edges.setdefault((waiting, prereq), {"needs": "", "via": [], "gate": False})
        if needs and not rec["needs"]:
            rec["needs"] = str(needs)
        if via is not None and via not in rec["via"]:
            rec["via"].append(via)
        rec["gate"] = rec["gate"] or gate

    for e in rows:
        for a in e.get("after") or []:
            if isinstance(a, dict):
                add(str(e["slug"]), str(a.get("epic")), a.get("needs", ""))
        # An epic file's `after` waits for `done` whether it names the epic or one of its
        # tickets (`gated_by` is checked against done keys only), and `done` is written at
        # the prerequisite epic's closure: either way, a gate.
        for key in e.get("gated_by") or []:
            target, _whole = _target_epic(key, by_id, slugs)
            add(str(e["slug"]), target, gate=True)
    for t in status.get("tickets") or []:
        if not isinstance(t, dict) or t.get("epic") not in slugs:
            continue
        for ref in t.get("after") or []:
            if isinstance(ref, int) and not isinstance(ref, bool):
                continue                     # a sibling in the same epic
            target, whole = _target_epic(ref, by_id, slugs)
            add(str(t["epic"]), target, via=str(t.get("ref") or t.get("id")), gate=whole)
    return order, state, edges


def _parent_edges(status: dict):
    rows = [r for r in status["initiatives"] if isinstance(r, dict) and r.get("slug")]
    order = [str(r["slug"]) for r in rows]
    state = {str(r["slug"]): str(r.get("status") or "") for r in rows}
    edges = {}
    for r in rows:
        for a in r.get("after") or []:
            if isinstance(a, dict) and str(a.get("initiative")) in state:
                edges[(str(r["slug"]), str(a["initiative"]))] = {
                    "needs": str(a.get("needs", "")), "via": [], "gate": True}
    return order, state, edges


def waves(status: dict) -> dict:
    """The order an initiative's epics (or a parent's initiatives) may run in, as waves.

    `waves[n].after` lists, for each member, what it waits on in an earlier wave, with the
    `needs` reason v7 recorded and `gate` when the wait is for that epic's closure; `via`
    names the entries whose `after` made an edge no declaration carries. `gates` is every
    remaining epic a later wave waits on for closure: what an unattended run pauses at.
    """
    import networkx as nx
    scope = _status_scope(status)
    order, state, edges = (_parent_edges(status) if scope == "parent"
                           else _initiative_edges(status))
    pos = {k: i for i, k in enumerate(order)}
    live = [k for k in order if state[k] not in _FINISHED]
    g = nx.DiGraph()
    g.add_nodes_from(live)
    g.add_edges_from((p, w) for (w, p) in edges if w in g and p in g)
    out = {"scope": scope, "waves": [], "gates": [],
           "done": [k for k in order if state[k] == "done"]}
    if not nx.is_directed_acyclic_graph(g):
        out["error"] = ("the dependency graph has a cycle, so it has no wave order; "
                        "`tickets.py status` names it")
        return out
    gate_set = set()
    for n, gen in enumerate(nx.topological_generations(g), start=1):
        group = sorted(gen, key=pos.get)
        after = []
        for w in group:
            for (waiting, prereq), rec in sorted(edges.items(),
                                                 key=lambda kv: pos[kv[0][1]]):
                if waiting != w or state[prereq] == "done":
                    continue
                item = {"epic": prereq, "for": w, "needs": rec["needs"], "gate": rec["gate"]}
                if rec["via"]:
                    item["via"] = list(rec["via"])
                if state[prereq] == "dropped":
                    item["dropped"] = True
                elif rec["gate"]:
                    gate_set.add(prereq)
                after.append(item)
        out["waves"].append({"n": n, "epics": group, "parallel": len(group) > 1,
                             "after": after})
    wave_of = {e: w["n"] for w in out["waves"] for e in w["epics"]}
    out["gates"] = sorted(gate_set, key=lambda k: (wave_of.get(k, 0), pos[k]))
    if scope == "initiative" and not order:
        out["note"] = "the initiative lists no epics, so there are no waves to order"
    return out


_LANE_MAX = 999


def read_lanes(path: str) -> dict:
    """{epic slug: lane} from an initiative's `l3io.toml` (`[epic.<slug>] lane`). A missing
    file is lanes off: {}. A lane that is not a whole number 1..999 raises ValueError, because
    a lane is a slot in a partition and never a person's name."""
    import tomllib
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return {}
    out = {}
    for slug, tbl in (data.get("epic") or {}).items():
        if not isinstance(tbl, dict) or "lane" not in tbl:
            continue
        lane = tbl["lane"]
        if isinstance(lane, bool) or not isinstance(lane, int) or not 1 <= lane <= _LANE_MAX:
            raise ValueError(f"{path}: [epic.{slug}] lane {lane!r} is not a lane number "
                             f"(1-{_LANE_MAX}); set it with pm_status set-lane")
        out[str(slug)] = lane
    return out


def lanes(status: dict, assigned: dict, lane_count: int = 0) -> dict:
    """Which epics each lane owns, which waves it works, and every wait that crosses lanes.

    A filter over the waves, never a second plan. With no epic assigned, lanes are off and
    the view is empty, unless `lane_count` asks for a proposal (`partition` over the same
    epic graph, its phases read as waves)."""
    w = waves(status)
    order, _state, edges = _initiative_edges(status)
    wave_of = {e: x["n"] for x in w["waves"] for e in x["epics"]}
    out = {"scope": "initiative", "lanes": [], "unassigned": [], "cross_lane_edges": 0,
           "crossings": []}
    if not assigned:
        out["note"] = "no epic carries a lane, so lanes are off for this initiative"
        if lane_count >= 2:
            plan = {"planned": [{"key": k, "depends_on": [p for (q, p) in edges if q == k]}
                                for k in order if k in wave_of]}
            prop = partition(plan, lane_count)
            for x in prop.get("lanes", []):
                x["epics"] = sorted(x["epics"], key=order.index)
                x["waves"] = x.pop("phases")
                x["idle_waves"] = x.pop("idle_phases")
            out["proposal"] = prop
        return out
    live = [k for k in order if k in wave_of]
    out["unassigned"] = [k for k in live if k not in assigned]
    n_waves = len(w["waves"])
    for lane in sorted({assigned[k] for k in live if k in assigned}):
        mine = [k for k in live if assigned.get(k) == lane]
        worked = sorted({wave_of[k] for k in mine})
        out["lanes"].append({"lane": lane, "epics": mine, "waves": worked,
                             "idle_waves": [n for n in range(1, n_waves + 1)
                                            if n not in worked],
                             "waits_for": [], "waited_on_by": []})
    by_lane = {x["lane"]: x for x in out["lanes"]}
    for (waiting, prereq), rec in sorted(edges.items(),
                                         key=lambda kv: (order.index(kv[0][0]),
                                                         order.index(kv[0][1]))):
        lw, lp = assigned.get(waiting), assigned.get(prereq)
        if waiting not in wave_of or prereq not in wave_of or not lw or not lp or lw == lp:
            continue
        out["crossings"].append({"from": waiting, "to": prereq, "needs": rec["needs"],
                                 "gate": rec["gate"]})
        by_lane[lw]["waits_for"].append({"epic": waiting, "on": prereq, "lane": lp,
                                         "needs": rec["needs"]})
        by_lane[lp]["waited_on_by"].append({"epic": prereq, "by": waiting, "lane": lw})
    out["cross_lane_edges"] = len(out["crossings"])
    return out


def _v7_main(a) -> int:
    status, err = _load_status(a.status_json)
    if err:
        sys.stderr.write(f"plan-graph.py: {err}\n")
        return 2
    scope = _status_scope(status)
    if not scope:
        sys.stderr.write("plan-graph.py: expected `tickets.py status` output for an "
                         "initiative or a parent initiative (an `epics` or `initiatives` "
                         "list); an epic folder's status has neither. Run it on the "
                         "initiative.\n")
        return 2
    if a.mode == "waves":
        return _emit(waves(status), a.pretty)
    if scope != "initiative":
        sys.stderr.write("plan-graph.py: lanes are on epics, and a parent initiative lists "
                         "initiatives; run lanes on one of its initiatives.\n")
        return 2
    if not a.lanes_toml:
        sys.stderr.write("plan-graph.py: lanes needs --lanes-toml, the initiative's "
                         "l3io.toml beside its tickets.toml.\n")
        return 2
    try:
        assigned = read_lanes(a.lanes_toml)
    except ValueError as e:
        sys.stderr.write(f"plan-graph.py: {e}\n")
        return 2
    return _emit(lanes(status, assigned, a.lanes), a.pretty)


def _emit(result: dict, pretty: bool) -> int:
    sep = None if pretty else (",", ":")
    sys.stdout.write(json.dumps(result, indent=2 if pretty else None, separators=sep) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plan-graph.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("waves", "lanes"),
                    help="waves: a v7 initiative's epics in the order they may run. lanes: "
                         "a v7 initiative's lanes over those waves.")
    ap.add_argument("--lanes", type=int, default=0,
                    help="lanes with none assigned: how many lanes to propose (from "
                         "modules.l3io-pm.lane_count)")
    ap.add_argument("--status-json", dest="status_json", default="",
                    help="waves and lanes: `tickets.py status` JSON, a file or - for stdin")
    ap.add_argument("--lanes-toml", dest="lanes_toml", default="",
                    help="lanes: the initiative's l3io.toml; absent means lanes are off")
    ap.add_argument("--pretty", action="store_true",
                    help="indent the JSON for reading by hand")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)

    if not a.status_json:
        sys.stderr.write(f"plan-graph.py: {a.mode} needs --status-json (a file, or - "
                         f"for stdin).\n")
        return 2
    return _v7_main(a)

if __name__ == "__main__":
    sys.exit(main())
