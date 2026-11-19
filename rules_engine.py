"""Deterministic eligibility engine with Kleene three-valued logic (True / False / Unknown).

Why three-valued: a rural user rarely gives every fact up front. "Unknown" is not "No". The engine
never guesses; it reports which *specific* unknown facts could still change the outcome so the system
can ask for exactly those by voice, or continue with partial information when the user says skip.

Rule grammar (YAML):  node := {fact, op, value} | {all:[node]} | {any:[node]} | {not: node}
Each rule has kind 'required' (node must hold) or 'exclusion' (node must NOT hold) and a `source`
chunk id that cites the guideline text the rule comes from."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

Tri = Optional[bool]   # True / False / None(unknown)

_OPS = {
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
    "in": lambda a, b: a in b, "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b, "gte": lambda a, b: a >= b,
}


@dataclass
class Leaf:
    label: Dict[str, str]
    fact: str
    value: Any                      # the user's value (None if unknown)
    status: Tri


@dataclass
class RuleResult:
    id: str
    kind: str                       # required | exclusion
    status: str                     # pass | fail | unknown
    label: Dict[str, str]
    source: str
    leaves: List[Leaf] = field(default_factory=list)
    unknown_facts: List[str] = field(default_factory=list)


@dataclass
class Evaluation:
    scheme_id: str
    verdict: str                    # ELIGIBLE | LIKELY | NOT_ELIGIBLE | NEED_INFO
    rules: List[RuleResult]
    askable: List[str]              # unknown facts we may still ask the user about
    unresolved: List[str]           # unknown facts the user skipped


def _all(vals: Iterable[Tri]) -> Tri:
    vals = list(vals)
    if any(v is False for v in vals):
        return False
    if any(v is None for v in vals):
        return None
    return True


def _any(vals: Iterable[Tri]) -> Tri:
    vals = list(vals)
    if any(v is True for v in vals):
        return True
    if any(v is None for v in vals):
        return None
    return False


def eval_node(node: dict, facts: Dict[str, Any], leaves: List[Leaf], unknown: Set[str]) -> Tri:
    if "fact" in node:
        key = node["fact"]
        val = facts.get(key)
        if val is None:
            leaves.append(Leaf(node.get("label", {}), key, None, None))
            unknown.add(key)
            return None
        try:
            res: Tri = bool(_OPS[node["op"]](val, node["value"]))
        except TypeError:
            res = None
        leaves.append(Leaf(node.get("label", {}), key, val, res))
        return res
    if "not" in node:
        r = eval_node(node["not"], facts, leaves, unknown)
        return None if r is None else (not r)
    for gate, fn in (("all", _all), ("any", _any)):
        if gate in node:
            sub_unknown: Set[str] = set()
            vals = [eval_node(n, facts, leaves, sub_unknown) for n in node[gate]]
            out = fn(vals)
            if out is None:                       # only unknowns that can still matter
                unknown |= sub_unknown
            return out
    raise ValueError(f"bad rule node: {node}")


def evaluate(scheme_id: str, rules_doc: dict, facts: Dict[str, Any], skipped: Iterable[str] = ()) -> Evaluation:
    skipped = set(skipped)
    results: List[RuleResult] = []
    for r in rules_doc["rules"]:
        leaves: List[Leaf] = []
        unk: Set[str] = set()
        node_val = eval_node(r["node"], facts, leaves, unk)
        if r["kind"] == "exclusion":
            passed: Tri = None if node_val is None else (not node_val)
        else:
            passed = node_val
        status = "unknown" if passed is None else ("pass" if passed else "fail")
        results.append(RuleResult(
            id=r["id"], kind=r["kind"], status=status,
            label=r["node"].get("label", {}), source=r["source"], leaves=leaves,
            unknown_facts=sorted(unk) if status == "unknown" else []))

    unknown_facts: List[str] = []
    for rr in results:
        for k in rr.unknown_facts:
            if k not in unknown_facts:
                unknown_facts.append(k)
    askable = [k for k in unknown_facts if k not in skipped]
    unresolved = [k for k in unknown_facts if k in skipped]

    if any(rr.status == "fail" for rr in results):
        verdict = "NOT_ELIGIBLE"
    elif all(rr.status == "pass" for rr in results):
        verdict = "ELIGIBLE"
    elif askable:
        verdict = "NEED_INFO"
    else:   # something unknown, nothing left to ask: continue with partial information
        verdict = "LIKELY" if any(rr.status == "pass" for rr in results) else "NEED_INFO"
    return Evaluation(scheme_id, verdict, results, askable, unresolved)
