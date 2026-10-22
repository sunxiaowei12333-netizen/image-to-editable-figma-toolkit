"""Validate an explicit scope without reinterpreting legacy audit counts."""


def validate_scope(data, errors, blockers):
    if "scope" not in data:
        return  # Legacy records retain their original validation semantics.
    scope = data["scope"]
    if not isinstance(scope, dict):
        errors.append("scope must be an object")
        return
    if scope.get("mode") not in {"current-visible", "explicit-expanded"}:
        errors.append("scope.mode must be current-visible or explicit-expanded")
    roots = scope.get("processingRootIds")
    if (not isinstance(roots, list) or not roots
            or any(not isinstance(x, str) or not x.strip() for x in roots)):
        errors.append("scope.processingRootIds must contain non-empty node ids")
    elif len(set(roots)) != len(roots):
        errors.append("scope.processingRootIds must be unique")
    if scope.get("mode") == "explicit-expanded":
        request = scope.get("requestedScope")
        if not isinstance(request, str) or not request.strip():
            errors.append("scope.requestedScope must describe the requested expansion")
    for key in ("dependencyCheckPassed", "excludedContentPreserved"):
        value = scope.get(key)
        if not isinstance(value, bool):
            errors.append(f"scope.{key} must be a boolean")
        elif not value:
            blockers.append(f"scope.{key} is false")
