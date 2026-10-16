#!/usr/bin/env python3
"""Build and push the incident watcher image once per source commit."""

import os
import subprocess
import sys


def main() -> None:
    region = os.environ.get("AWS_REGION", "").strip()
    image = os.environ.get("INCIDENT_AGENT_IMAGE", "").strip()
    if not region or not image:
        raise SystemExit("AWS_REGION and INCIDENT_AGENT_IMAGE must be set.")

    existing = subprocess.run(
        [
            "aws",
            "ecr",
            "describe-images",
            "--region",
            region,
            "--repository-name",
            "online-boutique",
            "--image-ids",
            f"imageTag={image.rsplit(':', maxsplit=1)[-1]}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if existing.returncode == 0:
        print(f"Incident agent image already exists; reusing {image}")
        return
    if "ImageNotFoundException" not in existing.stderr:
        print(existing.stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(
            existing.returncode,
            existing.args,
            output=existing.stdout,
            stderr=existing.stderr,
        )

    subprocess.run(
        ["docker", "build", "--file", "incident-agent/Dockerfile", "--tag", image, "."],
        check=True,
    )
    subprocess.run(["docker", "push", image], check=True)


if __name__ == "__main__":
    main()
