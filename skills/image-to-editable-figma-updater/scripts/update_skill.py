#!/usr/bin/env python3
"""Check and safely update image-to-editable-figma from a private GitHub repo."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


REPOSITORY = "sunxiaowei12333-netizen/image-to-editable-figma-toolkit"
REF = "main"
REMOTE_SKILL_PATH = "skills/image-to-editable-figma"
TARGET_SKILL_NAME = "image-to-editable-figma"
RELEASE_FILE = "release.json"
IGNORED_PARTS = {"node_modules", "__pycache__"}
IGNORED_RELATIVE_PATHS = {
    RELEASE_FILE,
    "tooling/.local-state.json",
    "tooling/package-lock.json",
    "tooling/npm-shrinkwrap.json",
    ".DS_Store",
}
CODEX_HOME_OVERRIDE: Path | None = None
SYSTEM_SKILLS_ROOT_OVERRIDE: Path | None = None


class UpdateError(RuntimeError):
    pass


def codex_home() -> Path:
    if CODEX_HOME_OVERRIDE is not None:
        return CODEX_HOME_OVERRIDE
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def system_skills_root() -> Path:
    if SYSTEM_SKILLS_ROOT_OVERRIDE is not None:
        return SYSTEM_SKILLS_ROOT_OVERRIDE
    override = os.environ.get("CODEX_SYSTEM_SKILLS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return codex_home() / "skills" / ".system"


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        output = result.stdout.strip()
        raise UpdateError(output or f"Command failed: {' '.join(command)}")
    return result


def ignored(relative: Path) -> bool:
    posix = relative.as_posix()
    if posix in IGNORED_RELATIVE_PATHS or relative.name.endswith(".pyc"):
        return True
    return any(part in IGNORED_PARTS for part in relative.parts)


def content_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if ignored(relative) or path.is_dir():
            continue
        if path.is_symlink():
            raise UpdateError(f"Symlinks are not allowed in a release: {relative.as_posix()}")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def load_release(skill_root: Path) -> dict[str, Any]:
    path = skill_root / RELEASE_FILE
    if not path.is_file():
        return {"version": None, "contentSha256": None, "changes": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UpdateError(f"Invalid {RELEASE_FILE}: {error}") from error
    if not isinstance(value, dict):
        raise UpdateError(f"Invalid {RELEASE_FILE}: expected an object")
    return value


def verify_release(skill_root: Path) -> tuple[dict[str, Any], str]:
    release = load_release(skill_root)
    version = release.get("version")
    expected = release.get("contentSha256")
    if not isinstance(version, str) or not version.strip():
        raise UpdateError("Remote release has no valid version.")
    if not isinstance(expected, str) or len(expected) != 64:
        raise UpdateError("Remote release has no valid contentSha256.")
    actual = content_hash(skill_root)
    if actual != expected:
        raise UpdateError(
            f"Remote release fingerprint mismatch: expected {expected}, got {actual}."
        )
    return release, actual


def download_latest(source_dir: str | None) -> tuple[Path, Path | None]:
    if source_dir:
        source = Path(source_dir).expanduser().resolve()
        if not (source / "SKILL.md").is_file():
            raise UpdateError(f"Test source is not a Skill: {source}")
        return source, None

    installer = system_skills_root() / "skill-installer" / "scripts" / "install-skill-from-github.py"
    if not installer.is_file():
        raise UpdateError(f"Codex skill installer not found: {installer}")
    temporary_root = Path(tempfile.mkdtemp(prefix="image-to-figma-update-check-"))
    destination = temporary_root / "skills"
    run(
        [
            sys.executable,
            str(installer),
            "--repo",
            REPOSITORY,
            "--path",
            REMOTE_SKILL_PATH,
            "--ref",
            REF,
            "--dest",
            str(destination),
        ]
    )
    return destination / TARGET_SKILL_NAME, temporary_root


def validate_skill(skill_root: Path) -> None:
    validator = system_skills_root() / "skill-creator" / "scripts" / "quick_validate.py"
    if validator.is_file():
        run([sys.executable, str(validator), str(skill_root)])

    node = shutil.which("node")
    for path in sorted((skill_root / "scripts").glob("*.mjs")):
        if not node:
            raise UpdateError("Node.js is required to validate the updated Skill.")
        run([node, "--check", str(path)])

    python_scripts = sorted((skill_root / "scripts").glob("*.py"))
    if python_scripts:
        run([sys.executable, "-m", "py_compile", *[str(path) for path in python_scripts]])
        for cache in skill_root.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)


def report(source_dir: str | None) -> dict[str, Any]:
    target = codex_home() / "skills" / TARGET_SKILL_NAME
    remote_root, temporary_root = download_latest(source_dir)
    try:
        remote_release, remote_hash = verify_release(remote_root)
        if not target.is_dir():
            return {
                "status": "not-installed",
                "repository": REPOSITORY,
                "currentVersion": None,
                "latestVersion": remote_release["version"],
                "latestHash": remote_hash,
                "changes": remote_release.get("changes", []),
                "requiresConfirmation": True,
            }

        local_release = load_release(target)
        local_hash = content_hash(target)
        local_expected = local_release.get("contentSha256")
        local_modified = not isinstance(local_expected, str) or local_hash != local_expected
        same_release = (
            local_release.get("version") == remote_release.get("version")
            and local_hash == remote_hash
        )
        if local_modified:
            status = "local-modified"
        elif same_release:
            status = "current"
        else:
            status = "update-available"
        return {
            "status": status,
            "repository": REPOSITORY,
            "currentVersion": local_release.get("version"),
            "latestVersion": remote_release["version"],
            "currentHash": local_hash,
            "latestHash": remote_hash,
            "localModified": local_modified,
            "changes": remote_release.get("changes", []),
            "requiresConfirmation": status != "current",
            "preserves": ["tooling/.local-state.json", "user task outputs", "browser profiles"],
        }
    finally:
        if temporary_root:
            shutil.rmtree(temporary_root, ignore_errors=True)


def package_json_equal(first: Path, second: Path) -> bool:
    a = first / "tooling" / "package.json"
    b = second / "tooling" / "package.json"
    return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()


def post_install_check(target: Path) -> dict[str, Any]:
    validate_skill(target)
    bootstrap = target / "scripts" / "bootstrap.mjs"
    node = shutil.which("node")
    if not bootstrap.is_file() or not node:
        raise UpdateError("Updated Skill cannot initialize its private Node dependencies.")
    run([node, str(bootstrap), "--ensure-hugeicons"], cwd=target)
    check = subprocess.run(
        [node, str(bootstrap), "--check"],
        cwd=str(target),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "bootstrapExitCode": check.returncode,
        "bootstrapOutput": check.stdout.strip(),
    }


def apply_update(
    confirm_version: str | None,
    allow_local_modifications: bool,
    source_dir: str | None,
) -> dict[str, Any]:
    if not confirm_version:
        raise UpdateError("--confirm-version is required for --apply.")

    home = codex_home()
    skills_root = home / "skills"
    target = skills_root / TARGET_SKILL_NAME
    remote_root, temporary_root = download_latest(source_dir)
    incoming = skills_root / f".{TARGET_SKILL_NAME}.incoming-{os.getpid()}"
    backup: Path | None = None
    moved_node_modules = False
    try:
        remote_release, remote_hash = verify_release(remote_root)
        if remote_release["version"] != confirm_version:
            raise UpdateError(
                f"Confirmed version {confirm_version} no longer matches remote version "
                f"{remote_release['version']}. Run --check again."
            )
        validate_skill(remote_root)

        if target.is_dir():
            local_release = load_release(target)
            local_hash = content_hash(target)
            local_expected = local_release.get("contentSha256")
            local_modified = not isinstance(local_expected, str) or local_hash != local_expected
            if local_modified and not allow_local_modifications:
                raise UpdateError(
                    "Local managed files differ from the installed release. "
                    "Re-run only after explicit approval with --allow-local-modifications."
                )

        skills_root.mkdir(parents=True, exist_ok=True)
        if incoming.exists():
            shutil.rmtree(incoming)
        shutil.copytree(remote_root, incoming)
        state_source = target / "tooling" / ".local-state.json"
        if state_source.is_file():
            state_target = incoming / "tooling" / ".local-state.json"
            state_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(state_source, state_target)

        if content_hash(incoming) != remote_hash:
            raise UpdateError("Incoming release changed while staging.")

        if target.exists():
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_root = home / "skill-backups" / TARGET_SKILL_NAME
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / f"{stamp}-{os.getpid()}"
            os.replace(target, backup)
        os.replace(incoming, target)

        if backup and package_json_equal(backup, target):
            old_modules = backup / "tooling" / "node_modules"
            new_modules = target / "tooling" / "node_modules"
            if old_modules.is_dir() and not new_modules.exists():
                new_modules.parent.mkdir(parents=True, exist_ok=True)
                os.replace(old_modules, new_modules)
                moved_node_modules = True

        try:
            environment = post_install_check(target)
        except Exception:
            if backup:
                if moved_node_modules:
                    modules = target / "tooling" / "node_modules"
                    original_modules = backup / "tooling" / "node_modules"
                    if modules.is_dir() and not original_modules.exists():
                        original_modules.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(modules, original_modules)
                shutil.rmtree(target, ignore_errors=True)
                os.replace(backup, target)
            else:
                shutil.rmtree(target, ignore_errors=True)
            raise

        return {
            "status": "updated",
            "version": remote_release["version"],
            "contentSha256": remote_hash,
            "backupPath": str(backup) if backup else None,
            "preservedLocalState": state_source.is_file(),
            "reusedNodeModules": moved_node_modules,
            "environment": environment,
            "nextStep": "Open a new Codex task before using the updated Skill.",
        }
    finally:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)
        if temporary_root:
            shutil.rmtree(temporary_root, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-version")
    parser.add_argument("--allow-local-modifications", action="store_true")
    parser.add_argument("--source-dir", help=argparse.SUPPRESS)
    parser.add_argument("--codex-home", help=argparse.SUPPRESS)
    parser.add_argument("--system-skills-root", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    global CODEX_HOME_OVERRIDE, SYSTEM_SKILLS_ROOT_OVERRIDE
    args = parse_args()
    if args.codex_home:
        CODEX_HOME_OVERRIDE = Path(args.codex_home).expanduser().resolve()
    if args.system_skills_root:
        SYSTEM_SKILLS_ROOT_OVERRIDE = Path(args.system_skills_root).expanduser().resolve()
    try:
        if args.check:
            result = report(args.source_dir)
        else:
            result = apply_update(
                args.confirm_version,
                args.allow_local_modifications,
                args.source_dir,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except UpdateError as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
