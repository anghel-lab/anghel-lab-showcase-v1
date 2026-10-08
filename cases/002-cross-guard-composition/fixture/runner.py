from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO_DIR = HERE / "scenarios"
ALLOWED_ROUTES = {"normal", "recovery", "startup"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def evaluate_shared_preconditions(state: dict, route: str) -> tuple[bool, str | None, list[str]]:
    trace = [f"entry:{route}", "check:schema_compatible"]
    if state.get("schemaCompatible") is not True:
        trace.append("deny:schema_incompatible")
        return False, "schema_incompatible", trace

    trace.append("check:authority_eligible")
    if state.get("authorityEligible") is not True:
        trace.append("deny:authority_ineligible")
        return False, "authority_ineligible", trace

    trace.append("check:human_gate_eligible")
    if state.get("humanGateEligible") is not True:
        trace.append("deny:human_gate_ineligible")
        return False, "human_gate_ineligible", trace

    return True, None, trace


def guarded_resume(state: dict, route: str) -> dict:
    if route not in ALLOWED_ROUTES:
        return {
            "allowed": False,
            "decision": "deny_unsupported_route",
            "interpreted": False,
            "trace": [f"entry:{route}", "check:route_supported", "deny:unsupported_route"],
        }

    allowed, reason, trace = evaluate_shared_preconditions(state, route)
    if not allowed:
        return {
            "allowed": False,
            "decision": f"deny_{reason}",
            "interpreted": False,
            "trace": trace,
        }

    trace.append("interpret:resume")
    return {
        "allowed": True,
        "decision": "resume",
        "interpreted": True,
        "trace": trace,
    }


def component_tests_pass_integration_fails(scenario: dict) -> dict:
    require(scenario["isolatedComponentTests"] == {
        "compatibilityGuard": "pass",
        "authorityGuard": "pass",
    }, "isolated component tests must pass")

    legacy_trace = [
        "legacy:component_local_tests_pass",
        "legacy:interpret:resume_without_shared_preconditions",
    ]
    legacy = {
        "allowed": True,
        "decision": "resume",
        "interpreted": True,
        "trace": legacy_trace,
    }
    guarded = guarded_resume(scenario["state"], scenario["route"])
    return {
        "isolatedComponentTestsPass": True,
        "legacyIntegration": legacy,
        "guardedIntegration": guarded,
        "gapDetected": legacy["allowed"] and not guarded["allowed"],
    }


def shared_precondition_blocks_invalid_resume(scenario: dict) -> dict:
    result = guarded_resume(scenario["state"], scenario["route"])
    return {
        "route": scenario["route"],
        "result": result,
        "blockedBeforeInterpretation": (not result["allowed"]) and (not result["interpreted"]),
    }


def yield_allowed_cleanup_denied(scenario: dict) -> dict:
    state = scenario["state"]
    result = guarded_resume(state, scenario["route"])
    if not result["allowed"]:
        return {
            "yieldAllowed": False,
            "cleanupAllowed": False,
            "decision": result["decision"],
            "trace": result["trace"],
        }

    trace = result["trace"][:-1]
    trace.append("check:yield_eligible")
    yield_allowed = state.get("yieldEligible") is True
    trace.append("yield:allowed" if yield_allowed else "yield:denied")

    trace.append("check:cleanup_eligible")
    cleanup_allowed = state.get("cleanupEligible") is True
    if cleanup_allowed:
        trace.append("cleanup:allowed")
        decision = "cleanup"
    else:
        trace.append("deny:cleanup_ineligible")
        decision = "deny_cleanup_ineligible"

    return {
        "yieldAllowed": yield_allowed,
        "cleanupAllowed": cleanup_allowed,
        "decision": decision,
        "trace": trace,
    }


def normal_recovery_startup_share_preconditions(scenario: dict) -> dict:
    cases = {}
    for case in scenario["cases"]:
        route_results = {}
        for route in scenario["routes"]:
            route_results[route] = guarded_resume(case["state"], route)
        cases[case["name"]] = {
            "routes": route_results,
            "allBlockedBeforeInterpretation": all(
                (not result["allowed"]) and (not result["interpreted"])
                for result in route_results.values()
            ),
        }
    return {
        "cases": cases,
        "allCasesBlockedBeforeInterpretation": all(
            case["allBlockedBeforeInterpretation"] for case in cases.values()
        ),
    }


def mutated_guarded_resume(
    state: dict,
    route: str,
    predicate: str,
    bypass_route: str,
) -> dict:
    require(route in ALLOWED_ROUTES, f"unsupported mutation route: {route}")
    require(predicate in {"schema", "authority"}, f"unsupported mutation predicate: {predicate}")

    trace = [f"entry:{route}", "check:schema_compatible"]
    if not (predicate == "schema" and route == bypass_route):
        if state.get("schemaCompatible") is not True:
            trace.append("deny:schema_incompatible")
            return {
                "allowed": False,
                "decision": "deny_schema_incompatible",
                "interpreted": False,
                "trace": trace,
            }

    trace.append("check:authority_eligible")
    if not (predicate == "authority" and route == bypass_route):
        if state.get("authorityEligible") is not True:
            trace.append("deny:authority_ineligible")
            return {
                "allowed": False,
                "decision": "deny_authority_ineligible",
                "interpreted": False,
                "trace": trace,
            }

    trace.append("check:human_gate_eligible")
    if state.get("humanGateEligible") is not True:
        trace.append("deny:human_gate_ineligible")
        return {
            "allowed": False,
            "decision": "deny_human_gate_ineligible",
            "interpreted": False,
            "trace": trace,
        }

    trace.append("interpret:resume")
    return {
        "allowed": True,
        "decision": "resume",
        "interpreted": True,
        "trace": trace,
    }


def run_route_specific_mutation_probes(scenario: dict) -> tuple[int, int]:
    case_by_name = {case["name"]: case for case in scenario["cases"]}
    probe_cases = {
        "schema": "schema_incompatible",
        "authority": "authority_ineligible",
    }
    passed = 0
    total = 0

    for predicate, case_name in probe_cases.items():
        state = case_by_name[case_name]["state"]
        for route in scenario["routes"]:
            total += 1
            actual = mutated_guarded_resume(state, route, predicate, route)
            expected = scenario["expected"]["cases"][case_name]["routes"][route]
            require(
                actual != expected and actual["allowed"] is True and actual["interpreted"] is True,
                f"route-specific {predicate} bypass escaped fixture: route={route}",
            )
            passed += 1
            print(f"PASS mutation {predicate}_bypass_{route}")

    return passed, total


def run_unsupported_route_probe() -> tuple[int, int]:
    actual = guarded_resume(
        {
            "schemaCompatible": True,
            "authorityEligible": True,
            "humanGateEligible": True,
        },
        "unsupported",
    )
    expected = {
        "allowed": False,
        "decision": "deny_unsupported_route",
        "interpreted": False,
        "trace": [
            "entry:unsupported",
            "check:route_supported",
            "deny:unsupported_route",
        ],
    }
    require(actual == expected, "unsupported route must fail closed before state interpretation")
    print("PASS fail-closed unsupported_route")
    return 1, 1


HANDLERS = {
    "component_tests_pass_integration_fails": component_tests_pass_integration_fails,
    "shared_precondition_blocks_invalid_resume": shared_precondition_blocks_invalid_resume,
    "yield_allowed_cleanup_denied": yield_allowed_cleanup_denied,
    "normal_recovery_startup_share_preconditions": normal_recovery_startup_share_preconditions,
}


def count_trace_events(value) -> int:
    if isinstance(value, dict):
        total = 0
        for key, nested in value.items():
            if key == "trace" and isinstance(nested, list):
                total += len(nested)
            else:
                total += count_trace_events(nested)
        return total
    if isinstance(value, list):
        return sum(count_trace_events(item) for item in value)
    return 0


def load_scenarios() -> list[dict]:
    paths = sorted(SCENARIO_DIR.glob("*.json"))
    require(bool(paths), "no scenario files found")
    scenarios = []
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        require(value.get("id") in HANDLERS, f"unknown scenario id: {path.name}")
        require("expected" in value, f"missing expected result: {path.name}")
        scenarios.append(value)
    return scenarios


def main() -> int:
    scenarios = load_scenarios()
    passed = 0
    trace_events = 0
    matrix_scenario = None

    for scenario in scenarios:
        scenario_id = scenario["id"]
        actual = HANDLERS[scenario_id](scenario)
        expected = scenario["expected"]
        if actual != expected:
            print(f"FAIL {scenario_id}")
            print(json.dumps({"expected": expected, "actual": actual}, sort_keys=True))
            return 1
        trace_events += count_trace_events(actual)
        passed += 1
        print(f"PASS {scenario_id}")
        if scenario_id == "normal_recovery_startup_share_preconditions":
            matrix_scenario = scenario

    require(matrix_scenario is not None, "route-consistency matrix scenario is required")
    mutation_passed, mutation_total = run_route_specific_mutation_probes(matrix_scenario)
    unsupported_passed, unsupported_total = run_unsupported_route_probe()

    print(
        "Showcase Case 002 fixture: "
        f"PASS ({passed}/{len(scenarios)}, trace events={trace_events}, "
        f"route-specific mutation probes={mutation_passed}/{mutation_total}, "
        f"unsupported-route probes={unsupported_passed}/{unsupported_total})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
