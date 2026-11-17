"""pm_status.metrics.estimates -- the estimate engine (references/metrics-contract.md).

`compute_story_estimate` (band midpoint x scope ratio x fix factor, per metric)
and `rollup_values` (sum of children + a calibrated closure band + a calibrated
orchestration band), plus the cold-start bands and the token-mix split the
roll-up prices through. `estimate-entries` (sidecar.estimate) is their one
caller: it is the v7 address of the retired 3.x `estimate-story` and
`estimate-rollup` verbs, writing one entry's estimate and the epic roll-up.

`compute_story_estimate` is reached as `metrics.estimates.<name>(...)` from
outside this file and is NOT re-exported anywhere, so a patch of it bites.
"""

from __future__ import annotations

from ..core import (
    PMError,
    _now_iso,
    _num_or_none,
)
from .calibration import (
    CLOSURE_RANGE_KEYS,
    COLD_START_FIX_FACTOR,
    COLD_START_SCOPE_RATIO,
    MIN_SAMPLES,
    ORCH_SPREAD,
    _child_estimate_value,
    active_closure_ratio,
    active_fix_factor,
    active_orchestration_fraction,
    active_scope_ratio,
    load_calibration,
)
from .rates import (
    COLD_START_TOKEN_MIX,
    FRESH_TOKEN_CLASSES,
    TOKEN_CLASSES,
    cost_from_tokens,
    fresh_share,
    tokens_block,
)

# The estimate-time model. Skills pass modules.l3io-pm.default_model through
# --model; this is the fallback for a direct CLI call, and it is a REAL model
# id so an unknown-model error can never be produced by the default itself.
DEFAULT_ESTIMATE_MODEL = "claude-opus-5"


def observed_mix(cal) -> dict:
    """Mean observed token mix, or the cold-start assumption below MIN_SAMPLES."""
    samples = ((cal or {}).get("token_mix") or {}).get("samples") or []
    # hasattr(s, "get") first: a stray non-mapping entry (hand-edit, bad
    # merge, partial corruption of the committed, shared calibration file)
    # must fall back to cold-start like every other malformed shape here —
    # not crash `estimate-entries` for the whole project. Same guard as the
    # tokens_k mapping check in record_story_sample above.
    usable = [s for s in samples if hasattr(s, "get") and
              all(_num_or_none(s.get(c)) is not None for c in TOKEN_CLASSES)]
    if len(usable) < MIN_SAMPLES:
        return dict(COLD_START_TOKEN_MIX)
    mix = {c: sum(float(s[c]) for s in usable) / len(usable) for c in TOKEN_CLASSES}
    total = sum(mix.values())
    if total <= 0:
        return dict(COLD_START_TOKEN_MIX)
    return {c: v / total for c, v in mix.items()}   # renormalize; means need not sum to 1


def split_tokens(total: float, mix: dict) -> dict:
    """Split a banded total across classes, preserving the total exactly.

    Rounding drift goes to the largest class rather than being dropped, so
    `sum(classes) == total` is an invariant a test can assert and a reader can
    trust.
    """
    out = {c: round(total * float(mix.get(c, 0.0))) for c in TOKEN_CLASSES}
    drift = round(total) - sum(out.values())
    if drift:
        biggest = max(TOKEN_CLASSES, key=lambda c: out[c])
        out[biggest] += drift
    return out


# Cold-start base bands (low, high) per classification; the single source. No `cost` row: cost is derived from the
# tokens_k total and priced per model, see cmd_estimate_story -- a separate cost band drifted
# from the token estimate it should follow. `tokens_k` is a FRESH-token band (input + output
# + cache_write); see FRESH_TOKEN_CLASSES. Do not raise it to meet a cache-inclusive actual:
# cache_read is projected from the observed mix and belongs to orchestration, not scope.
BASE_BANDS = {
    "simple":   {"man_hours": (2, 4),  "hitl_hours": (0.1, 0.3), "elapsed_hours": (0.5, 1.5),
                 "tokens_k": (20, 50)},
    "standard": {"man_hours": (4, 8),  "hitl_hours": (0.2, 0.5), "elapsed_hours": (1, 3),
                 "tokens_k": (40, 100)},
    "complex":  {"man_hours": (8, 16), "hitl_hours": (0.3, 1.0), "elapsed_hours": (2, 6),
                 "tokens_k": (80, 200)},
}


def compute_story_estimate(state_root, node, cls, model, overrides, confidence=None):
    """Compute and write a story's estimate block: band midpoint x scope ratio x fix
    factor, per metric. Classification is the model's judgment; everything after it
    is arithmetic, done here so it's error-checked and reproducible.

    Each metric queries its own calibrated scope ratio — man_hours and tokens_k may
    be calibrated independently once each has >=3 samples, so ratios are looked up
    per metric, never hoisted out and reused across all four in BASE_BANDS.

    All four applied ratios are recorded as `estimate.scope_ratios`, per metric.
    This is load-bearing, not provenance: `derive_story_sample` divides the applied
    ratio back out to measure the next sample against the base band, and one
    scalar cannot reconstruct four metrics' corrections.

    `cost` is not one of the banded/calibrated metrics: it is priced from the
    banded tokens_k TOTAL, split across classes by `observed_mix` (or the
    cold-start assumption below three samples), then run through
    `cost_from_tokens` for `--model` (falling back to DEFAULT_ESTIMATE_MODEL).
    This keeps cost arithmetically bound to the token estimate it prices —
    the two can no longer drift apart the way a separately-banded,
    separately-calibrated cost could.

    Never saves and never exits: `estimate-entries` (sidecar.estimate) writes the
    computed block into the entry's sidecar.
    """
    _, cal = load_calibration(state_root)
    fix = active_fix_factor(cal, cls)
    fix = COLD_START_FIX_FACTOR if fix is None else fix

    from ruamel.yaml.comments import CommentedMap

    # Every value below is computed into locals first, including the token
    # split and the priced cost -- node/est is not touched until all of that
    # (in particular cost_from_tokens, the one call that can raise) has
    # succeeded. An in-process caller must be able to catch PMError and keep
    # going without finding a half-written estimate block behind it.
    applied = CommentedMap()
    raw = {}
    for metric, (lo, hi) in BASE_BANDS[cls].items():
        mid = (lo + hi) / 2.0
        ratio = active_scope_ratio(cal, cls, metric)
        if ratio is None:
            ratio = COLD_START_SCOPE_RATIO
        applied[metric] = round(ratio, 4)
        value = mid * ratio * fix
        raw[metric] = round(value) if metric == "tokens_k" else round(value, 2)

    # The band produces FRESH tokens, matching what the scope ratio now measures.
    # cache_read is then projected from the observed mix rather than banded: it
    # tracks corpus x agent count, so a story-size band cannot predict it, but the
    # ratio it bears to fresh tokens is exactly what token_mix samples record.
    fresh_total = raw["tokens_k"]
    mix = observed_mix(cal)
    fshare = fresh_share(mix)
    counts = split_tokens(fresh_total, {c: mix.get(c, 0.0) / fshare for c in FRESH_TOKEN_CLASSES})
    counts["cache_read"] = round(fresh_total * (mix.get("cache_read", 0.0) / fshare))
    tokens_est = tokens_block(counts)
    try:
        cost = cost_from_tokens(counts, model, overrides)
    except KeyError as e:
        # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
        # which would double-wrap a message that already reads as prose.
        raise PMError(2, e.args[0])

    # Everything above is a local computation; only now, with cost already
    # priced successfully, do we touch node. Get the existing estimate block
    # or create one -- in place, so any other keys and ruamel comments on an
    # existing block survive -- then write the computed values into it in the
    # same key order it has always had.
    est = node.get("estimate")
    if est is None:
        est = CommentedMap()
        node["estimate"] = est
    for metric, value in raw.items():
        est[metric] = value
    est.pop("tokens_k")
    est["tokens_k"] = tokens_est
    est["cost"] = cost
    est["model"] = model

    est["fix_factor"] = round(fix, 4)
    est["scope_ratios"] = applied
    est.pop("scope_ratio", None)   # the superseded single-value form
    if confidence:
        est["confidence"] = confidence
    node["classification"] = cls
    node["updated_at"] = _now_iso()
    return applied


# Closure overhead as a fraction of children, used when no calibrated ratio is
# active yet. Deliberately a band, not a point: closure cost is variable.
COLD_START_CLOSURE_BAND = (0.10, 0.25)
NO_CHILD_ESTIMATES = "has no child estimates to roll up"


def rollup_values(cal, level, children, model, overrides):
    """The roll-up arithmetic over already-loaded children: (estimate, children counted,
    metrics whose orchestration band is not yet active). `level` names the calibration
    components applied (`epic`); each child is a mapping holding `estimate`.
    The v7 epic roll-up (`sidecar.estimate`, run by `estimate-entries`) passes the epic's
    entries, with no sprint between them (ADR-0016).

    Output is always range form: sum(children) + a closure band + an orchestration band.
    The closure band scales by the calibrated closure ratio once active (>=3 samples), else
    the cold-start band applies (ratio 1.0). The orchestration band scales by the
    calibrated orchestration FRACTION once active, else it contributes nothing -- there is
    no cold-start prior for orchestration (see ORCH_SPREAD). The applied ratios are recorded
    as `closure_ratios` and `orchestration_ratios`, per metric. `cost` is not banded: it is
    priced from the rolled-up tokens_k range, split across classes by `observed_mix`.

    Raises PMError(2) when no child carries an estimate, or for an unpriceable model."""
    from ruamel.yaml.comments import CommentedMap
    est = CommentedMap()
    applied = CommentedMap()
    orch_applied = CommentedMap()
    counted = 0
    for metric, (lo_key, hi_key) in CLOSURE_RANGE_KEYS.items():
        total = 0.0
        seen = 0
        for cn in children:
            v = _child_estimate_value(cn, metric)
            if v is not None:
                total += v
                seen += 1
        if seen == 0:
            continue
        counted = max(counted, seen)
        ratio = active_closure_ratio(cal, level, metric)
        if ratio is None:
            ratio = 1.0            # cold start: the closure band applies unscaled
        applied[metric] = round(ratio, 4)

        frac = active_orchestration_fraction(cal, level, metric)
        orch_applied[metric] = round(frac, 4) if frac is not None else 0
        of = frac or 0.0
        lo = total * (1 + ratio * COLD_START_CLOSURE_BAND[0] + of * ORCH_SPREAD[0])
        hi = total * (1 + ratio * COLD_START_CLOSURE_BAND[1] + of * ORCH_SPREAD[1])
        if metric == "tokens_k":
            est[lo_key], est[hi_key] = round(lo), round(hi)
        else:
            est[lo_key], est[hi_key] = round(lo, 2), round(hi, 2)

    if counted == 0:
        raise PMError(2, NO_CHILD_ESTIMATES)

    est["closure_ratios"] = applied
    est["orchestration_ratios"] = orch_applied
    # Every metric whose orchestration band is inactive, named: see the caller's warning.
    inactive = [m for m, v in orch_applied.items() if not v]

    mix = observed_mix(cal)
    try:
        for bound, key in (("tokens_k_min", "cost_low"), ("tokens_k_max", "cost_high")):
            tv = _num_or_none(est.get(bound))
            if tv is not None:
                est[key] = cost_from_tokens(split_tokens(tv, mix), model, overrides)
    except KeyError as e:
        # e.args[0], not str(e) — KeyError.__str__ repr-quotes its argument,
        # which would double-wrap a message that already reads as prose.
        raise PMError(2, e.args[0])
    est["model"] = model
    est["confidence"] = "medium"
    return est, counted, inactive
