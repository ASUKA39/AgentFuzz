#!/usr/bin/env python3
"""Create AgentFuzz's CodeQL inputs from a configured TypeScript target."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from build_target_image import ROOT, ensure_source


DEFAULT_QUERIES = [
    {
        "file": "ql/get_if.ql",
        "sarif": "if.sarif",
        "converter": "typescript-if",
        "output": "if.json",
    },
    {
        "file": "ql/get_callchain_and_location.ql",
        "sarif": "location.sarif",
        "converter": "typescript-callchain",
        "enter_hook": "enter_hook.json",
        "oracle": "oracle.json",
    },
    {
        "file": "ql/get_dataflow_str_constraint.ql",
        "sarif": "dsc.sarif",
        "converter": "typescript-dsc",
        "output": "dsc.json",
    },
]


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    analysis = config.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("config.analysis must be an object")
    codeql = str(analysis.get("codeql", "codeql"))
    pack_cache = analysis.get("pack_cache")
    if pack_cache:
        pack_cache = str(Path(str(pack_cache)).expanduser())
    language = analysis.get("language", "javascript")
    if language not in {"javascript", "typescript"}:
        raise ValueError("AgentFuzz TypeScript port requires analysis.language=javascript")
    queries = analysis.get("queries", DEFAULT_QUERIES)
    if not isinstance(queries, list) or not queries:
        raise ValueError("config.analysis.queries must be a non-empty list when overridden")

    for pack in analysis.get("packs", []):
        if analysis.get("download_packs", False):
            run([codeql, "pack", "download", str(pack)])

    source = ensure_source(config, ROOT / ".workspace" / "target-source")
    db = (ROOT / analysis.get("database", ".workspace/codeql/target")).resolve()
    output = (ROOT / analysis.get("output", ".workspace/static-analysis/target")).resolve()
    sarif_dir = output / "sarif"
    json_dir = output / "output"
    sarif_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    run([
        codeql, "database", "create", str(db),
        f"--language={language}", f"--source-root={source}", "--overwrite",
    ])

    for query in queries:
        if not isinstance(query, dict):
            raise ValueError("each config.analysis.queries entry must be an object")
        query_file = (ROOT / query["file"]).resolve()
        sarif = sarif_dir / query["sarif"]
        analyze = [
            codeql, "database", "analyze", str(db), str(query_file),
            "--rerun", "--format=sarif-latest", "--sarif-add-snippets",
            f"--max-paths={query.get('max_paths', 200)}", f"--output={sarif}",
        ]
        if pack_cache:
            analyze.append(f"--search-path={(ROOT / pack_cache).resolve() if not Path(pack_cache).is_absolute() else pack_cache}")
        run(analyze)

        converter = query.get("converter")
        if converter == "typescript-callchain":
            run([
                "node", str(ROOT / "ts" / "convert-sarif.mjs"), "--kind", "callchain",
                "--input", str(sarif), "--sourceRoot", str(source), "--enter", str(json_dir / query["enter_hook"]),
                "--oracle", str(json_dir / query["oracle"]),
            ])
        elif converter in {"typescript-if", "typescript-dsc"}:
            kind = converter.removeprefix("typescript-")
            run([
                "node", str(ROOT / "ts" / "convert-sarif.mjs"), "--kind", kind,
                "--input", str(sarif), "--sourceRoot", str(source), "--output", str(json_dir / query["output"]),
            ])
        elif converter:
            raise ValueError(f"unsupported converter: {converter}")

    print(f"Static analysis outputs: {output}")


if __name__ == "__main__":
    main()
