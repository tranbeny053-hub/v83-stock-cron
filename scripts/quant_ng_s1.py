"""Make a pure MOCK/OFFLINE S1 decision over parsed listing observations; it contains no network
code.
Under S1-3(c), the supplied number is the P1-phase cap; the P0-phase cap is outside this engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


class Refusal(Exception):
    """A malformed, unauthorized, or unsafe MOCK decision input."""


# This set changes only by reviewed code.
OWNER_RULED_S1_PLAN_SHA256 = frozenset()
_PLAN_KEYS = {"schema", "status", "rulings", "host", "cap", "probes", "draw"}
_RULING_KEYS = {f"S1-{i}" for i in range(1, 14)}
_OBS_KEYS = {
    "schema",
    "source",
    "marker",
    "run_start_utc",
    "run_end_utc",
    "flags",
    "requests_used",
    "p0",
    "p1",
}
_FLAGS = {
    "redirect": "redirect",
    "non_https": "non-HTTPS URL",
    "non_success": "non-success response",
    "unreadable_folder": "unreadable folder",
    "unparsable_page": "unparsable page",
    "protected_fragment": "protected fragment",
}
_PROTECTED = {"BTCUSDT", "ETHUSDT"}


def _shape(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise Refusal(f"malformed {label}: {label}")
    for key in keys:
        if key not in value:
            raise Refusal(f"malformed {label}: {key}")
    for key in value:
        if key not in keys:
            raise Refusal(f"malformed {label}: {key}")


def _enum(value: Any, allowed: set[Any], key: str) -> None:
    try:
        valid = value in allowed
    except TypeError:
        valid = False
    if not valid:
        raise Refusal(f"malformed plan: {key}")


def _int(value: Any, minimum: int, key: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise Refusal(f"malformed plan: {key}")
    return True


def _instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise Refusal("malformed instant")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise Refusal("malformed instant") from exc


def _validate_plan(plan: dict) -> None:
    _shape(plan, _PLAN_KEYS, "plan")
    if plan["schema"] != "ucpe.s1_plan.v1":
        raise Refusal("malformed plan: schema")
    if not isinstance(plan["status"], str) or plan["status"] not in {"MOCK", "OWNER_RULED"}:
        raise Refusal("malformed plan: status")
    if plan["status"] == "OWNER_RULED":
        raise Refusal("plan not owner-ruled")
    rulings = plan["rulings"]
    _shape(rulings, _RULING_KEYS, "plan")
    choices = {
        "S1-1": {"a", "b", "c"},
        "S1-2": {"a", "b", "c"},
        "S1-3": {"a", "b", "c"},
        "S1-4": {"a", "b", "c", "d"},
        "S1-7": {"D", "D+1"},
        "S1-8": {"a", "b"},
        "S1-9": {"a", "b"},
        "S1-10": {"a", "b"},
        "S1-11": {"a", "b"},
        "S1-12": {"a", "b", "n/a"},
        "S1-13": {"a", "b", "n/a"},
    }
    for key, allowed in choices.items():
        _enum(rulings[key], allowed, key)
    _shape(rulings["S1-5"], {"stop_evidence", "stop_inconclusive"}, "plan")
    _enum(rulings["S1-5"]["stop_evidence"], {"a", "b"}, "S1-5")
    _enum(rulings["S1-5"]["stop_inconclusive"], {"consume", "run_only"}, "S1-5")
    if not isinstance(rulings["S1-6"], list) or rulings["S1-6"] not in [
        ["a"],
        ["a", "b"],
        ["a", "c"],
        ["a", "b", "c"],
    ]:
        raise Refusal("malformed plan: S1-6")
    host = plan["host"]
    if not isinstance(host, str) or not host.endswith(".invalid"):
        raise Refusal("host must be a MOCK host")
    _shape(plan["cap"], {"number", "m", "H", "F"}, "plan")
    cap = plan["cap"]
    mode = rulings["S1-3"]
    if mode in {"a", "c"}:
        _int(cap["number"], 1, "cap.number")
        if any(cap[k] is not None for k in ("m", "H", "F")):
            raise Refusal("malformed plan: cap")
    else:
        if cap["number"] is not None:
            raise Refusal("malformed plan: cap")
        _int(cap["m"], 0, "cap.m")
        _int(cap["H"], 1, "cap.H")
        _int(cap["F"], 1, "cap.F")
    probes = plan["probes"]
    if (
        not isinstance(probes, list)
        or any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9]{2,30}", s) for s in probes)
        or len(set(probes)) != len(probes)
    ):
        raise Refusal("malformed plan: probes")
    if _PROTECTED.intersection(probes):
        raise Refusal("BTCUSDT and ETHUSDT are never probed")
    source = rulings["S1-4"]
    if bool(probes) != (source in {"a", "b", "d"}):
        raise Refusal("malformed plan: probes")
    if (rulings["S1-12"] == "n/a") != (source in {"a", "b"}):
        raise Refusal("malformed plan: S1-12")
    if (rulings["S1-13"] == "n/a") != (source != "d"):
        raise Refusal("malformed plan: S1-13")
    draw = plan["draw"]
    if (draw is not None) != (source in {"c", "d"}):
        raise Refusal("malformed plan: draw")
    if draw is not None:
        _shape(draw, {"kind", "k"}, "plan")
        _enum(draw["kind"], {"sorted_first_k", "every"}, "draw.kind")
        if draw["kind"] == "sorted_first_k":
            _int(draw["k"], 1, "draw.k")
        elif draw["k"] is not None:
            raise Refusal("malformed plan: draw.k")
    if rulings["S1-1"] == "b":
        raise Refusal("S1-1 (b): no run is authorized")
    if rulings["S1-2"] == "c":
        raise Refusal("S1-2 (c): no host, no run")


def _page(page: Any, p0: bool) -> None:
    keys = {"host", "capture_utc", "date_header", "names"} | ({"page_size"} if p0 else set())
    _shape(page, keys, "observation")
    if page["capture_utc"] is not None:
        _instant(page["capture_utc"])
    if page["date_header"] is not None and not isinstance(page["date_header"], str):
        raise Refusal("malformed observation: date_header")
    if not isinstance(page["host"], str) or not page["host"].endswith(".invalid"):
        raise Refusal("host must be a MOCK host")
    if not isinstance(page["names"], list) or any(not isinstance(n, str) for n in page["names"]):
        raise Refusal("malformed observation: page")
    if (
        p0
        and page["page_size"] is not None
        and (
            isinstance(page["page_size"], bool)
            or not isinstance(page["page_size"], int)
            or page["page_size"] < 1
        )
    ):
        raise Refusal("malformed observation: page_size")


def _validate_observation(obs: dict) -> None:
    _shape(obs, _OBS_KEYS, "observation")
    if obs["source"] != "mock" or obs["marker"] != "UCPE-MOCK-v1":
        raise Refusal("observation is not MOCK")
    if obs["schema"] != "ucpe.s1_observation.v1":
        raise Refusal("malformed observation: schema")
    for k in ("run_start_utc", "run_end_utc"):
        if obs[k] is not None:
            _instant(obs[k])
    _shape(obs["flags"], set(_FLAGS), "observation")
    if any(not isinstance(v, bool) for v in obs["flags"].values()):
        raise Refusal("malformed observation: flags")
    if (
        isinstance(obs["requests_used"], bool)
        or not isinstance(obs["requests_used"], int)
        or obs["requests_used"] < 0
    ):
        raise Refusal("malformed observation: requests_used")
    _shape(obs["p0"], {"pages"}, "observation")
    if not isinstance(obs["p0"]["pages"], list):
        raise Refusal("malformed observation: p0.pages")
    for page in obs["p0"]["pages"]:
        _page(page, True)
    if not isinstance(obs["p1"], dict):
        raise Refusal("malformed observation: p1")
    for symbol, folder in obs["p1"].items():
        if not isinstance(symbol, str):
            raise Refusal("malformed observation: p1")
        _shape(folder, {"pages"}, "observation")
        if not isinstance(folder["pages"], list):
            raise Refusal("malformed observation: p1.pages")
        for page in folder["pages"]:
            _page(page, False)


def _valid_name(symbol: str, name: str, suffix: str) -> date | None:
    match = re.fullmatch(re.escape(symbol) + r"-1d-(\d{4})-(\d{2})-(\d{2})\.zip" + suffix, name)
    if not match:
        return None
    try:
        return date(*(int(x) for x in match.groups()))
    except ValueError:
        return None


def decide(plan: dict, observation: dict) -> dict:
    """Return a deterministic decision without mutating either input."""
    _validate_plan(plan)
    _validate_observation(observation)
    r = plan["rulings"]
    p0_names: list[str] = []
    dropped = 0
    duplicate = False
    for page in observation["p0"]["pages"]:
        for name in page["names"]:
            if name in _PROTECTED:
                dropped += 1
            elif name in p0_names:
                duplicate = True
            else:
                p0_names.append(name)
    draw_names: list[str] = []
    if plan["draw"] is not None:
        ordered = sorted(p0_names)
        draw_names = (
            ordered[: plan["draw"]["k"]] if plan["draw"]["kind"] == "sorted_first_k" else ordered
        )
    probes = list(plan["probes"])
    kinds = {s: "a" for s in probes}
    if r["S1-4"] in {"c", "d"}:
        for symbol in draw_names:
            if symbol not in kinds:
                probes.append(symbol)
                kinds[symbol] = "c"
    K = len(probes)
    if r["S1-3"] == "b":
        pages0 = observation["p0"]["pages"]
        if len(pages0) <= 1 or pages0[0]["page_size"] is None:
            cap = plan["cap"]["H"]
        else:
            P = pages0[0]["page_size"]
            cap = min(
                plan["cap"]["H"],
                len(pages0) + K * ((2 * plan["cap"]["F"] + P - 1) // P) + plan["cap"]["m"],
            )
    else:
        cap = plan["cap"]["number"]
    stops = [label for key, label in _FLAGS.items() if observation["flags"][key]]
    if observation["requests_used"] > cap:
        stops.append("cap reached")
    if duplicate:
        stops.append("duplicate name")
    if r["S1-4"] == "c" and not draw_names:
        stops.append("K = 0")
    if r["S1-4"] == "d" and not draw_names and r["S1-13"] == "b":
        stops.append("empty (c) part")
    all_pages = [(p, "P0") for p in observation["p0"]["pages"]]
    all_pages += [(p, s) for s, folder in observation["p1"].items() for p in folder["pages"]]
    if any(p["host"] != plan["host"] for p, _ in all_pages):
        stops.append("host mismatch")
    if any(p["capture_utc"] is None for p, _ in all_pages):
        stops.append("unreadable clock")
    if "b" in r["S1-6"] and any(
        not isinstance(p["date_header"], str) or not p["date_header"] for p, _ in all_pages
    ):
        stops.append("unreadable clock")
    if "c" in r["S1-6"] and (
        observation["run_start_utc"] is None or observation["run_end_utc"] is None
    ):
        stops.append("unreadable clock")
    if set(observation["p1"]) - set(probes):
        stops.append("unexpected folder")
    if any(s in p0_names and s not in observation["p1"] for s in probes):
        stops.append("unreadable folder")
    probe_forms: dict[str, tuple[bool, list[date]]] = {}
    any_form_fault = False
    for symbol, folder in observation["p1"].items():
        names = [n for page in folder["pages"] for n in page["names"]]
        form_fault = len(names) != len(set(names))
        zips: list[date] = []
        companions: list[date] = []
        for name in names:
            counted = _valid_name(symbol, name, "")
            companion = _valid_name(symbol, name, r"\.CHECKSUM")
            if counted:
                zips.append(counted)
            elif companion:
                companions.append(companion)
            else:
                form_fault = True
        if r["S1-9"] == "b" and (
            any(zips.count(d) != companions.count(d) for d in set(zips + companions))
        ):
            form_fault = True
        probe_forms[symbol] = (form_fault, zips)
        any_form_fault |= form_fault
    if r["S1-10"] == "a" and any_form_fault:
        stops.append("form fault")
    stops = list(dict.fromkeys(stops))
    theta = 31 if r["S1-7"] == "D" else 32
    base = {
        "schema": "ucpe.s1_decision.v1",
        "status": "MOCK",
        "run_outcome": None,
        "run_stops": stops,
        "probes": [],
        "consequence": None,
        "cap": cap,
        "theta": theta,
        "dropped": dropped,
        "K": K,
        "residual_risk": (
            "a symbol halted, not delisted, for more than 30 days also passes; "
            "S1 cannot tell them apart"
        ),
    }
    if stops:
        base["run_outcome"] = "STOP-inconclusive"
        base["consequence"] = _consequence("STOP-inconclusive", r["S1-5"])
        return base
    rows = []
    for symbol in probes:
        outcome, reason, D, C, delta = "inconclusive", "present, not PASS", None, None, None
        if symbol not in p0_names:
            outcome = "inconclusive" if r["S1-8"] == "a" else "STOP-evidence"
            reason = "absent from P0"
        elif symbol in probe_forms and probe_forms[symbol][0] and r["S1-10"] == "b":
            reason = "form fault"
        elif symbol not in probe_forms or not probe_forms[symbol][1]:
            reason = "no counting name"
        else:
            dates = probe_forms[symbol][1]
            D = max(dates).isoformat()
            captures = [_instant(p["capture_utc"]) for p in observation["p1"][symbol]["pages"]]
            C = min(captures).date().isoformat() if captures else None
            if C is None:
                reason = "no counting name"
                D = None
            else:
                delta = (date.fromisoformat(C) - date.fromisoformat(D)).days
                if delta >= theta:
                    outcome, reason = "PASS", "delta meets threshold"
        rows.append(
            {
                "symbol": symbol,
                "kind": kinds[symbol],
                "outcome": outcome,
                "reason": reason,
                "D": D,
                "C": C,
                "delta": delta,
            }
        )
    base["probes"] = rows
    any_pass = any(row["outcome"] == "PASS" for row in rows)
    all_evidence = bool(rows) and all(row["outcome"] == "STOP-evidence" for row in rows)
    any_evidence = any(row["outcome"] == "STOP-evidence" for row in rows)
    full_sweep = (
        r["S1-12"] == "a"
        and set(p0_names).issubset(probes)
        and all(
            next(
                (row["reason"] == "present, not PASS" for row in rows if row["symbol"] == name),
                False,
            )
            for name in p0_names
        )
    )
    if any_pass:
        outcome = "PASS"
    elif (all_evidence if r["S1-11"] == "a" else any_evidence) or full_sweep:
        outcome = "STOP-evidence"
    else:
        outcome = "STOP-inconclusive"
    base["run_outcome"] = outcome
    base["consequence"] = _consequence(outcome, r["S1-5"])
    return base


def _consequence(outcome: str, ruling: dict) -> str:
    if outcome == "PASS":
        return "pass: some delisted symbols are kept; never proves complete survivorship"
    if outcome in {"STOP-evidence", "STOP-inconclusive"} and (
        outcome == "STOP-evidence" or ruling["stop_inconclusive"] == "consume"
    ):
        return (
            "route ends"
            if ruling["stop_evidence"] == "a"
            else "survivor panel only; no historical-universe claim"
        )
    return "this run only; a new plan may be authorized"


def run(plan_path: str | Path, plan_sha256: str, observation_path: str | Path) -> dict:
    plan_bytes = Path(plan_path).read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != plan_sha256:
        raise Refusal("plan digest mismatch")
    try:
        plan = json.loads(plan_bytes)
    except json.JSONDecodeError as exc:
        raise Refusal("malformed plan: JSON") from exc
    try:
        observation = json.loads(Path(observation_path).read_bytes())
    except json.JSONDecodeError as exc:
        raise Refusal("malformed observation: JSON") from exc
    return decide(plan, observation)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("plan_sha256")
    parser.add_argument("observation")
    args = parser.parse_args(argv)
    try:
        result = run(args.plan, args.plan_sha256, args.observation)
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
