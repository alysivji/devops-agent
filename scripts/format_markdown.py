#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    target_paths = _resolve_target_paths(argv[1:])
    for path in target_paths:
        path.write_text(_format_markdown(path.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


def _resolve_target_paths(raw_paths: list[str]) -> list[Path]:
    if raw_paths:
        return [Path(raw_path) for raw_path in raw_paths if raw_path.endswith(".md")]

    tracked_files = subprocess.run(
        ["git", "ls-files", "*.md"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in tracked_files.stdout.splitlines() if line]


def _format_markdown(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    index = 0
    in_fence = False

    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()

        if index == 0 and line == "---":
            _flush_paragraph(output, paragraph)
            output.append(line)
            index += 1
            while index < len(lines):
                output.append(lines[index])
                if lines[index] == "---":
                    index += 1
                    break
                index += 1
            continue

        if stripped.startswith("```") or stripped.startswith("~~~"):
            _flush_paragraph(output, paragraph)
            output.append(line.rstrip())
            in_fence = not in_fence
            index += 1
            continue

        if in_fence:
            output.append(line.rstrip())
            index += 1
            continue

        if not stripped:
            _flush_paragraph(output, paragraph)
            output.append("")
            index += 1
            continue

        if _is_structural_line(line, stripped):
            _flush_paragraph(output, paragraph)
            output.append(_format_structural_block(lines, index))
            index = _next_index(lines, index)
            continue

        paragraph.append(stripped.rstrip())
        index += 1

    _flush_paragraph(output, paragraph)
    return "\n".join(output) + "\n"


def _is_structural_line(line: str, stripped: str) -> bool:
    return (
        stripped.startswith("#")
        or stripped.startswith(">")
        or stripped.startswith("|")
        or stripped in {"---", "***", "___"}
        or line.startswith(("    ", "\t"))
        or (stripped.startswith("<") and stripped.endswith(">"))
        or _is_list_item(line)
    )


def _is_list_item(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith(("- ", "* ", "+ ")):
        return True
    marker, _, _ = stripped.partition(" ")
    return marker[:-1].isdigit() and marker.endswith(".")


def _format_structural_block(lines: list[str], start_index: int) -> str:
    line = lines[start_index]
    if not _is_list_item(line):
        return line.rstrip()

    indent = line[: len(line) - len(line.lstrip())]
    stripped = line.lstrip()
    marker, _, remainder = stripped.partition(" ")
    content = remainder.strip()
    index = start_index + 1

    while index < len(lines):
        next_line = lines[index]
        next_stripped = next_line.lstrip()
        if (
            not next_stripped
            or _is_structural_line(next_line, next_stripped)
            or next_line.startswith(("    ", "\t"))
        ):
            break
        content = f"{content} {next_stripped.strip()}"
        index += 1

    return f"{indent}{marker} {content}".rstrip()


def _next_index(lines: list[str], start_index: int) -> int:
    line = lines[start_index]
    if not _is_list_item(line):
        return start_index + 1

    index = start_index + 1
    while index < len(lines):
        next_line = lines[index]
        next_stripped = next_line.lstrip()
        if (
            not next_stripped
            or _is_structural_line(next_line, next_stripped)
            or next_line.startswith(("    ", "\t"))
        ):
            break
        index += 1
    return index


def _flush_paragraph(output: list[str], paragraph: list[str]) -> None:
    if paragraph:
        output.append(" ".join(paragraph))
        paragraph.clear()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
