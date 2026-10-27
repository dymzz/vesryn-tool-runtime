#!/usr/bin/env python3
"""Check/apply repo-local Ruff and Pyright comment-suppression policy.

Copy to <repo>/scripts/ensure_comment_policy.py; no external Python packages.
Defaults to the parent of this scripts/ directory. Use --root for monorepos,
symlinks, or scripts stored outside the target repository.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

RUFF_REQUIRED = ("PGH003", "PGH004", "RUF100")
PYRIGHT_KEY = "reportUnnecessaryTypeIgnoreComment"
# Keep array-of-tables as boundaries too. We only edit ordinary named tables.
TABLE_HEADER = re.compile(r"(?m)^[ \t]*(\[{1,2})([^\r\n]+?)(\]{1,2})[ \t]*(?:\#[^\r\n]*)?$")


class UnsafeEdit(ValueError):
    """A configuration needs manual reconciliation to preserve its semantics."""


def newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def get_table(data: dict, name: str) -> dict:
    current = data
    for part in name.split("."):
        current = current.get(part, {}) if isinstance(current, dict) else {}
    return current if isinstance(current, dict) else {}


def table_bounds(text: str, name: str) -> tuple[int, int] | None:
    matches = [m for m in TABLE_HEADER.finditer(text) if len(m.group(1)) == len(m.group(3))]
    for index, header in enumerate(matches):
        if len(header.group(1)) == 1 and header.group(2).strip() == name:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return header.end(), end
    return None


def replace_key(text: str, table: str, key: str, value: str) -> str:
    """Edit one simple TOML assignment while leaving other data unchanged."""
    bounds = table_bounds(text, table)
    nl = newline(text)
    if bounds is None:
        return text.rstrip("\r\n") + nl * (2 if text.strip() else 0) + f"[{table}]" + nl + f"{key} = {value}" + nl
    begin, end = bounds
    region = text[begin:end]
    match = re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*", region)
    if match:
        start = begin + match.end()
        rest = text[start:end]
        same_line = rest.splitlines()[0] if rest else ""
        if same_line.strip().startswith("[") and "]" not in same_line:
            raise UnsafeEdit(f"{table}.{key} is a multiline array; handle through update_ruff")
        old_value = re.match(r"[^\r\n#]*", rest)
        if old_value is None:
            raise UnsafeEdit(f"Cannot locate scalar value for {table}.{key}")
        value_end = start + old_value.end()
        # Only simple same-line TOML literals are handled here.
        return text[:start] + value + text[value_end:]
    # Insert just after the table heading (including its newline).
    pos = begin
    if text.startswith("\r\n", pos):
        pos += 2
    elif text.startswith("\n", pos):
        pos += 1
    else:
        return text[:pos] + nl + f"{key} = {value}" + nl + text[pos:]
    return text[:pos] + f"{key} = {value}" + nl + text[pos:]


def rule_matches(selector: str, rule: str) -> bool:
    return selector.upper() == "ALL" or rule.startswith(selector.upper())


def update_ruff(text: str, table: str) -> tuple[str, list[str]]:
    data = tomllib.loads(text)
    lint = get_table(data, table)
    selected = lint.get("extend-select", [])
    extra = lint.get("select", [])
    ignored = lint.get("ignore", [])
    ignored_extra = lint.get("extend-ignore", [])
    for label, entries in (("extend-select", selected), ("select", extra), ("ignore", ignored), ("extend-ignore", ignored_extra)):
        if not isinstance(entries, list) or any(not isinstance(s, str) for s in entries):
            raise UnsafeEdit(f"{table}.{label} must be a list of rule names")
    for rule in RUFF_REQUIRED:
        if any(rule_matches(selector, rule) for selector in [*ignored, *ignored_extra]):
            raise UnsafeEdit(f"{table}: {rule} is explicitly ignored; resolve the conflict first")
    for setting in ("per-file-ignores", "extend-per-file-ignores"):
        value = lint.get(setting, {})
        if not isinstance(value, dict):
            raise UnsafeEdit(f"{table}.{setting} must be a table")
        if any(rule_matches(sel, rule) for codes in value.values() for sel in codes for rule in RUFF_REQUIRED):
            raise UnsafeEdit(f"{table}.{setting} suppresses a required rule; resolve the exception manually")
    missing = [r for r in RUFF_REQUIRED if not any(rule_matches(sel, r) for sel in [*selected, *extra])]
    if not missing:
        return text, []
    desired = [*selected, *missing]
    bounds = table_bounds(text, table)
    if bounds:
        region = text[bounds[0]:bounds[1]]
        m = re.search(r"(?m)^[ \t]*extend-select[ \t]*=[ \t]*(.*)$", region)
        if m and m.group(1).strip().startswith("[") and "]" not in m.group(1):
            # Common TOML multiline string-list form; safely preserve comments.
            after = bounds[0] + m.end()
            closing = re.search(r"(?m)^([ \t]*)\][ \t]*(?:\#[^\r\n]*)?$", text[after:bounds[1]])
            if not closing:
                raise UnsafeEdit(f"{table}.extend-select has an unsupported multiline format")
            close_start = after + closing.start()
            interior = text[after:close_start]
            rows = interior.splitlines(keepends=True)
            non_comment = [i for i, row in enumerate(rows) if row.strip() and not row.lstrip().startswith("#")]
            if non_comment:
                last = non_comment[-1]
                row = rows[last]
                # A missing comma must be added to the preceding string item.
                parts = re.match(r'([ \t]*"[^"\r\n]*")(,?)([ \t]*(?:\#[^\r\n]*)?)(\r?\n)?$', row)
                if not parts:
                    raise UnsafeEdit(f"{table}.extend-select needs manual editing (complex multiline item)")
                if not parts.group(2):
                    rows[last] = parts.group(1) + "," + parts.group(3) + (parts.group(4) or "")
            indent = re.search(r'(?m)^([ \t]+)"', interior)
            item_indent = indent.group(1) if indent else "    "
            content = "".join(rows)
            if content and not content.endswith(("\n", "\r")):
                content += newline(text)
            append = "".join(f'{item_indent}"{rule}",{newline(text)}' for rule in missing)
            updated = text[:after] + content + append + text[close_start:]
            tomllib.loads(updated)
            return updated, missing
    updated = replace_key(text, table, "extend-select", json.dumps(desired))
    tomllib.loads(updated)
    return updated, missing


def update_pyright_toml(text: str) -> tuple[str, list[str]]:
    settings = get_table(tomllib.loads(text), "tool.pyright")
    old = settings.get(PYRIGHT_KEY)
    if old is True or old in ("warning", "error"):
        return text, []
    if PYRIGHT_KEY in settings:
        raise UnsafeEdit(f"tool.pyright.{PYRIGHT_KEY} is explicitly {old!r}; reconcile before applying")
    updated = replace_key(text, "tool.pyright", PYRIGHT_KEY, '"warning"')
    tomllib.loads(updated)
    return updated, [PYRIGHT_KEY]


def update_pyright_json(text: str) -> tuple[str, list[str]]:
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UnsafeEdit("pyrightconfig.json is not strict JSON; update this file manually") from exc
    if not isinstance(settings, dict):
        raise UnsafeEdit("pyrightconfig.json must contain an object")
    old = settings.get(PYRIGHT_KEY)
    if old is True or old in ("warning", "error"):
        return text, []
    if PYRIGHT_KEY in settings:
        raise UnsafeEdit(f"pyrightconfig.json: {PYRIGHT_KEY} is explicitly {old!r}; resolve the conflict")
    # Insert one property instead of reserializing and reformatting the file.
    close = text.rfind("}")
    nl = newline(text)
    line_start = text.rfind("\n", 0, close) + 1
    if line_start > 0 and not text[line_start:close].strip():
        before = text[:line_start]
        if settings:
            end = len(before.rstrip())
            before = before[:end] + "," + before[end:]
        indentation = re.search(r'(?m)^([ \t]+)"', text)
        indent = indentation.group(1) if indentation else "  "
        updated = before + f'{indent}"{PYRIGHT_KEY}": "warning"' + nl + text[line_start:]
    else:
        before = text[:close]
        sep = ", " if settings else ""
        updated = before.rstrip() + sep + f'"{PYRIGHT_KEY}": "warning"' + text[len(before.rstrip()):]
    json.loads(updated)
    return updated, [PYRIGHT_KEY]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="show missing settings without modifying files")
    modes.add_argument("--apply", action="store_true", help="safely insert missing settings")
    parser.add_argument("--root", type=Path, help="target repository/project directory; defaults to script/../..")
    args = parser.parse_args(argv)
    root = (args.root if args.root is not None else Path(__file__).resolve().parent.parent).resolve()
    if not root.is_dir():
        parser.error(f"project root does not exist: {root}")
    project = root / "pyproject.toml"
    if not any((root / name).exists() for name in (
        "pyproject.toml", "ruff.toml", ".ruff.toml", "pyrightconfig.json", ".git"
    )):
        parser.error(f"cannot confirm Python project root at {root}; use --root with the intended project")
    ruff = next((p for p in (root / ".ruff.toml", root / "ruff.toml", project) if p.is_file()), root / "ruff.toml")
    pyright = root / "pyrightconfig.json"
    if not pyright.is_file():
        pyright = project if project.is_file() else pyright
    ruff_table = "tool.ruff.lint" if ruff == project else "lint"
    print(f"Project root: {root}")
    print(f"Ruff config:  {ruff} ({'found' if ruff.is_file() else 'new'})")
    print(f"Pyright config: {pyright} ({'found' if pyright.is_file() else 'new'})")
    planned: dict[Path, str] = {}
    missing: dict[Path, list[str]] = {}
    try:
        for path, updater in ((ruff, lambda s: update_ruff(s, ruff_table)),
                              (pyright, update_pyright_json if pyright.suffix == ".json" else update_pyright_toml)):
            content = planned.get(path)
            if content is None:
                content = path.read_text(encoding="utf-8") if path.is_file() else ("{}\n" if path.suffix == ".json" else "")
            updated, needed = updater(content)
            if needed:
                missing.setdefault(path, []).extend(needed)
                planned[path] = updated
    except (UnsafeEdit, OSError, UnicodeError, tomllib.TOMLDecodeError, ValueError, TypeError) as exc:
        print(f"Cannot safely reconcile configuration: {exc}", file=sys.stderr)
        return 2
    if not missing:
        print("Comment policy: configured (no changes needed).")
        return 0
    for path, rules in missing.items():
        print(f"Rules not enabled in {path}: {', '.join(rules)}")
    if args.check:
        print("Use --apply to insert these settings; --check never modifies files.")
        return 1
    for path, content in planned.items():
        path.write_text(content, encoding="utf-8", newline="")
        print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
