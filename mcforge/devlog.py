"""`devlog PROJECT`: gate the development client run from its log.

A screenshot shows that something rendered; a number shows that it is right. The
driver and dev-flagged mod code print machine-readable lines

    MCFORGE-TRACE <kind> key=value key=value ...

and this command checks them, together with the things every client run should be
free of: an unfinished script, exceptions that name the mod or its libraries,
sound events without a sound, and missing models or textures of the mod.

Rules (JSON, optional, `--rules FILE`; default PROJECT/devlog-rules.json when present):

    {"prefixes": ["MCFORGE-TRACE"],
     "ignore_errors": ["text of a known harmless error line"],
     "gates": {"final": [
       {"kind": "orient", "field": "err", "max": 0.15, "count_min": 8},
       {"kind": "spring", "where": {"id": "physics"}, "group_by": "name", "pick": "last",
        "field": "peak", "divide_by": "clamp", "min": 0.65, "max": 0.85},
       {"kind": "chain", "skip": {"id": "teleport*"}, "field": "stretch", "max": 1.15},
       {"kind": "hit", "distinct_min": {"target": 3}},
       {"kind": "fps", "compare": {"field": "fps", "a": {"scene": "eight"}, "b": {"scene": "empty"}, "min_ratio": 0.6},
        "severity": "warn"}]}}

A check selects the trace records of one `kind` (`where` and `skip` match fields
with shell wildcards), optionally groups them (`group_by`) and reduces each group
(`pick`: last, max, min, mean, median, p90), then tests `field` (optionally divided
by another field) against `min`/`max`. `count_min`/`count_max` bound the number of
selected records (a check with a `field` needs at least one record unless
`count_min` is 0), `equals` requires exact field values, `distinct_min` a number of
different values, `compare` the ratio of the mean of a field between two selections.
`"severity": "warn"` reports without failing.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import json
import math
from pathlib import Path
import re

from .workbench import read_json

MAX_LOG_BYTES = 256 * 1024 * 1024
KEY_VALUE = re.compile(r"([A-Za-z_][\w.]*)=(\S+)")
DONE = re.compile(r"MCFORGE-DEVSHOTS done (\d+)")
FAILED = re.compile(r"MCFORGE-DEVSHOTS failed: ([^\r\n]+)")
ERROR_LINE = re.compile(r"(Exception|Error)\b")
STACK = ("at ", "Caused by", "...", "Suppressed")
LIBRARIES = ("software.bernie",)
SOUND = ("Unable to play unknown soundEvent", "Missing sound for event", "Unable to play empty soundEvent")
ASSET = ("Unable to load model", "Missing textures in model", "Using missing texture", "Failed to load texture",
         "Unable to resolve texture", "Missing model", "Exception loading blockstate", "Couldn't load", "Could not load",
         "Failed to load model", "Parsing error loading")
PICKS = ("last", "max", "min", "mean", "median", "p90")


def find_log(project: Path) -> Path | None:
    """The newest dev client log: the run directory's latest.log, else the newest receipt's client.log."""
    candidates = [project / "run-devshots/logs/latest.log"]
    candidates += sorted((project / "build/mcforge/verification").glob("*/client.log"))
    existing = [path for path in candidates if path.is_file()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def _number(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number


def parse_log(text: str, mod_id: str, package: str, prefixes=("MCFORGE-TRACE",), ignore=()) -> dict:
    lines = text.splitlines()
    records: dict[str, list[dict]] = {}
    errors, sounds, assets = [], [], []
    done = failed = None
    needles = tuple(n for n in (package, f"{mod_id}:", *LIBRARIES) if n)
    for index, line in enumerate(lines):
        for prefix in prefixes:
            marker = prefix + " "
            if marker in line:
                body = line.split(marker, 1)[1].strip()
                kind, _, rest = body.partition(" ")
                records.setdefault(kind, []).append(dict(KEY_VALUE.findall(rest)) | {"_line": index + 1})
                break
        match = DONE.search(line)
        if match:
            done = int(match.group(1))
        match = FAILED.search(line)
        if match:
            failed = match.group(1)
        if any(text in line for text in ignore):
            continue
        if any(marker in line for marker in SOUND) and f"{mod_id}:" in line:
            sounds.append(line.strip()[:240])
        elif any(marker in line for marker in ASSET) and f"{mod_id}:" in line:
            assets.append(line.strip()[:240])
        elif ERROR_LINE.search(line) and ("ERROR" in line or "FATAL" in line or line.lstrip().startswith(("java.", "Caused by", "Exception in"))):
            block = [line]
            for following in lines[index + 1:index + 80]:
                if following.lstrip().startswith(STACK):
                    block.append(following)
                else:
                    break
            joined = " ".join(block)
            if any(needle in joined for needle in needles) and "MCFORGE-DEVSHOTS" not in line:
                errors.append({"line": index + 1, "text": line.strip()[:240]})
    return {"records": records, "errors": errors, "unknown_sounds": sounds, "missing_assets": assets, "done": done, "failed": failed}


def _matches(record: dict, patterns: dict | None) -> bool:
    for key, pattern in (patterns or {}).items():
        options = pattern if isinstance(pattern, list) else [pattern]
        value = record.get(key)
        if value is None or not any(fnmatchcase(str(value), str(option)) for option in options):
            return False
    return True


def _select(records: dict, kind: str, where=None, skip=None) -> list[dict]:
    return [r for r in records.get(kind, []) if _matches(r, where) and not (skip and _matches(r, skip))]


def _reduce(values: list[float], pick: str) -> float:
    values = [v for v in values if not math.isnan(v)]
    if not values:
        return math.nan
    if pick == "last":
        return values[-1]
    if pick == "max":
        return max(values)
    if pick == "min":
        return min(values)
    if pick == "mean":
        return sum(values) / len(values)
    ordered = sorted(values)
    if pick == "median":
        return ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2
    if pick == "p90":
        return ordered[min(len(ordered) - 1, int(math.floor(0.9 * (len(ordered) - 1) + 0.5)))]
    raise ValueError(f"pick must be one of {', '.join(PICKS)}")


def _value(record: dict, check: dict) -> float:
    value = _number(record.get(check["field"]))
    if check.get("divide_by"):
        divisor = _number(record.get(check["divide_by"]))
        return value / divisor if divisor and not math.isnan(divisor) else math.nan
    return value


def run_check(records: dict, check: dict) -> list[str]:
    if not isinstance(check, dict) or not isinstance(check.get("kind"), str):
        raise ValueError(f"Each check needs a kind: {check!r}")
    kind = check["kind"]
    label = check.get("name") or kind
    problems = []
    if "compare" in check:
        compare = check["compare"]
        field = compare["field"]
        a = _reduce([_number(r.get(field)) for r in _select(records, kind, compare.get("a"))], compare.get("pick", "mean"))
        b = _reduce([_number(r.get(field)) for r in _select(records, kind, compare.get("b"))], compare.get("pick", "mean"))
        if math.isnan(a) or math.isnan(b) or b == 0:
            return [f"{label}: no {field} trace for {compare.get('a')} and {compare.get('b')}"]
        ratio = a / b
        if "min_ratio" in compare and ratio < compare["min_ratio"]:
            problems.append(f"{label}: {field} {a:g} is {ratio:.2f} of {b:g} (minimum {compare['min_ratio']})")
        if "max_ratio" in compare and ratio > compare["max_ratio"]:
            problems.append(f"{label}: {field} {a:g} is {ratio:.2f} of {b:g} (maximum {compare['max_ratio']})")
        return problems
    selected = _select(records, kind, check.get("where"), check.get("skip"))
    needs_records = "field" in check or "equals" in check or "distinct_min" in check
    count_min = check.get("count_min", 1 if needs_records else None)
    if count_min is not None and len(selected) < count_min:
        return [f"{label}: {len(selected)} trace record(s), need at least {count_min}"]
    if "count_max" in check and len(selected) > check["count_max"]:
        problems.append(f"{label}: {len(selected)} trace record(s), at most {check['count_max']} allowed")
    for key, wanted in (check.get("equals") or {}).items():
        bad = [r for r in selected if str(r.get(key)) != str(wanted)]
        if bad:
            problems.append(f"{label}: {len(bad)} record(s) with {key} != {wanted} (first at log line {bad[0]['_line']})")
    for key, wanted in (check.get("distinct_min") or {}).items():
        values = sorted({str(r.get(key)) for r in selected if r.get(key) is not None})
        if len(values) < wanted:
            problems.append(f"{label}: {key} has {len(values)} distinct value(s) {values}, need {wanted}")
    if "field" in check:
        groups: dict[str, list[dict]] = {}
        if check.get("group_by"):
            for record in selected:
                groups.setdefault(str(record.get(check["group_by"])), []).append(record)
            reduced = {name: _reduce([_value(r, check) for r in rows], check.get("pick", "last")) for name, rows in groups.items()}
        elif check.get("pick"):
            reduced = {check["pick"]: _reduce([_value(r, check) for r in selected], check["pick"])}
        else:
            reduced = {f"line {r['_line']}": _value(r, check) for r in selected}
        what = check["field"] + (f"/{check['divide_by']}" if check.get("divide_by") else "")
        shown = 0
        for name, value in reduced.items():
            low, high = check.get("min"), check.get("max")
            bad = math.isnan(value) or (low is not None and value < low - 1e-9) or (high is not None and value > high + 1e-9)
            if bad:
                shown += 1
                if shown <= 8:
                    bounds = f"{'' if low is None else low}..{'' if high is None else high}"
                    problems.append(f"{label}: {what} = {value:.4g} outside {bounds} ({name})")
        if shown > 8:
            problems.append(f"{label}: {shown - 8} more value(s) outside the bounds")
    return problems


def summarize(records: dict) -> dict:
    """Per kind: record count and min/max of every numeric field, split by `name` when the records carry one."""
    summary = {}
    for kind, rows in records.items():
        fields: dict[str, list[float]] = {}
        for row in rows:
            scope = f"{row['name']}." if "name" in row else ""
            for key, value in row.items():
                number = _number(value)
                if key not in ("_line", "name") and not math.isnan(number):
                    fields.setdefault(scope + key, []).append(number)
        entry = {"count": len(rows)}
        for key in sorted(fields)[:60]:
            values = fields[key]
            entry[key] = {"min": round(min(values), 4), "max": round(max(values), 4), "last": round(values[-1], 4)}
        summary[kind] = entry
    return summary


def check_devlog(project: Path, log: Path | None = None, rules: Path | None = None, gate: str | None = None) -> dict:
    project = Path(project).resolve()
    lock = read_json(project / "mcforge-project.json")
    log = Path(log).resolve() if log else find_log(project)
    if log is None or not log.is_file():
        raise ValueError("No dev client log found (run-devshots/logs/latest.log); run verify PROJECT --client first or pass --log FILE")
    if log.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("Log exceeds 256 MiB")
    if rules is None and (project / "devlog-rules.json").is_file():
        rules = project / "devlog-rules.json"
    config = json.loads(Path(rules).read_text(encoding="utf-8-sig")) if rules else {}
    if not isinstance(config, dict):
        raise ValueError("Rules must be a JSON object")
    gates = config.get("gates") or {}
    if gate and gate not in gates:
        raise ValueError(f"Gate {gate!r} is not in the rules; known: {', '.join(sorted(gates)) or 'none (pass --rules FILE)'}")
    parsed = parse_log(log.read_text(encoding="utf-8", errors="replace"), lock["mod_id"], lock.get("package", ""),
                       tuple(config.get("prefixes") or ("MCFORGE-TRACE",)), tuple(config.get("ignore_errors") or ()))
    problems, warnings = [], []
    if parsed["failed"]:
        problems.append(f"the driver failed: {parsed['failed']}")
    elif parsed["done"] is None:
        problems.append("no \"MCFORGE-DEVSHOTS done\" marker: the driver did not finish")
    if parsed["errors"]:
        problems.append(f"{len(parsed['errors'])} error(s) naming the mod or its libraries, first at line "
                        f"{parsed['errors'][0]['line']}: {parsed['errors'][0]['text']}")
    if parsed["unknown_sounds"]:
        problems.append(f"{len(parsed['unknown_sounds'])} sound event problem(s), first: {parsed['unknown_sounds'][0]}")
    if parsed["missing_assets"]:
        problems.append(f"{len(parsed['missing_assets'])} missing model/texture/data line(s), first: {parsed['missing_assets'][0]}")
    names = [gate] if gate else sorted(gates)
    for name in names:
        for check in gates[name]:
            found = [f"[{name}] {text}" for text in run_check(parsed["records"], check)]
            (warnings if isinstance(check, dict) and check.get("severity") == "warn" else problems).extend(found)
    return {"project": str(project), "log": str(log), "rules": str(rules) if rules else None, "gates": names,
            "done": parsed["done"], "screenshots": parsed["done"], "traces": summarize(parsed["records"]),
            "errors": parsed["errors"][:20], "unknown_sounds": parsed["unknown_sounds"][:20],
            "missing_assets": parsed["missing_assets"][:20], "problems": problems, "warnings": warnings,
            "status": "failed" if problems else "passed"}
