#!/usr/bin/env python3
"""Render the immutable ECR image into the incident-agent Kubernetes manifest."""

import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: render-incident-agent.py <template> <output>")
    image = os.environ.get("INCIDENT_AGENT_IMAGE", "").strip()
    if ".dkr.ecr." not in image or "/online-boutique:incident-agent-" not in image:
        raise SystemExit("INCIDENT_AGENT_IMAGE must be an AWS ECR image URI.")

    template = Path(sys.argv[1]).read_text(encoding="utf-8")
    placeholder = "${INCIDENT_AGENT_IMAGE}"
    if template.count(placeholder) != 1:
        raise SystemExit(f"Expected exactly one {placeholder} placeholder.")
    output = Path(sys.argv[2])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace(placeholder, image), encoding="utf-8")
    print(f"Rendered incident-agent manifest: {output}")


if __name__ == "__main__":
    main()
