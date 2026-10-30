#!/usr/bin/env python3
"""CI smoke check: the agent skill/plugin resources survive sdist -> wheel packaging.

Builds the sdist and the wheel built from it with ``uv build`` (UI compile skipped via
``EMERGENTFLOW_SKIP_UI_BUILD``), asserts the expected agent resources are present in each
archive, then imports the extracted wheel from outside the checkout and exercises the
packaged agent prompt path. Stdlib only. Exit 0 on success, 1 on any missing resource.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SDIST_REQUIRED = (
    "agents/SKILL.md",
    "agents/_reply-contract.md",
    "agents/.mcp.json",
    "agents/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
)

WHEEL_REQUIRED = (
    "emergentflow/collab/reply_contract.py",
    "emergentflow/agents/SKILL.md",
    "emergentflow/agents/_reply-contract.md",
    "emergentflow/agents/emergent-flow-collaborator.md",
    "emergentflow/agents/data-modeller.md",
    "emergentflow/agents/data-scientist.md",
    "emergentflow/agents/researcher.md",
    "emergentflow/agents/ml-engineer.md",
    "emergentflow/agents/emergent-flow-experimenter.md",
    "emergentflow/agents/.mcp.json",
    "emergentflow/agents/.claude-plugin/plugin.json",
)

# Runs in a child interpreter whose PYTHONPATH points at the extracted wheel, with cwd outside
# the repo, so the import resolves to the packaged copy rather than the source tree.
PROBE = r"""
import pathlib, re, sys
import emergentflow
from emergentflow.collab import chat_runner
from emergentflow.collab.reply_contract import REPLY_CONTRACT
site = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(emergentflow.__file__).resolve().is_relative_to(site), emergentflow.__file__
agents = chat_runner._AGENTS_DIR.resolve()
assert agents == site / "emergentflow" / "agents", agents
for md in agents.glob("*.md"):
    for target in re.findall(r"\]\((\.{1,2}/[^)#\s]+)", md.read_text(encoding="utf-8")):
        resolved = (agents / target).resolve()
        assert resolved.is_file() and resolved.is_relative_to(agents), (md.name, target)
prompt = chat_runner._build_first_turn_prompt(
    session_id="s", base_url="http://x", auth_token=None, user_message="hi",
    persona_filename="data-scientist.md",
)
assert REPLY_CONTRACT in prompt and "Emergent Flow Collaborator" in prompt
assert "## Your persona" in prompt and "Data Scientist" in prompt
print("packaged agents OK")
"""


def _only(entries: list[Path], pattern: str) -> Path:
    matches = sorted(p for p in entries if p.match(pattern))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {pattern} in dist/, found {matches}")
    return matches[0]


def _check_sdist(sdist: Path) -> list[str]:
    with tarfile.open(sdist, "r:gz") as tar:
        names = set()
        for member in tar.getnames():
            parts = member.split("/", 1)
            if len(parts) == 2:
                names.add(parts[1])
    return [req for req in SDIST_REQUIRED if req not in names]


def _check_wheel(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    return [req for req in WHEEL_REQUIRED if req not in names]


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        dist = tmp / "dist"
        subprocess.run(
            ["uv", "build", "--out-dir", str(dist)],
            cwd=REPO,
            check=True,
            env={**os.environ, "EMERGENTFLOW_SKIP_UI_BUILD": "1"},
        )
        entries = list(dist.iterdir())
        sdist = _only(entries, "*.tar.gz")
        wheel = _only(entries, "*.whl")

        failures: list[str] = []
        missing_sdist = _check_sdist(sdist)
        if missing_sdist:
            failures.extend(f"sdist {sdist.name}: missing {name}" for name in missing_sdist)
        else:
            print(f"sdist {sdist.name}: agent resources present")

        missing_wheel = _check_wheel(wheel)
        if missing_wheel:
            failures.extend(f"wheel {wheel.name}: missing {name}" for name in missing_wheel)
        else:
            print(f"wheel {wheel.name}: agent resources present")

        if failures:
            for line in failures:
                print(line, file=sys.stderr)
            return 1

        site = tmp / "site"
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(site)
        probe = subprocess.run(
            [sys.executable, "-c", PROBE, str(site)],
            cwd=tmp,
            env={**os.environ, "PYTHONPATH": str(site)},
            check=False,
        )
        if probe.returncode != 0:
            print("packaged agent import probe failed.", file=sys.stderr)
            return 1
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
