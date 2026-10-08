from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def write_json(root: Path, relative: str, value) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_validator(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "validation/validate_showcase.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def isolated_repo() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory()
    target = Path(tmp.name) / "showcase"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", ".ai", "__pycache__", "*.pyc"),
    )
    return tmp, target


def expect_pass(name: str, mutate=None) -> None:
    tmp, target = isolated_repo()
    try:
        if mutate:
            mutate(target)
        result = run_validator(target)
        if result.returncode != 0:
            raise AssertionError(f"{name}: expected PASS, got {result.stdout}{result.stderr}")
    finally:
        tmp.cleanup()


def expect_fail(name: str, mutate) -> None:
    tmp, target = isolated_repo()
    try:
        mutate(target)
        result = run_validator(target)
        if result.returncode == 0:
            raise AssertionError(f"{name}: expected FAIL, validator passed")
    finally:
        tmp.cleanup()


def empty_entrypoints(root: Path) -> None:
    manifest = read_json(root, "showcase.json")
    manifest["entrypoints"] = {}
    write_json(root, "showcase.json", manifest)


def misbind_claims_entrypoint(root: Path) -> None:
    manifest = read_json(root, "showcase.json")
    manifest["entrypoints"]["claims"] = "README.md"
    write_json(root, "showcase.json", manifest)


def disconnect_graph(root: Path) -> None:
    claims = read_json(root, "claims/index.json")
    for claim in claims["claims"]:
        claim["caseRefs"] = []
    write_json(root, "claims/index.json", claims)

    cases = read_json(root, "cases/index.json")
    for entry in cases["cases"]:
        case = read_json(root, entry["path"])
        case["claimRefs"] = []
        write_json(root, entry["path"], case)


def missing_failure_pattern(root: Path) -> None:
    case = read_json(root, "cases/001-task-state-continuity/case.json")
    case.pop("failurePattern")
    write_json(root, "cases/001-task-state-continuity/case.json", case)


def break_backlink(root: Path) -> None:
    case = read_json(root, "cases/001-task-state-continuity/case.json")
    case["claimRefs"] = ["guard-composition-integrity"]
    write_json(root, "cases/001-task-state-continuity/case.json", case)


def unsupported_public_reproduction(root: Path) -> None:
    case_path = "cases/002-cross-guard-composition/case.json"
    case = read_json(root, case_path)
    case["publicFixture"]["status"] = "planned"
    case["validation"]["level"] = "public_reproduction"
    write_json(root, case_path, case)


def structured_invocation(artifact_ref: str) -> dict:
    return {
        "profile": "python_script",
        "runner": "python",
        "entryArtifactRef": artifact_ref,
        "args": [],
    }


def nonexistent_public_reproduction_refs(root: Path) -> None:
    artifact_ref = "fixtures/does-not-exist.py"
    invocation = structured_invocation(artifact_ref)
    case = read_json(root, "cases/001-task-state-continuity/case.json")
    case["publicFixture"].update(
        {
            "status": "executable",
            "artifactRefs": [artifact_ref],
            "entryArtifactRef": artifact_ref,
        }
    )
    case["validation"].update(
        {
            "level": "public_reproduction",
            "evidenceRefs": ["validation/does-not-exist.json"],
            "reproductionInvocation": invocation,
        }
    )
    write_json(root, "cases/001-task-state-continuity/case.json", case)


def evidence_artifact_mismatch(root: Path) -> None:
    artifact_ref = "fixtures/demo.py"
    (root / artifact_ref).parent.mkdir(parents=True, exist_ok=True)
    (root / artifact_ref).write_text("print('ok')\n", encoding="utf-8")
    invocation = structured_invocation(artifact_ref)

    case = read_json(root, "cases/001-task-state-continuity/case.json")
    case["publicFixture"].update(
        {
            "status": "executable",
            "artifactRefs": [artifact_ref],
            "entryArtifactRef": artifact_ref,
        }
    )
    case["validation"].update(
        {
            "level": "public_reproduction",
            "evidenceRefs": ["validation/demo-evidence.json"],
            "reproductionInvocation": invocation,
        }
    )
    write_json(root, "cases/001-task-state-continuity/case.json", case)
    write_json(
        root,
        "validation/demo-evidence.json",
        {
            "schemaVersion": "0.1.0",
            "caseId": "case-001-task-state-continuity",
            "validationLevel": "public_reproduction",
            "result": "pass",
            "artifactRefs": ["README.md"],
            "reproductionInvocation": invocation,
        },
    )


def shell_comment_string_cannot_bind_entry_artifact(root: Path) -> None:
    artifact_ref = "fixtures/demo.py"
    (root / artifact_ref).parent.mkdir(parents=True, exist_ok=True)
    (root / artifact_ref).write_text("print('ok')\n", encoding="utf-8")
    fake_command = f'python -c "print(123)" # {artifact_ref}'

    case = read_json(root, "cases/001-task-state-continuity/case.json")
    case["publicFixture"].update(
        {
            "status": "executable",
            "artifactRefs": [artifact_ref],
            "entryArtifactRef": artifact_ref,
        }
    )
    case["validation"].update(
        {
            "level": "public_reproduction",
            "evidenceRefs": ["validation/demo-evidence.json"],
            "reproductionInvocation": fake_command,
        }
    )
    write_json(root, "cases/001-task-state-continuity/case.json", case)
    write_json(
        root,
        "validation/demo-evidence.json",
        {
            "schemaVersion": "0.1.0",
            "caseId": "case-001-task-state-continuity",
            "validationLevel": "public_reproduction",
            "result": "pass",
            "artifactRefs": [artifact_ref],
            "reproductionInvocation": fake_command,
        },
    )


def valid_public_reproduction(root: Path) -> None:
    artifact_ref = "fixtures/demo.py"
    (root / artifact_ref).parent.mkdir(parents=True, exist_ok=True)
    (root / artifact_ref).write_text("print('ok')\n", encoding="utf-8")

    invocation = structured_invocation(artifact_ref)
    evidence_ref = "validation/demo-evidence.json"
    case = read_json(root, "cases/001-task-state-continuity/case.json")
    case["publicFixture"].update(
        {
            "status": "executable",
            "artifactRefs": [artifact_ref],
            "entryArtifactRef": artifact_ref,
        }
    )
    case["validation"].update(
        {
            "level": "public_reproduction",
            "evidenceRefs": [evidence_ref],
            "reproductionInvocation": invocation,
        }
    )
    write_json(root, "cases/001-task-state-continuity/case.json", case)
    write_json(
        root,
        evidence_ref,
        {
            "schemaVersion": "0.1.0",
            "caseId": "case-001-task-state-continuity",
            "validationLevel": "public_reproduction",
            "result": "pass",
            "artifactRefs": [artifact_ref],
            "reproductionInvocation": invocation,
        },
    )


def main() -> None:
    expect_pass("baseline")
    expect_pass("valid public reproduction contract", valid_public_reproduction)
    expect_fail("empty entrypoints", empty_entrypoints)
    expect_fail("misbound claims entrypoint", misbind_claims_entrypoint)
    expect_fail("disconnected claim/case graph", disconnect_graph)
    expect_fail("missing required case field", missing_failure_pattern)
    expect_fail("broken claim/case backlink", break_backlink)
    expect_fail("planned fixture cannot claim public reproduction", unsupported_public_reproduction)
    expect_fail("nonexistent public reproduction refs", nonexistent_public_reproduction_refs)
    expect_fail("validation evidence must match fixture artifacts", evidence_artifact_mismatch)
    expect_fail("shell comment string cannot bind entry artifact", shell_comment_string_cannot_bind_entry_artifact)
    print("Showcase validator regression tests: PASS (2 positive, 9 negative)")


if __name__ == "__main__":
    main()
