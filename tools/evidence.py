"""Assess explicitly instrumented checks without converting missing data into passes."""

import json


def parse_event(line: str):
    if not line.startswith("TRICORDER "):
        return None
    try:
        event = json.loads(line[len("TRICORDER "):])
    except json.JSONDecodeError as error:
        raise ValueError("malformed instrumentation") from error
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    for key in ("boot_id", "event"):
        if not isinstance(event.get(key), str) or not event[key]:
            raise ValueError(f"missing/invalid {key}")
    for key in ("seq", "device_us"):
        if type(event.get(key)) is not int or event[key] < 0:
            raise ValueError(f"missing/invalid {key}")
    if event["event"] == "check":
        if not isinstance(event.get("check"), str) or not event["check"]:
            raise ValueError("missing check identity")
        if event.get("result") not in ("pass", "fail", "inconclusive"):
            raise ValueError("invalid check result")
    return event


def combine(results):
    if "fail" in results:
        return "fail"
    if not results or "inconclusive" in results:
        return "inconclusive"
    return "pass"


def assess(events, required_checks):
    boots = {}
    errors = []
    previous_boot = None
    for raw in events:
        event = parse_event("TRICORDER " + json.dumps(raw))
        boot = event["boot_id"]
        if boot not in boots:
            boots[boot] = {"last_seq": -1, "last_us": -1,
                           "checks": {name: [] for name in required_checks}}
            if event["event"] != "boot":
                errors.append(f"{boot}: missing boot event")
        elif previous_boot != boot:
            errors.append(f"{boot}: stale boot reappeared")
        state = boots[boot]
        if event["seq"] != state["last_seq"] + 1:
            errors.append(f"{boot}: sequence gap or duplicate at {event['seq']}")
        if event["device_us"] < state["last_us"]:
            errors.append(f"{boot}: device clock moved backward")
        if event["event"] == "boot" and state["last_seq"] >= 0:
            errors.append(f"{boot}: reused boot identity")
        state.update(last_seq=event["seq"], last_us=event["device_us"])
        if event["event"] == "check":
            state["checks"].setdefault(event["check"], []).append(event["result"])
        previous_boot = boot
    checks = {name: combine([combine(state["checks"][name]) for state in boots.values()])
              for name in required_checks}
    return {"status": "fail" if errors else combine(list(checks.values())),
            "checks": checks, "integrity_errors": errors, "boot_count": len(boots),
            "scope": "Only named instrumented checks; no implied peripheral or goal acceptance."}
