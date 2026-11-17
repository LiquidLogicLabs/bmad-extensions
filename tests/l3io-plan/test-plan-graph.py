#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["networkx>=3.6"]
# ///
"""plan-graph.py -- waves and lanes over a BMad v7 initiative, and the lane partition
`lanes` proposes."""
import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                      "skills", "l3io-pm", "l3io-plan", "scripts", "plan-graph.py")
spec = importlib.util.spec_from_file_location("plan_graph", SCRIPT)
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)


def plan(epics, active=(), archived=()):
    return {
        "planned": epics,
        "active": [{"key": k, "status": "in-progress", "depends_on": []} for k in active],
        "archived": [{"key": k, "status": "done", "depends_on": []} for k in archived],
    }


def epic(key, sprints, deps=(), lane=None):
    e = {"key": key, "status": "backlog", "depends_on": list(deps),
         "estimate": {}, "sprints": sprints}
    if lane is not None:
        e["lane"] = lane
    return e


class TestPartition(unittest.TestCase):
    """Proposing which lane owns which epic.

    The mode is CONFIGURED (lane_count from setup), never inferred: a project set up for three
    lanes that has not assigned any yet looks exactly like a single-developer project if you
    only scan epics.
    """

    def _two_clusters(self):
        def e(k, deps): return epic(k, [], deps)
        return plan([e("E001", []), e("E002", ["E001"]), e("E003", ["E001"]),
                     e("E004", ["E002", "E003"]), e("E005", []), e("E006", ["E005"]),
                     e("E007", ["E005"]), e("E008", ["E006", "E007"])])

    def test_two_natural_clusters_split_with_no_crossings(self):
        r = pg.partition(self._two_clusters(), 2)
        self.assertEqual(r["cross_lane_edges"], 0)
        self.assertEqual(sorted(len(L["epics"]) for L in r["lanes"]), [4, 4])

    def test_over_partitioning_reports_its_price(self):
        # THE POINT. Asking for more lanes than the work supports forces splits through real
        # dependencies, and a lead deciding whether to add a third person needs that BEFORE
        # assigning rather than after.
        r = pg.partition(self._two_clusters(), 3)
        self.assertEqual(r["cross_lane_edges"], 2)
        self.assertEqual(len(r["crossings"]), 2)

    def test_idle_phases_are_reported_because_they_are_a_different_objective(self):
        # Minimising crossings and keeping lanes busy are not the same thing: a partition
        # perfect by connectivity can leave a lane with nothing until another finishes.
        r = pg.partition(self._two_clusters(), 3)
        self.assertTrue(any(L["idle_phases"] for L in r["lanes"]),
                        "k=3 strands at least one lane for a phase; that must be visible")

    def test_every_epic_is_assigned_exactly_once(self):
        r = pg.partition(self._two_clusters(), 3)
        allocated = [e for L in r["lanes"] for e in L["epics"]]
        self.assertEqual(len(allocated), len(set(allocated)), "no epic in two lanes")
        self.assertEqual(len(allocated), 8, "no epic left unassigned")

    def test_more_lanes_than_epics_is_capped_and_says_so(self):
        r = pg.partition(plan([epic("E001", []), epic("E002", [])]), 5)
        self.assertEqual(r["lane_count"], 2)
        self.assertIn("cannot each own one", r["note"])

    def test_an_empty_plan_partitions_to_nothing(self):
        r = pg.partition(plan([]), 3)
        self.assertEqual(r["lanes"], [])

    def test_the_same_plan_partitions_the_same_way_twice(self):
        p = self._two_clusters()
        self.assertEqual(json.dumps(pg.partition(p, 2), sort_keys=True),
                         json.dumps(pg.partition(p, 2), sort_keys=True))



# -- BMad v7: waves and lanes over `tickets.py status` ----------------------------------
#
# The fixtures are `tickets.py status` output recorded at the upstream pin by
# fixtures/record-v7-status.sh, which also holds the tree they describe. In `shop`:
#
#   epic-platform  (in-progress)          epic-docs
#        |   \  declared + entry 2.1 -> 1.1, entry 3.1 -> 1.2
#   epic-cart    epic-search <- entry 3.1 -> 2.1 (undeclared)
#        |  gated: epic-checkout.md `after: [epic-cart]`
#   epic-checkout
FIXTURES = os.path.join(HERE, "fixtures")


def recorded(name):
    with open(os.path.join(FIXTURES, f"v7-status-{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def members(result):
    return [w["epics"] for w in result["waves"]]


def edge(result, member, prerequisite):
    for w in result["waves"]:
        for a in w["after"]:
            if a["for"] == member and a["epic"] == prerequisite:
                return a
    return None


def run_cli(argv, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = pg.main(argv)
    finally:
        sys.stdin = saved
    return code, out.getvalue(), err.getvalue()


class TestWaves(unittest.TestCase):

    def test_waves_from_status_json(self):
        r = pg.waves(recorded("shop"))
        self.assertEqual(r["scope"], "initiative")
        self.assertEqual(members(r), [["epic-platform", "epic-docs"], ["epic-cart"],
                                      ["epic-search", "epic-checkout"]])
        self.assertEqual([w["n"] for w in r["waves"]], [1, 2, 3])
        self.assertEqual([w["parallel"] for w in r["waves"]], [True, False, True])
        self.assertEqual(r["waves"][0]["after"], [])
        # The CLI reads the same JSON from a file or from stdin.
        path = os.path.join(FIXTURES, "v7-status-shop.json")
        code, out, err = run_cli(["waves", "--status-json", path])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), r)
        with open(path, encoding="utf-8") as fh:
            code, out, err = run_cli(["waves", "--status-json", "-"], fh.read())
        self.assertEqual((code, json.loads(out)), (0, r), err)

    def test_an_entry_after_into_another_epic_orders_the_waves(self):
        # epic-search declares only epic-platform, but its entry 3.1 waits on 2.1 in
        # epic-cart. tickets.py reports that as `undeclared_after`; the wave order must still
        # honour it, or search would be dispatched beside the cart it needs.
        r = pg.waves(recorded("shop"))
        a = edge(r, "epic-search", "epic-cart")
        self.assertIsNotNone(a, "the entry-level edge did not order the waves")
        self.assertEqual(a["via"], ["3.1"])
        self.assertEqual(a["needs"], "")

    def test_waves_parent_initiative_scope(self):
        r = pg.waves(recorded("portfolio"))
        self.assertEqual(r["scope"], "parent")
        self.assertEqual(members(r), [["shop"], ["ops", "growth"], ["insights"]])
        # A child initiative waits for its prerequisite to be done (tickets.py parent_view),
        # so every prerequisite of a later wave is a gate.
        self.assertEqual(r["gates"], ["shop", "ops", "growth"])

    def test_needs_reason_preserved(self):
        r = pg.waves(recorded("shop"))
        self.assertEqual(edge(r, "epic-cart", "epic-platform")["needs"],
                         "sessions and the product catalogue")
        self.assertEqual(edge(r, "epic-search", "epic-platform")["needs"],
                         "the catalogue index")
        self.assertEqual(edge(r, "epic-checkout", "epic-cart")["needs"],
                         "a basket to pay for")
        p = pg.waves(recorded("portfolio"))
        self.assertEqual(edge(p, "insights", "growth")["needs"],
                         "campaign results to report on")
        self.assertEqual(edge(p, "ops", "shop")["needs"], "the shop's order events to monitor")

    def test_gates_lists_epics_a_later_wave_waits_on(self):
        # Only an epic's closure (`done`) can gate: epic-checkout.md's `after: [epic-cart]`
        # waits for the cart epic to be done (tickets.py classify, :581-606). epic-platform is
        # waited on only through entries and a declaration, which a `built` ticket satisfies,
        # so it is not a gate.
        r = pg.waves(recorded("shop"))
        self.assertEqual(r["gates"], ["epic-cart"])
        self.assertTrue(edge(r, "epic-checkout", "epic-cart")["gate"])
        self.assertFalse(edge(r, "epic-cart", "epic-platform")["gate"])
        # A ticket's own `after` naming an epic waits for that epic's closure too.
        s = recorded("shop")
        next(t for t in s["tickets"] if t["epic"] == "epic-search")["after"].append("epic-docs")
        self.assertEqual(pg.waves(s)["gates"], ["epic-docs", "epic-cart"])

    def test_a_done_epic_leaves_the_waves_and_meets_its_edges(self):
        s = recorded("shop")
        next(e for e in s["epics"] if e["slug"] == "epic-platform")["status"] = "done"
        r = pg.waves(s)
        self.assertEqual(members(r), [["epic-cart", "epic-docs"],
                                      ["epic-search", "epic-checkout"]])
        self.assertEqual(r["done"], ["epic-platform"])
        self.assertIsNone(edge(r, "epic-cart", "epic-platform"))

    def test_an_epic_scope_status_is_refused(self):
        s = recorded("shop")
        del s["epics"]
        s["next_id"] = 2
        code, _o, err = run_cli(["waves", "--status-json", "-"], json.dumps(s))
        self.assertEqual(code, 2)
        self.assertIn("initiative", err)

    def test_a_cycle_emits_no_waves_and_says_why(self):
        s = recorded("shop")
        plat = next(e for e in s["epics"] if e["slug"] == "epic-platform")
        plat["after"] = [{"epic": "epic-checkout", "needs": "loop"}]
        r = pg.waves(s)
        self.assertEqual(r["waves"], [])
        self.assertIn("cycle", r["error"])

    def test_the_same_status_gives_the_same_waves_twice(self):
        s = recorded("shop")
        self.assertEqual(json.dumps(pg.waves(s), sort_keys=True),
                         json.dumps(pg.waves(s), sort_keys=True))


class TestV7Lanes(unittest.TestCase):

    def lanes_toml(self, text):
        d = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"plan-graph-{os.getpid()}")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"l3io-{self._testMethodName}.toml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.unlink, p)
        return p

    def test_lanes_view_from_the_container_sidecar(self):
        t = self.lanes_toml('[epic.epic-platform]\nlane = 1\n[epic.epic-cart]\nlane = 1\n'
                            '[epic.epic-checkout]\nlane = 1\n[epic.epic-search]\nlane = 2\n'
                            '[epic.epic-docs]\nlane = 2\n')
        r = pg.lanes(recorded("shop"), pg.read_lanes(t))
        by = {x["lane"]: x for x in r["lanes"]}
        self.assertEqual(by[1]["epics"], ["epic-platform", "epic-cart", "epic-checkout"])
        self.assertEqual(by[2]["epics"], ["epic-search", "epic-docs"])
        self.assertEqual(by[1]["waves"], [1, 2, 3])
        self.assertEqual(by[2]["waves"], [1, 3])
        self.assertEqual(by[2]["idle_waves"], [2])
        self.assertEqual(r["cross_lane_edges"], 2)
        self.assertEqual(sorted((c["from"], c["to"]) for c in r["crossings"]),
                         [("epic-search", "epic-cart"), ("epic-search", "epic-platform")])
        self.assertEqual(by[2]["waits_for"][0]["lane"], 1)
        self.assertEqual(r["unassigned"], [])

    def test_lanes_off_is_inert(self):
        missing = os.path.join(FIXTURES, "no-such-l3io.toml")
        r = pg.lanes(recorded("shop"), pg.read_lanes(missing))
        self.assertEqual(r["lanes"], [])
        self.assertNotIn("proposal", r)
        code, out, err = run_cli(["lanes", "--status-json",
                                  os.path.join(FIXTURES, "v7-status-shop.json"),
                                  "--lanes-toml", missing])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["lanes"], [])

    def test_a_lane_that_is_not_a_number_is_refused(self):
        t = self.lanes_toml('[epic.epic-cart]\nlane = "sarah"\n')
        code, _o, err = run_cli(["lanes", "--status-json",
                                 os.path.join(FIXTURES, "v7-status-shop.json"),
                                 "--lanes-toml", t])
        self.assertEqual(code, 2)
        self.assertIn("not a lane number", err)

    def test_a_proposal_when_lanes_are_on_and_none_is_assigned(self):
        missing = os.path.join(FIXTURES, "no-such-l3io.toml")
        code, out, err = run_cli(["lanes", "--status-json",
                                  os.path.join(FIXTURES, "v7-status-shop.json"),
                                  "--lanes-toml", missing, "--lanes", "2"])
        self.assertEqual(code, 0, err)
        prop = json.loads(out)["proposal"]
        self.assertEqual(prop["lane_count"], 2)
        allocated = sorted(e for x in prop["lanes"] for e in x["epics"])
        self.assertEqual(allocated, sorted(["epic-platform", "epic-cart", "epic-search",
                                            "epic-checkout", "epic-docs"]))
        self.assertIn("idle_waves", prop["lanes"][0])

    def test_lanes_refuse_a_parent_initiative(self):
        code, _o, err = run_cli(["lanes", "--status-json",
                                 os.path.join(FIXTURES, "v7-status-portfolio.json"),
                                 "--lanes-toml", os.path.join(FIXTURES, "none.toml")])
        self.assertEqual(code, 2)
        self.assertIn("epic", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
