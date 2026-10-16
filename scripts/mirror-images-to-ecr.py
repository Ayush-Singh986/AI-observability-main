#!/usr/bin/env python3
"""Mirror the demo's public images to ECR and render its Kubernetes manifest."""

import os
import re
import subprocess
import sys
from pathlib import Path


def load_sources(path: Path) -> dict[str, str]:
    sources = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tag, source = line.split(maxsplit=1)
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: expected '<ecr-tag> <source-image>'") from error
        if tag in sources:
            raise ValueError(f"{path}:{line_number}: duplicate ECR tag {tag}")
        sources[tag] = source
    return sources


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: mirror-images-to-ecr.py <manifest> <rendered-manifest>")

    registry = os.environ.get("ECR_REGISTRY", "").strip().rstrip("/")
    if not registry:
        raise SystemExit("ECR_REGISTRY must be set to the AWS ECR registry hostname.")
    region = os.environ.get("AWS_REGION", "").strip()
    if not region:
        raise SystemExit("AWS_REGION must be set.")
    commit = os.environ.get("GIT_COMMIT", "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{12,40}", commit):
        raise SystemExit("GIT_COMMIT must contain at least 12 hexadecimal characters.")

    manifest_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    sources = load_sources(manifest_path.parent / "image-sources.txt")
    content = manifest_path.read_text(encoding="utf-8")
    template = re.compile(r"\$\{ECR_REGISTRY\}/online-boutique:([A-Za-z0-9_.-]+)")
    manifest_tags = set(template.findall(content))

    if not manifest_tags:
        raise SystemExit(f"No ECR image placeholders found in {manifest_path}.")
    if manifest_tags != set(sources):
        missing_sources = sorted(manifest_tags - set(sources))
        unused_sources = sorted(set(sources) - manifest_tags)
        raise SystemExit(
            "Manifest and image source map do not match. "
            f"Missing source entries: {missing_sources}; unused source entries: {unused_sources}"
        )

    for tag in sorted(manifest_tags):
        source_image = sources[tag]
        commit_tag = f"{tag}-{commit[:12]}"
        target_image = f"{registry}/online-boutique:{commit_tag}"
        existing_image = subprocess.run(
            [
                "aws",
                "ecr",
                "describe-images",
                "--region",
                region,
                "--repository-name",
                "online-boutique",
                "--image-ids",
                f"imageTag={commit_tag}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if existing_image.returncode and "ImageNotFoundException" not in existing_image.stderr:
            raise subprocess.CalledProcessError(
                existing_image.returncode,
                existing_image.args,
                output=existing_image.stdout,
                stderr=existing_image.stderr,
            )
        if existing_image.returncode == 0:
            print(f"Image already exists; reusing {target_image}")
            content = content.replace(
                f"${{ECR_REGISTRY}}/online-boutique:{tag}",
                target_image,
            )
            continue

        subprocess.run(["docker", "pull", source_image], check=True)
        subprocess.run(["docker", "tag", source_image, target_image], check=True)
        subprocess.run(["docker", "push", target_image], check=True)
        content = content.replace(
            f"${{ECR_REGISTRY}}/online-boutique:{tag}",
            target_image,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Rendered AWS manifest: {output_path}")


if __name__ == "__main__":
    main()
