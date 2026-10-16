#!/usr/bin/env python3
"""Index a Jenkins deployment attempt and its outcome in Elasticsearch."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MANIFEST_PATH = "release/kubernetes-manifests.yaml"


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def deployment_documents(manifest: str) -> dict[str, str]:
    documents = {}
    for document in re.split(r"(?m)^---\s*$", manifest):
        if not re.search(r"(?m)^kind:\s*Deployment\s*$", document):
            continue
        name = re.search(r"(?m)^metadata:\s*\n\s+name:\s*([A-Za-z0-9-]+)\s*$", document)
        if name:
            documents[name.group(1)] = document.strip()
    return documents


def manifest_at(revision: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{MANIFEST_PATH}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return None
    return result.stdout


def changed_services(commit: str) -> list[str]:
    current_text = manifest_at(commit)
    if current_text is None:
        return ["online-boutique"]

    previous_text = manifest_at(f"{commit}^")
    if previous_text is None:
        return sorted(deployment_documents(current_text)) or ["online-boutique"]

    previous = deployment_documents(previous_text)
    current = deployment_documents(current_text)
    changed = sorted(
        name
        for name in previous.keys() | current.keys()
        if previous.get(name) != current.get(name)
    )
    return changed or ["online-boutique"]


def main() -> None:
    endpoint = os.environ.get("ES_ENDPOINT", "").strip().rstrip("/")
    api_key = os.environ.get("ES_API_KEY", "").strip()
    commit = os.environ.get("GIT_COMMIT", "").strip()
    result = os.environ.get("DEPLOYMENT_RESULT", "").strip()
    if not endpoint or not api_key or not commit or not result:
        raise SystemExit("ES_ENDPOINT, ES_API_KEY, GIT_COMMIT, and DEPLOYMENT_RESULT must be set.")
    if not endpoint.startswith(("https://", "http://")):
        raise SystemExit("ES_ENDPOINT must be an HTTP or HTTPS URL.")

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit,
        "author": git("show", "-s", "--format=%an", commit),
        "service": changed_services(commit),
        "image_tag": commit[:12],
        "change": git("show", "-s", "--format=%s", commit),
        "outcome": result.lower(),
        "cluster": os.environ.get("EKS_CLUSTER_NAME", ""),
        "build_url": os.environ.get("BUILD_URL", ""),
    }
    request = Request(
        f"{endpoint}/jenkins-deployments/_doc",
        data=json.dumps(event).encode("utf-8"),
        headers={
            "Authorization": f"ApiKey {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        print(f"Elasticsearch rejected the deployment event: HTTP {error.code}: {details}", file=sys.stderr)
        raise SystemExit(1) from error

    print(f"Indexed deployment event {response_body.get('_id', '(no document id)')}.")


if __name__ == "__main__":
    main()
