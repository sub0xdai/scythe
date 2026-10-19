"""Append-only project memory.

Every successful render appends one block to <project>/project.md: what
was rendered, at what shape, and what evaluation measured. A later
session reads that file instead of guessing what the project already
contains.
"""

import datetime
import os

MEMORY_FILE = "project.md"

HEADER = """# project log

Append-only render history for this project. Each block is one render:
the shape it was built at, the outputs, and what evaluation measured.
"""


def _path(project_dir):
    return os.path.join(project_dir, MEMORY_FILE)


def _shape(config, timeline):
    width, height = config["resolution"]
    parts = [
        f"{width}x{height} @ {config['fps']}fps",
        f"theme {config.get('theme') or 'none'}",
        f"transitions {config.get('transition_mode', 'hard_cut')}",
        f"{len(timeline.video)} video track(s)",
        f"{len(timeline.audio)} audio track(s)",
    ]
    return ", ".join(parts)


def record(project_dir, *, outputs, duration, timeline, config,
           findings=(), note=None):
    """Append one render block to <project>/project.md. Returns the path."""
    path = _path(project_dir)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    lines = [
        f"## {stamp}",
        "",
        f"- outputs: {', '.join(os.path.basename(o) for o in outputs)}",
        f"- duration: {duration:.3f}s",
        f"- shape: {_shape(config, timeline)}",
        f"- evaluation: {len(errors)} error(s), {len(warnings)} warning(s)",
    ]
    for finding in findings:
        lines.append(f"  - {finding.severity} {finding.rule}: {finding.message}")
    if note:
        lines.append(f"- note: {note}")
    block = "\n".join(lines) + "\n"

    if not os.path.exists(path):
        body = HEADER + "\n" + block
    else:
        with open(path) as f:
            existing = f.read()
        body = existing.rstrip("\n") + "\n\n" + block
    with open(path, "w") as f:
        f.write(body)
    return path
