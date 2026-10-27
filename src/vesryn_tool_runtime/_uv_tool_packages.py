"""Pinned requests and read-only uv tool inspection; no installer or state."""

import os
import re
import subprocess
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from .documents import decode


def normalize_with_packages(value, main_package):
    if value is None:
        return None
    if not isinstance(value, (tuple, list)):
        raise TypeError("additional packages must be a list or tuple of exact pins")
    main = canonicalize_name(main_package)
    pins = {}
    for item in value:
        if not isinstance(item, str):
            raise TypeError("additional packages require exact name==version pins")
        requirement = Requirement(item)
        specifiers = tuple(requirement.specifier)
        if (
            requirement.url
            or requirement.marker
            or requirement.extras
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            raise ValueError("additional packages require exact name==version pins")
        name = canonicalize_name(requirement.name)
        version = str(Version(specifiers[0].version))
        if name == main:
            raise ValueError("an additional package cannot override the main artifact")
        if name in pins and Version(pins[name]) != Version(version):
            raise ValueError("conflicting additional package versions")
        pins[name] = min(pins.get(name, version), version)
    return tuple(f"{name}=={pins[name]}" for name in sorted(pins))


_INSPECT = """import importlib.metadata as m, json, sys
print(json.dumps({"python": sys.executable, "prefix": sys.prefix,
"python_version": ".".join(map(str, sys.version_info[:3])),
"packages": [{"name": d.metadata["Name"], "version": d.version}
             for d in m.distributions()]}))
"""


def _run(argv, environ, runner):
    effective = dict(os.environ)
    effective.update(
        {key: value for key, value in environ.items() if value is not None}
    )
    result = runner(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=effective,
    )
    if len((result.stdout or "").encode()) > 2 * 1024 * 1024:
        raise ValueError("tool environment evidence exceeds 2 MiB")
    return result


def _entry_path(text):
    if Path(text).is_absolute():
        return text
    match = re.fullmatch(r"[^()]+ \((.+)\)", text)
    if match and Path(match[1]).is_absolute():
        return match[1]
    raise ValueError("unsupported uv entry path")


def inspect_uv_tool(uv, package, *, environ, runner):
    """Inspect uv 0.12.23's public list view and that environment's Python."""
    package = canonicalize_name(package)
    listed = _run(
        [
            uv,
            "--no-config",
            "--color",
            "never",
            "tool",
            "list",
            "--show-paths",
            "--show-with",
        ],
        environ,
        runner,
    )
    if listed.returncode != 0:
        raise ValueError("uv tool listing failed")
    pattern = re.compile(rf"{re.escape(package)} v(\S+)(?: \[with: (.*?)\])? \((.+)\)")
    selected = None
    entries = []
    in_selected = False
    for line in (listed.stdout or "").splitlines():
        if line.startswith("- "):
            if in_selected:
                entries.append(_entry_path(line[2:]))
            continue
        in_selected = False
        match = pattern.fullmatch(line)
        if match:
            if selected is not None:
                raise ValueError("duplicate uv tool record")
            selected = match
            in_selected = True
    if selected is None:
        return None
    version, requirements, location = selected.groups()
    Version(version)
    root = Path(location)
    if not root.is_absolute() or not entries:
        raise ValueError("uv tool environment has no absolute path or entries")
    pins = []
    for item in requirements.split(", ") if requirements else ():
        requirement = Requirement(item)
        if requirement.url or requirement.marker or requirement.extras:
            raise ValueError("unsupported uv additional requirement view")
        pins.append(canonicalize_name(requirement.name) + str(requirement.specifier))
    python = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    inspected = _run([str(python), "-I", "-B", "-c", _INSPECT], environ, runner)
    if inspected.returncode != 0:
        raise ValueError("tool environment interpreter inspection failed")
    facts = decode((inspected.stdout or "").encode())
    if set(facts) != {"python", "prefix", "python_version", "packages"}:
        raise ValueError("unsupported tool environment evidence")
    if not isinstance(facts["python"], str) or not isinstance(facts["prefix"], str):
        raise TypeError("missing tool interpreter identity")
    if (
        Path(facts["python"]).resolve() != python.resolve()
        or Path(facts["prefix"]).resolve() != root.resolve()
    ):
        raise ValueError("inspection came from another environment")
    Version(facts["python_version"])
    if not isinstance(facts["packages"], list):
        raise TypeError("missing installed distribution inventory")
    packages = {}
    for item in facts["packages"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "version"}
            or not all(isinstance(value, str) for value in item.values())
        ):
            raise ValueError("invalid installed distribution")
        name = canonicalize_name(item["name"], validate=True)
        Version(item["version"])
        if name in packages:
            raise ValueError("duplicate installed distribution")
        packages[name] = item["version"]
    if package not in packages or Version(packages[package]) != Version(version):
        raise ValueError("uv listing and actual main distribution disagree")
    checked = _run(
        [uv, "--no-config", "pip", "check", "--python", str(python)], environ, runner
    )
    facts.update(
        packages=[
            {"name": name, "version": packages[name]} for name in sorted(packages)
        ],
        with_packages=tuple(sorted(pins)),
        dependencies_consistent=checked.returncode == 0,
    )
    return {
        "package": package,
        "version": version,
        "entrypoints": tuple(entries),
        "environment": facts,
    }


def satisfies_request(observed, main_package, version, requested):
    """A matching request receipt AND actual installed packages are required."""
    facts = observed["environment"]
    installed = {item["name"]: item["version"] for item in facts["packages"]}
    requirements = (f"{main_package}=={version}", *requested)
    return (
        facts["with_packages"] == requested
        and facts["dependencies_consistent"]
        and all(
            canonicalize_name(req.name) in installed
            and req.specifier.contains(
                installed[canonicalize_name(req.name)], prereleases=True
            )
            for req in map(Requirement, requirements)
        )
    )
