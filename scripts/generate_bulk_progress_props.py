#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from widgets.bulk_progress_props import build_bulk_progress_schema

GENERATED_DIR = (
    REPO_ROOT / "gooey-gui" / "app" / "components" / "bulkProgress" / "generated"
)
SCHEMA_PATH = GENERATED_DIR / "bulk-progress-props.schema.json"
TYPES_PATH = GENERATED_DIR / "componentProps.d.ts"


def main() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    schema = build_bulk_progress_schema()
    SCHEMA_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    subprocess.run(
        [
            "npx",
            "json-schema-to-typescript",
            str(SCHEMA_PATH),
            "--output",
            str(TYPES_PATH),
            "--bannerComment",
            "/* Generated from widgets/bulk_progress_props.py. Do not edit manually. */",
        ],
        cwd=REPO_ROOT / "gooey-gui",
        check=True,
    )


if __name__ == "__main__":
    main()
