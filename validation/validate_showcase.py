from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_RESOLVED = ROOT.resolve()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def require_fields(value: dict, fields: list[str], label: str, *, non_empty: bool = False) -> None:
    for field in fields:
        require(field in value, f"missing required field {field}: {label}")
        require(value[field] is not None, f"null required field {field}: {label}")
        if non_empty:
            require(bool(value[field]), f"empty required field {field}: {label}")


def resolve_repo_file(relative: str, label: str) -> Path:
    require(isinstance(relative, str) and relative.strip(), f"empty repository file ref: {label}")
    ref = Path(relative)
    require(not ref.is_absolute(), f"absolute repository file ref is forbidden: {label}")
    candidate = (ROOT / ref).resolve()
    try:
        candidate.relative_to(ROOT_RESOLVED)
    except ValueError:
        require(False, f"repository file ref escapes root: {label}: {relative}")
    require(candidate.is_file(), f"missing repository file ref: {label}: {relative}")
    return candidate


def load_json_ref(relative: str, label: str):
    path = resolve_repo_file(relative, label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: invalid JSON for {label}: {relative}: {exc}") from exc


def require_repo_file_refs(value, label: str) -> list[str]:
    require(isinstance(value, list) and bool(value), f"{label} must be a non-empty list")
    refs: list[str] = []
    for index, relative in enumerate(value):
        require(isinstance(relative, str) and relative.strip(), f"empty {label}[{index}]")
        resolve_repo_file(relative, f"{label}[{index}]")
        refs.append(relative)
    require(len(refs) == len(set(refs)), f"duplicate refs in {label}")
    return refs


def validate_reproduction_invocation(
    invocation,
    *,
    fixture: dict,
    invocation_contract: dict,
    case_id: str,
    label: str,
) -> dict:
    require(isinstance(invocation, dict), f"{label} must be a structured object")
    required_fields = invocation_contract.get("requiredFields", [])
    require(bool(required_fields), "reproductionInvocationContract.requiredFields must be non-empty")
    require_fields(invocation, required_fields, label)

    profiles = invocation_contract.get("profiles", {})
    require(isinstance(profiles, dict) and bool(profiles), "reproductionInvocationContract.profiles required")
    profile_name = invocation.get("profile")
    require(profile_name in profiles, f"unknown reproduction invocation profile: {case_id}")
    profile = profiles[profile_name]

    runner = invocation.get("runner")
    allowed_runners = profile.get("allowedRunners", [])
    require(isinstance(allowed_runners, list) and bool(allowed_runners), f"allowed runners missing: {profile_name}")
    require(runner in allowed_runners, f"runner is not allowed by profile {profile_name}: {case_id}")

    entry_artifact = invocation.get("entryArtifactRef")
    require(isinstance(entry_artifact, str) and entry_artifact.strip(), f"entryArtifactRef required: {case_id}")
    require(entry_artifact == fixture.get("entryArtifactRef"), f"invocation entryArtifactRef mismatch: {case_id}")
    resolve_repo_file(entry_artifact, f"invocation entryArtifactRef for {case_id}")

    artifact_refs = fixture.get("artifactRefs", [])
    require(entry_artifact in artifact_refs, f"invocation entryArtifactRef must be in fixture artifactRefs: {case_id}")

    args = invocation.get("args")
    require(isinstance(args, list), f"invocation args must be a list: {case_id}")
    require(all(isinstance(arg, str) for arg in args), f"invocation args must contain only strings: {case_id}")

    require(profile.get("entryArtifactArgIndex") == 1, f"unsupported entry artifact position: {profile_name}")
    require(profile.get("argsAfterEntryArtifact") is True, f"profile must place args after entry artifact: {profile_name}")

    return invocation


def validate_passing_evidence(
    *,
    case_id: str,
    validation_level: str,
    fixture: dict,
    validation: dict,
    evidence_contract: dict,
    invocation_contract: dict,
    schema_version: str,
) -> None:
    artifact_refs = require_repo_file_refs(fixture.get("artifactRefs"), f"artifactRefs for {case_id}")
    evidence_refs = require_repo_file_refs(validation.get("evidenceRefs"), f"evidenceRefs for {case_id}")

    required_fields = evidence_contract.get("requiredFields", [])
    require(bool(required_fields), "validationEvidenceContract.requiredFields must be non-empty")
    passing_result = evidence_contract.get("passingResult")
    require(isinstance(passing_result, str) and passing_result, "validationEvidenceContract.passingResult required")

    for relative in evidence_refs:
        evidence = load_json_ref(relative, f"validation evidence for {case_id}")
        require(isinstance(evidence, dict), f"validation evidence must be an object: {relative}")
        require_fields(evidence, required_fields, f"validation evidence {relative}", non_empty=True)
        require(evidence.get("schemaVersion") == schema_version, f"evidence schemaVersion mismatch: {relative}")
        require(evidence.get("caseId") == case_id, f"evidence caseId mismatch: {relative}")
        require(evidence.get("validationLevel") == validation_level, f"evidence validationLevel mismatch: {relative}")
        require(evidence.get("result") == passing_result, f"validation evidence is not passing: {relative}")
        evidence_artifact_refs = require_repo_file_refs(
            evidence.get("artifactRefs"),
            f"evidence artifactRefs in {relative}",
        )
        if evidence_contract.get("artifactRefsMustMatchFixture") is True:
            require(
                set(evidence_artifact_refs) == set(artifact_refs),
                f"evidence artifactRefs do not match fixture artifactRefs: {relative}",
            )

        if validation_level == "public_reproduction":
            reproduction_fields = evidence_contract.get("publicReproductionRequiredFields", [])
            require_fields(evidence, reproduction_fields, f"public reproduction evidence {relative}", non_empty=True)
            evidence_invocation = validate_reproduction_invocation(
                evidence.get("reproductionInvocation"),
                fixture=fixture,
                invocation_contract=invocation_contract,
                case_id=case_id,
                label=f"evidence reproductionInvocation {relative}",
            )
            if evidence_contract.get("reproductionInvocationMustMatchValidation") is True:
                require(
                    evidence_invocation == validation.get("reproductionInvocation"),
                    f"evidence reproductionInvocation mismatch: {relative}",
                )


def main() -> None:
    manifest = load_json_ref("showcase.json", "root manifest")
    require(isinstance(manifest, dict), "root manifest must be an object")
    require(manifest.get("canonical") is False, "Showcase must remain non-canonical")
    require(
        manifest.get("semantics", {}).get("productionReimport") == "prohibited",
        "production reverse-import must be prohibited",
    )
    require(
        manifest.get("releaseBoundary", {}).get("fullRepositorySurfaceAuditRequired") is True,
        "public release must require full repository-surface audit",
    )

    entrypoints = manifest.get("entrypoints")
    require(isinstance(entrypoints, dict) and bool(entrypoints), "manifest entrypoints must be a non-empty object")
    require("evidenceContract" in entrypoints, "manifest evidenceContract entrypoint is required")

    contract = load_json_ref(entrypoints["evidenceContract"], "evidenceContract entrypoint")
    require(isinstance(contract, dict), "evidence contract must be an object")
    required_entrypoint_paths = contract.get("requiredEntrypointPaths")
    require(
        isinstance(required_entrypoint_paths, dict) and bool(required_entrypoint_paths),
        "contract requiredEntrypointPaths must be a non-empty object",
    )
    for name, expected_path in required_entrypoint_paths.items():
        require(name in entrypoints, f"missing required manifest entrypoint: {name}")
        require(entrypoints[name] == expected_path, f"manifest entrypoint path mismatch: {name}")
        resolve_repo_file(entrypoints[name], f"manifest entrypoint {name}")

    entrypoint_shapes = contract.get("entrypointShapes", {})
    require(isinstance(entrypoint_shapes, dict) and bool(entrypoint_shapes), "contract entrypointShapes required")
    require_fields(contract, entrypoint_shapes.get("evidenceContract", []), "evidenceContract entrypoint", non_empty=True)

    claim_index = load_json_ref(entrypoints["claims"], "claims entrypoint")
    case_index = load_json_ref(entrypoints["cases"], "cases entrypoint")
    require(isinstance(claim_index, dict), "claims entrypoint must be a JSON object")
    require(isinstance(case_index, dict), "cases entrypoint must be a JSON object")
    require_fields(claim_index, entrypoint_shapes.get("claims", []), "claims entrypoint", non_empty=True)
    require_fields(case_index, entrypoint_shapes.get("cases", []), "cases entrypoint", non_empty=True)

    schema_version = manifest.get("schemaVersion")
    require(schema_version, "manifest schemaVersion is required")
    require(contract.get("schemaVersion") == schema_version, "contract schemaVersion mismatch")
    require(claim_index.get("schemaVersion") == schema_version, "claim index schemaVersion mismatch")
    require(case_index.get("schemaVersion") == schema_version, "case index schemaVersion mismatch")

    proof_levels = set(contract.get("proofLevels", {}))
    validation_levels = set(contract.get("validationLevels", {}))
    provenance_classes = set(contract.get("provenanceClasses", {}))
    fixture_statuses = set(contract.get("fixtureStatuses", []))
    maturity_requirements = contract.get("validationMaturityRequirements", {})
    invocation_contract = contract.get("reproductionInvocationContract", {})
    evidence_contract = contract.get("validationEvidenceContract", {})
    required_claim_fields = contract.get("requiredClaimFields", [])
    required_case_fields = contract.get("requiredCaseFields", [])

    require(validation_levels == set(maturity_requirements), "every validation level must have exactly one maturity requirement")
    require(bool(fixture_statuses), "fixtureStatuses must be non-empty")
    require(isinstance(invocation_contract, dict) and bool(invocation_contract), "reproductionInvocationContract required")
    require(isinstance(evidence_contract, dict) and bool(evidence_contract), "validationEvidenceContract required")

    claims = claim_index.get("claims", [])
    require(isinstance(claims, list) and bool(claims), "claim index must contain at least one claim")
    claim_ids = [item.get("id") for item in claims if isinstance(item, dict)]
    require(len(claim_ids) == len(claims), "every claim must be an object")
    require(all(isinstance(item, str) and item.strip() for item in claim_ids), "claim ids must be non-empty strings")
    require(len(claim_ids) == len(set(claim_ids)), "claim ids must be unique")
    claims_by_id = {item["id"]: item for item in claims}

    case_entries = case_index.get("cases", [])
    require(isinstance(case_entries, list) and bool(case_entries), "case index must contain at least one case")
    case_ids = [item.get("id") for item in case_entries if isinstance(item, dict)]
    require(len(case_ids) == len(case_entries), "every case index entry must be an object")
    require(all(isinstance(item, str) and item.strip() for item in case_ids), "case ids must be non-empty strings")
    require(len(case_ids) == len(set(case_ids)), "case ids must be unique")

    cases = {}
    for entry in case_entries:
        require_fields(entry, ["id", "path", "status"], f"case index entry {entry.get('id')}", non_empty=True)
        case = load_json_ref(entry["path"], f"case {entry.get('id')}")
        require(isinstance(case, dict), f"case must be an object: {entry.get('id')}")
        require(case.get("id") == entry.get("id"), f"case index mismatch: {entry.get('id')}")
        require(case.get("schemaVersion") == schema_version, f"case schemaVersion mismatch: {entry.get('id')}")
        cases[case["id"]] = case

    for claim in claims:
        claim_id = claim["id"]
        require_fields(claim, required_claim_fields, f"claim {claim_id}")
        require(isinstance(claim.get("statement"), str) and claim["statement"].strip(), f"claim statement required: {claim_id}")
        require(claim.get("proofLevel") in proof_levels, f"unknown proof level: {claim_id}")
        require(bool(claim.get("limitations")), f"claim limitations required: {claim_id}")
        require(bool(claim.get("caseRefs")), f"claim must reference at least one case: {claim_id}")
        for ref in claim["caseRefs"]:
            require(ref in cases, f"claim references missing case: {ref}")
            require(claim_id in cases[ref].get("claimRefs", []), f"claim/case backlink missing: {claim_id} -> {ref}")

    for case_id, case in cases.items():
        require_fields(case, required_case_fields, f"case {case_id}")
        require(isinstance(case.get("title"), str) and case["title"].strip(), f"case title required: {case_id}")
        require(bool(case.get("claimRefs")), f"case must reference at least one claim: {case_id}")
        require(bool(case.get("failurePattern")), f"failurePattern required: {case_id}")
        require(bool(case.get("designResponse")), f"designResponse required: {case_id}")
        require(bool(case.get("limitations")), f"case limitations required: {case_id}")

        origin = case.get("origin", {})
        origin_class = origin.get("class")
        require(origin_class in provenance_classes, f"unknown provenance class: {case_id}")
        if origin_class == "derived_private_source":
            require(origin.get("sourceDisclosure") == "opaque_private", f"private-derived case must keep source opaque: {case_id}")
            require("sourceUrl" not in origin, f"private source URL leaked: {case_id}")

        fixture = case.get("publicFixture", {})
        require(isinstance(fixture, dict), f"publicFixture must be an object: {case_id}")
        require(fixture.get("class") in provenance_classes, f"unknown public fixture class: {case_id}")
        fixture_status = fixture.get("status")
        require(fixture_status in fixture_statuses, f"unknown public fixture status: {case_id}")
        if origin_class == "derived_private_source":
            require(fixture.get("productionCodeCopied") is False, f"private-derived fixture must not copy production code: {case_id}")

        validation = case.get("validation", {})
        require(isinstance(validation, dict), f"validation must be an object: {case_id}")
        validation_level = validation.get("level")
        require(validation_level in validation_levels, f"unknown validation level: {case_id}")
        maturity = maturity_requirements[validation_level]
        require(
            fixture_status in set(maturity.get("allowedFixtureStatuses", [])),
            f"validation level {validation_level} is not allowed for fixture status {fixture_status}: {case_id}",
        )
        require_fields(
            fixture,
            maturity.get("requiredFixtureFields", []),
            f"publicFixture maturity for {case_id}",
            non_empty=True,
        )
        require_fields(
            validation,
            maturity.get("requiredValidationFields", []),
            f"validation maturity for {case_id}",
            non_empty=True,
        )

        if maturity.get("requireExistingArtifactRefs") is True:
            artifact_refs = require_repo_file_refs(fixture.get("artifactRefs"), f"artifactRefs for {case_id}")
            if "entryArtifactRef" in fixture:
                require(fixture["entryArtifactRef"] in artifact_refs, f"entryArtifactRef must be in artifactRefs: {case_id}")

        if maturity.get("requireStructuredInvocation") is True:
            validate_reproduction_invocation(
                validation.get("reproductionInvocation"),
                fixture=fixture,
                invocation_contract=invocation_contract,
                case_id=case_id,
                label=f"validation reproductionInvocation for {case_id}",
            )

        if maturity.get("requirePassingEvidenceRefs") is True:
            validate_passing_evidence(
                case_id=case_id,
                validation_level=validation_level,
                fixture=fixture,
                validation=validation,
                evidence_contract=evidence_contract,
                invocation_contract=invocation_contract,
                schema_version=schema_version,
            )

        for ref in case["claimRefs"]:
            require(ref in claims_by_id, f"case references missing claim: {ref}")
            require(case_id in claims_by_id[ref].get("caseRefs", []), f"case/claim backlink missing: {case_id} -> {ref}")

    print(f"Showcase foundation validation: PASS ({len(claims)} claims, {len(cases)} cases)")


if __name__ == "__main__":
    main()
