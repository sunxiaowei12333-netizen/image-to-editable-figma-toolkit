#!/usr/bin/env python3
"""Record timing, single-pass pipeline attempts, and independent visual review."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROFILES = {"cold-start", "warm-reuse"}
MODES = {"delivery", "rule-regression", "fresh-generation-stability"}
STAGES = {
    "resource-preflight",
    "capture-build",
    "html-preflight",
    "composition-check",
    "browser-preview",
    "approval-fingerprint",
}
MARKS = {"generationFinishedAt", "firstPreviewAt", "htmlReadyAt", "handoffReadyAt"}
VISUAL_STATUSES = {"pending", "passed", "warning", "failed"}
TECHNICAL_STATUSES = {"pending", "passed", "failed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_record(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("delivery record root must be an object")
    return value


def write_record(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 string") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def validate_record(record: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    if record.get("testMode") not in MODES:
        errors.append(f"testMode must be one of {sorted(MODES)}")
    if record.get("executionProfile") not in PROFILES:
        errors.append(f"executionProfile must be one of {sorted(PROFILES)}")
    try:
        started = parse_time(record.get("startedAt"), "startedAt")
    except ValueError as exc:
        errors.append(str(exc))
        started = None

    if "visualStatus" in record:
        errors.append("visualStatus is forbidden at the record root; use visualReview.status")
    visual = record.get("visualReview")
    if not isinstance(visual, dict) or visual.get("status") not in VISUAL_STATUSES:
        errors.append(f"visualReview.status must be one of {sorted(VISUAL_STATUSES)}")
    technical = record.get("technicalStatus")
    if not isinstance(technical, dict) or technical.get("status") not in TECHNICAL_STATUSES:
        errors.append(f"technicalStatus.status must be one of {sorted(TECHNICAL_STATUSES)}")

    attempts = record.get("pipelineAttempts")
    if not isinstance(attempts, list):
        errors.append("pipelineAttempts must be an array")
        attempts = []
    passed_by_stage = {stage: 0 for stage in STAGES}
    for index, attempt in enumerate(attempts):
        label = f"pipelineAttempts[{index}]"
        if not isinstance(attempt, dict):
            errors.append(f"{label} must be an object")
            continue
        stage = attempt.get("stage")
        status = attempt.get("status")
        if stage not in STAGES:
            errors.append(f"{label}.stage must be one of {sorted(STAGES)}")
        if status not in {"passed", "failed"}:
            errors.append(f"{label}.status must be passed or failed")
        if status == "failed" and not str(attempt.get("reason", "")).strip():
            errors.append(f"{label}.reason is required for a failed retry")
        evidence_path = attempt.get("evidencePath")
        if status == "passed":
            if not isinstance(evidence_path, str) or not Path(evidence_path).is_file():
                errors.append(f"{label}.evidencePath must exist for a passed stage")
            if stage in passed_by_stage:
                passed_by_stage[stage] += 1
    for stage, count in passed_by_stage.items():
        if count != 1:
            errors.append(f"pipeline stage {stage!r} must have exactly one passed attempt, found {count}")

    for mark in sorted(MARKS):
        if mark in record:
            try:
                parse_time(record[mark], mark)
            except ValueError as exc:
                errors.append(str(exc))
    if record.get("generationFinishedAt") and record.get("firstPreviewAt"):
        try:
            generation_finished = parse_time(record["generationFinishedAt"], "generationFinishedAt")
            first_preview = parse_time(record["firstPreviewAt"], "firstPreviewAt")
            delay = (first_preview - generation_finished).total_seconds()
            if delay < 0:
                errors.append("firstPreviewAt must not precede generationFinishedAt")
            elif delay > 240:
                errors.append(
                    f"generation-to-first-preview gate exceeded: {delay:.1f}s > 240s"
                )
        except ValueError:
            pass
    if started is not None and record.get("handoffReadyAt"):
        try:
            if parse_time(record["handoffReadyAt"], "handoffReadyAt") < started:
                errors.append("handoffReadyAt must not precede startedAt")
        except ValueError:
            pass

    if isinstance(technical, dict) and technical.get("status") == "passed":
        if any(count != 1 for count in passed_by_stage.values()):
            errors.append("technicalStatus cannot be passed before every final pipeline stage passes once")
    if isinstance(visual, dict) and visual.get("status") in {"passed", "warning", "failed"}:
        evidence_path = visual.get("evidencePath")
        if not isinstance(evidence_path, str) or not Path(evidence_path).is_file():
            errors.append("visualReview.evidencePath must exist when visual review is not pending")
        if not str(visual.get("note", "")).strip():
            errors.append("visualReview.note is required when visual review is not pending")
        if record.get("recordVersion", 1) >= 2:
            for field, hash_field in (("referencePath", "referenceSha256"), ("evidencePath", "evidenceSha256")):
                value = visual.get(field)
                if not isinstance(value, str) or not Path(value).is_file():
                    errors.append(f"visualReview.{field} must name an existing file")
                elif visual.get(hash_field) != file_hash(Path(value)):
                    errors.append(f"visualReview.{hash_field} does not match the reviewed file; review again")
    if isinstance(technical, dict) and technical.get("status") == "passed" and isinstance(visual, dict):
        if visual.get("status") == "pending":
            warnings.append("technical checks passed, but visual review is still pending")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("record", type=Path)
    init.add_argument("--mode", choices=sorted(MODES), default="delivery")
    init.add_argument("--profile", choices=sorted(PROFILES), default="cold-start")
    mark = sub.add_parser("mark")
    mark.add_argument("record", type=Path)
    mark.add_argument("name", choices=sorted(MARKS))
    attempt = sub.add_parser("attempt")
    attempt.add_argument("record", type=Path)
    attempt.add_argument("--stage", choices=sorted(STAGES), required=True)
    attempt.add_argument("--status", choices=("passed", "failed"), required=True)
    attempt.add_argument("--evidence", type=Path)
    attempt.add_argument("--reason", default="")
    technical = sub.add_parser("technical")
    technical.add_argument("record", type=Path)
    technical.add_argument("--status", choices=sorted(TECHNICAL_STATUSES), required=True)
    technical.add_argument("--note", default="")
    review = sub.add_parser("review")
    review.add_argument("record", type=Path)
    review.add_argument("--status", choices=sorted(VISUAL_STATUSES), required=True)
    review.add_argument("--evidence", type=Path)
    review.add_argument("--reference", type=Path, help="Original reference used for the visual comparison")
    review.add_argument("--note", default="")
    validate = sub.add_parser("validate")
    validate.add_argument("record", type=Path)
    args = parser.parse_args()

    try:
        path = args.record.expanduser().resolve()
        if args.command == "init":
            record = {
                "recordVersion": 2,
                "testMode": args.mode,
                "executionProfile": args.profile,
                "startedAt": now_iso(),
                "technicalStatus": {"status": "pending", "note": ""},
                "visualReview": {"status": "pending", "note": ""},
                "pipelineAttempts": [],
            }
            with path.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            result = {"ok": True, "record": str(path), "startedAt": record["startedAt"]}
        elif args.command == "validate":
            result = validate_record(read_record(path))
            result["record"] = str(path)
        else:
            record = read_record(path)
            if args.command == "mark":
                record[args.name] = now_iso()
            elif args.command == "attempt":
                if args.status == "failed" and not args.reason.strip():
                    raise ValueError("--reason is required for a failed attempt")
                evidence = args.evidence.expanduser().resolve() if args.evidence else None
                if args.status == "passed" and (evidence is None or not evidence.is_file()):
                    raise ValueError("--evidence must name an existing file for a passed attempt")
                record.setdefault("pipelineAttempts", []).append(
                    {
                        "stage": args.stage,
                        "status": args.status,
                        "at": now_iso(),
                        "evidencePath": str(evidence) if evidence else None,
                        "reason": args.reason.strip(),
                    }
                )
            elif args.command == "technical":
                record["technicalStatus"] = {
                    "status": args.status,
                    "note": args.note.strip(),
                    "at": now_iso(),
                }
            elif args.command == "review":
                evidence = args.evidence.expanduser().resolve() if args.evidence else None
                reference = args.reference.expanduser().resolve() if args.reference else None
                if args.status != "pending" and (evidence is None or not evidence.is_file()):
                    raise ValueError("--evidence must name an existing file when visual review is not pending")
                if args.status != "pending" and not args.note.strip():
                    raise ValueError("--note is required when visual review is not pending")
                if record.get("recordVersion", 1) >= 2 and args.status != "pending":
                    if reference is None or not reference.is_file():
                        raise ValueError("--reference must name the original reference file; technical pass alone is not visual review")
                record["visualReview"] = {
                    "status": args.status,
                    "note": args.note.strip(),
                    "evidencePath": str(evidence) if evidence else None,
                    "referencePath": str(reference) if reference else None,
                    "referenceSha256": file_hash(reference) if reference and reference.is_file() else None,
                    "evidenceSha256": file_hash(evidence) if evidence and evidence.is_file() else None,
                    "at": now_iso(),
                }
            write_record(path, record)
            result = {"ok": True, "record": str(path), "command": args.command}
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
