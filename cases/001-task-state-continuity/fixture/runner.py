from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO_DIR = HERE / "scenarios"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def snapshot(state: dict) -> dict:
    return dict(state)


def external_wait_then_resume(scenario: dict) -> tuple[dict, list[dict]]:
    state = dict(scenario["initial"])
    checkpoints: list[dict] = []
    require(state.get("status") == "waiting_external", "initial status must be waiting_external")
    for event in scenario["events"]:
        require(event.get("type") == "external_check", "unexpected event")
        if event.get("ready") is True:
            state["status"] = "ready"
            state["resumeCondition"] = "external_ready"
        else:
            state["status"] = "waiting_external"
            state["resumeCondition"] = "not_ready"
        state["completed"] = False
        checkpoints.append(snapshot(state))
    return state, checkpoints


def child_complete_parent_continues(scenario: dict) -> tuple[dict, list[dict]]:
    state = dict(scenario["initial"])
    checkpoints: list[dict] = []
    for event in scenario["events"]:
        require(event.get("type") == "child_completed", "unexpected event")
        require(event.get("childStatus") == "completed", "child must be completed")
        if state.get("parentStatus") == "waiting_child":
            state["parentStatus"] = "running"
            state["parentReevaluated"] = True
        checkpoints.append(snapshot(state))
    return state, checkpoints


def same_blocker_retry_limit(scenario: dict) -> tuple[dict, list[dict]]:
    state = dict(scenario["initial"])
    checkpoints: list[dict] = []
    for event in scenario["events"]:
        require(event.get("type") == "same_blocker_failure", "unexpected event")
        require(event.get("blockerId") == state.get("blockerId"), "blocker identity changed")
        state["attemptCount"] = int(state.get("attemptCount", 0)) + 1
        if state["attemptCount"] >= int(state["retryLimit"]):
            state["status"] = "blocked_after_retry_limit"
        else:
            state["status"] = "retry_pending"
        checkpoints.append(snapshot(state))
    return state, checkpoints


def explicit_human_stop(scenario: dict) -> tuple[dict, list[dict]]:
    state = dict(scenario["initial"])
    checkpoints: list[dict] = []
    for event in scenario["events"]:
        require(event.get("type") == "evaluate_continuation", "unexpected event")
        if event.get("humanStop") is True:
            state["status"] = "stopped_by_human"
            state["continuationAllowed"] = False
            state["decision"] = "human_stop_precedence"
        elif event.get("autoResumeReady") is True:
            state["status"] = "ready"
            state["continuationAllowed"] = True
            state["decision"] = "automatic_resume"
        checkpoints.append(snapshot(state))
    return state, checkpoints


HANDLERS = {
    "external_wait_then_resume": external_wait_then_resume,
    "child_complete_parent_continues": child_complete_parent_continues,
    "same_blocker_retry_limit": same_blocker_retry_limit,
    "explicit_human_stop": explicit_human_stop,
}


def load_scenarios() -> list[dict]:
    paths = sorted(SCENARIO_DIR.glob("*.json"))
    require(bool(paths), "no scenario files found")
    scenarios = []
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        require(value.get("id") in HANDLERS, f"unknown scenario id: {path.name}")
        scenarios.append(value)
    return scenarios


def main() -> int:
    scenarios = load_scenarios()
    passed = 0
    temporal_checkpoints = 0
    for scenario in scenarios:
        scenario_id = scenario["id"]
        actual, checkpoints = HANDLERS[scenario_id](scenario)

        expected_checkpoints = scenario.get("expectedAfterEachEvent")
        if expected_checkpoints is not None:
            if len(expected_checkpoints) != len(checkpoints):
                print(f"FAIL {scenario_id} checkpoint_count")
                print(json.dumps({"expected": len(expected_checkpoints), "actual": len(checkpoints)}, sort_keys=True))
                return 1
            for index, (expected_checkpoint, actual_checkpoint) in enumerate(
                zip(expected_checkpoints, checkpoints, strict=True), start=1
            ):
                if actual_checkpoint != expected_checkpoint:
                    print(f"FAIL {scenario_id} checkpoint={index}")
                    print(json.dumps({"expected": expected_checkpoint, "actual": actual_checkpoint}, sort_keys=True))
                    return 1
                temporal_checkpoints += 1

        expected = scenario["expected"]
        if actual != expected:
            print(f"FAIL {scenario_id}")
            print(json.dumps({"expected": expected, "actual": actual}, sort_keys=True))
            return 1
        passed += 1
        print(f"PASS {scenario_id}")

    print(f"Showcase Case 001 fixture: PASS ({passed}/{len(scenarios)}, temporal checkpoints={temporal_checkpoints})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
