#!/usr/bin/env python3
"""Build a target image from AgentFuzz's target configuration.

The script keeps the AgentFuzz image independent of any target repository.
It fixes the target source at the configured commit, creates a temporary
Docker build context under ``.workspace``, and lets the target Dockerfile
read the build commands from a generated JSON file.  A target-specific
``build_script`` may be configured when shell commands are insufficient.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print('+', ' '.join(command))
    subprocess.run(command, cwd=cwd, check=True)


def load_config(path: Path) -> dict:
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def safe_tag(target_name: str) -> str:
    value = re.sub(r'[^a-zA-Z0-9_.-]+', '-', target_name).lower().strip('-')
    return value or 'target'


def ensure_source(config: dict, source_root: Path) -> Path:
    target_name = config['target_name']
    source = source_root / target_name
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '--branch', config['ref'], '--depth', '1', config['repo_url'], str(source)])

    expected = config.get('expected_commit')
    if expected:
        actual = subprocess.check_output(
            ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True,
        ).strip()
        if actual != expected:
            run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', expected])
            run(['git', '-C', str(source), 'checkout', '--quiet', expected])
            actual = subprocess.check_output(
                ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True,
            ).strip()
        if actual != expected:
            raise RuntimeError(f'expected commit {expected}, got {actual}')
    return source


def create_context(source: Path, context: Path, target_config: dict) -> None:
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True)
    shutil.copytree(
        source, context, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.pytest_cache'),
    )
    dockerfile = ROOT / target_config.get('dockerfile', 'targets/default.Dockerfile')
    if not dockerfile.is_file():
        raise FileNotFoundError(f'target Dockerfile not found: {dockerfile}')
    shutil.copy2(dockerfile, context / 'Dockerfile')

    build_script = target_config.get('build_script')
    script_name = None
    if build_script:
        script_path = (ROOT / build_script).resolve()
        if ROOT not in script_path.parents:
            raise ValueError('target build_script must be inside the AgentFuzz repository')
        if not script_path.is_file():
            raise FileNotFoundError(f'target build script not found: {script_path}')
        script_name = script_path.name
        shutil.copy2(script_path, context / script_name)

    instrumentation = target_config.get('instrumentation')
    instrumentation_config = None
    if instrumentation:
        if not isinstance(instrumentation, dict):
            raise ValueError('target.instrumentation must be an object')
        script = instrumentation.get('script')
        rules_dir = instrumentation.get('rules_dir')
        if not script or not rules_dir:
            raise ValueError('target.instrumentation requires script and rules_dir')
        script_path = (ROOT / script).resolve()
        rules_path = (ROOT / rules_dir).resolve()
        if ROOT not in script_path.parents or not script_path.is_file():
            raise FileNotFoundError(f'instrumentation script not found: {script_path}')
        if ROOT not in rules_path.parents or not rules_path.is_dir():
            raise FileNotFoundError(f'instrumentation rules directory not found: {rules_path}')
        instrumentation_root = context / '.agentfuzz'
        (instrumentation_root / 'rules').mkdir(parents=True)
        shutil.copy2(script_path, instrumentation_root / 'instrument.sh')
        trace_path = ROOT / 'trace' / 'runtime.mjs'
        trace_name = 'runtime.mjs'
        instrument_path = ROOT / 'ts' / 'instrument.mjs'
        if not trace_path.is_file():
            raise FileNotFoundError(f'AgentFuzz tracer not found: {trace_path}')
        shutil.copy2(trace_path, instrumentation_root / trace_name)
        if instrument_path:
            if not instrument_path.is_file():
                raise FileNotFoundError(f'AgentFuzz instrumenter not found: {instrument_path}')
            shutil.copy2(instrument_path, instrumentation_root / 'instrument.mjs')
        for rule_file in rules_path.glob('*.json'):
            shutil.copy2(rule_file, instrumentation_root / 'rules' / rule_file.name)
        instrumentation_config = {
            'startup_delay': instrumentation.get('startup_delay', 40),
            'language': 'javascript',
        }
        (instrumentation_root / 'instrumentation.json').write_text(
            json.dumps(instrumentation_config, indent=2) + '\n',
            encoding='utf-8',
        )

    generated = {
        'install_command': target_config.get('install_command'),
        'build_command': target_config.get('build_command'),
        'build_script': script_name,
        'instrumentation': instrumentation_config,
    }
    (context / '.target-build-config.json').write_text(
        json.dumps(generated, indent=2) + '\n', encoding='utf-8',
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    parser.add_argument('--tag', help='Docker image tag; defaults to agentfuzz-target:<target_name>')
    args = parser.parse_args()

    config = load_config(args.config.resolve())
    target_config = config.get('target')
    if not isinstance(target_config, dict):
        raise ValueError('config.target must be an object')
    source = ensure_source(config, ROOT / '.workspace' / 'target-source')
    context = ROOT / '.workspace' / 'target-build' / config['target_name']
    language = config.get('analysis', {}).get('language', 'javascript')
    if language not in {'javascript', 'typescript'}:
        raise ValueError('AgentFuzz TypeScript port requires analysis.language=javascript')
    create_context(source, context, target_config)

    tag = args.tag or f"agentfuzz-target:{safe_tag(config['target_name'])}"
    command = [
        'docker', 'build', '--platform', 'linux/amd64',
        '--build-arg', f"NODE_VERSION={target_config.get('node_version', '20')}",
        '-t', tag, '-f', str(context / 'Dockerfile'), str(context),
    ]
    run(command)
    print(f'Built target image: {tag}')


if __name__ == '__main__':
    main()
