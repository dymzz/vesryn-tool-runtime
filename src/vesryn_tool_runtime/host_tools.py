"""Host CLI preparation, local registration and the shared Agent tool list.

Issue #33 (TR-DISC-01C): make installed CLIs directly usable by an Agent
through the host shell — no Scope/Permission/Binding/Adapter detour. One
preparation entry checks the target shell first (reuse what already resolves
and matches; report conflicts honestly), installs what is missing through
the real backends (``uv tool install`` for Python CLIs; the existing aria2
verification chain for native binaries), and registers the outcome in ONE
operation that updates both local stores:

- ``<user data root>/vesryn/data/tools.sqlite3`` — registrations as ToolAsset
  rows plus host facts in ``tool_install`` (command, version, entry,
  description, prepared_via, reused, source_verified);
- ``<user data root>/vesryn/data/tools.json`` — the strict command/description
  list Agents read, regenerated from the registration facts.

Reading the packaged default list, importing this module and SessionStart do
nothing implicit: no registration, download or installation. Nothing here
modifies host PATH or user config; native PATH exposure stays a host-side
startup concern. External installs missing upstream verification evidence
are reused honestly with ``source_verified=0`` — the executable's own file
hash is never reported as a verified publisher digest.
"""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from importlib.resources import files as resource_files
from pathlib import Path

from .asset_index import AssetIndex, asset_root
from .assets import AssetPolicy, AssetTarget
from .discovery_records import ToolAsset
from .native_assets import Aria2NativeBackend, Aria2Source
from .record_sources import legacy_preparation_definitions
from .record_store import open_record_store

DEFAULT_TOOLS_RESOURCE = "default-tools.json"

PREPARE_STATUSES = ("reused", "installed", "conflict", "missing_release")
VIA_VALUES = ("uv", "aria2", "external")


class HostToolError(Exception):
    """A stable host-tool reason; never a business tool status."""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(f"Host tool: {code}{': ' + detail if detail else ''}")


def default_tools():
    """The packaged default preparation candidates; a pure read."""
    raw = (
        resource_files(__package__)
        .joinpath(DEFAULT_TOOLS_RESOURCE)
        .read_text(encoding="utf-8")
    )
    items = json.loads(raw)
    if not isinstance(items, list):
        raise HostToolError("invalid_default_list")
    for item in items:
        if set(item) != {"tool_id", "version", "command", "description"}:
            raise HostToolError("invalid_default_list")
    return tuple(items)


def user_data_root(environ=None, platform=None):
    """One resolution rule for every consumer; creates nothing.

    ``VESRYN_TOOLS_HOME`` overrides everything (the documented consumer
    configuration); otherwise LOCALAPPDATA on Windows and
    XDG_DATA_HOME|~/.local/share elsewhere, always under ``vesryn/data``.
    """
    environ = os.environ if environ is None else environ
    if environ.get("VESRYN_TOOLS_HOME"):
        return Path(environ["VESRYN_TOOLS_HOME"])
    name = sys_platform(platform)
    if name == "windows":
        base = environ.get("LOCALAPPDATA")
    else:
        base = environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    if not base:
        raise HostToolError("unknown_user_data_root")
    return Path(base) / "vesryn" / "data"


def sys_platform(platform=None):
    import sys

    value = sys.platform if platform is None else platform
    return "windows" if value.startswith("win") else "posix"


def tools_database(root):
    return Path(root) / "tools.sqlite3"


def tools_json(root):
    return Path(root) / "tools.json"


def _now():
    return datetime.now(UTC).isoformat()


def _which(command, environ):
    return shutil.which(command, path=environ.get("PATH") or None)


def _run_env(environ):
    """Target-shell PATH over the host's essential process environment."""
    merged = dict(os.environ)
    for key, value in environ.items():
        if value is not None:
            merged[key] = value
    return merged


def _probe(command, environ, runner):
    """Resolve and read the entry's own version line; read-only."""
    entry = _which(command, environ)
    if entry is None:
        return None, None
    argv = [entry, "--version"]
    if entry.lower().endswith((".bat", ".cmd")):
        argv = ["cmd", "/c", entry, "--version"]
    try:
        result = runner(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_run_env(environ),
        )
    except OSError, subprocess.SubprocessError:
        return entry, None
    return entry, (result.stdout or "").strip()


def _find_release(asset, version, environ, platform=None):
    host = sys_platform(platform)
    import platform as _platform

    machine = (_platform.machine() or "").lower()
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine, machine)
    abi = "msvc" if host == "windows" else "gnu"
    python = (
        f"{_platform.python_version_tuple()[0]}.{_platform.python_version_tuple()[1]}"
    )
    for release in asset.versions:
        if version is not None and release.version != version:
            continue
        if release.platform is None:
            if release.python is not None and not _python_ok(release.python, python):
                continue
            return release
        if (
            release.platform.os == host
            and release.platform.arch == arch
            and release.platform.abi in (None, abi)
        ):
            if release.python is not None and not _python_ok(release.python, python):
                continue
            return release
    raise HostToolError(
        "missing_release",
        f"{asset.tool_id} {version or 'default'} on {host}/{arch}",
    )


def _python_ok(requirement, actual):
    from packaging.version import Version

    floor = requirement.lstrip(">=").strip()
    try:
        return Version(actual) >= Version(floor)
    except ValueError:
        return False


def prepare_tool(
    tool_id,
    *,
    version=None,
    command=None,
    description=None,
    root=None,
    allow_network=False,
    uv="uv",
    aria2=None,
    environ=None,
    runner=subprocess.run,
    platform=None,
):
    """Check, prepare, register and sync one tool — the single entry.

    Returns an outcome document; ``registered_not_synced`` means the SQLite
    registration committed but the shared JSON did not (explicit rebuild
    via ``refresh_tools``); nothing partial is reported as success.
    """
    environ = os.environ if environ is None else dict(environ)
    root = user_data_root() if root is None else Path(root)
    defaults = {item["tool_id"]: item for item in default_tools()}
    if tool_id in defaults:
        item = defaults[tool_id]
        version = version or item["version"]
        command = command or item["command"]
        description = description or item["description"]
    if not command or not description:
        raise HostToolError("invalid_input", "command and description required")

    from .record_sources import bundled_records

    asset = next(
        (
            record
            for record in bundled_records()
            if isinstance(record, ToolAsset) and record.tool_id == tool_id
        ),
        None,
    )
    if asset is None:
        raise HostToolError("unknown_tool", tool_id)
    release = _find_release(asset, version, environ, platform)
    version = release.version

    entry, shown = _probe(command, environ, runner)
    if entry is not None:
        if shown is not None and version not in shown:
            return _outcome(
                "conflict",
                tool_id,
                command,
                version,
                entry,
                detail=f"existing entry reports: {shown[:120]}",
            )
        return _register(
            root,
            asset,
            command,
            version,
            entry,
            description,
            "external" if asset.provider != "uv" else "uv",
            reused=True,
            source_verified=False,
            status="reused",
            environ=environ,
        )

    if asset.provider == "uv":
        _uv_install(uv, asset, release, runner)
        entry, shown = _probe(command, environ, runner)
        if entry is None:
            raise HostToolError(
                "install_incomplete", f"{command} not resolvable after uv install"
            )
        return _register(
            root,
            asset,
            command,
            version,
            entry,
            description,
            "uv",
            reused=False,
            source_verified=True,
            status="installed",
            environ=environ,
        )

    if aria2 is None:
        raise HostToolError(
            "backend_required",
            "native preparation needs a pinned aria2 executable",
        )
    executable, _version, sha256 = aria2
    index = AssetIndex(asset_root(environ=environ))
    backend = Aria2NativeBackend(index, aria2=Aria2Source(executable, _version, sha256))
    target = AssetTarget(
        release.platform.os, release.platform.arch, abi=release.platform.abi
    )
    # Host preparation selects by tool identity alone: the frozen release
    # facts come straight from the record; no capability contract, Binding
    # or Adapter exists or is fabricated on this path (issue #33).
    from .assets import AssetSelection

    definition = next(
        item for item in legacy_preparation_definitions() if item.asset_id == tool_id
    )
    legacy_release = next(
        item
        for item in definition.releases
        if item.version == release.version
        and item.os in {"any", release.platform.os}
        and item.arch in {"any", release.platform.arch}
    )
    selection = AssetSelection(
        tool_id,
        None,
        None,
        definition.asset_id,
        definition.catalog_revision,
        definition.sha256,
        target,
        AssetPolicy("host-prepare"),
        legacy_release,
    )
    receipt = backend.prepare(
        selection, policy=AssetPolicy("host-prepare"), allow_network=allow_network
    )
    if receipt.outcome.status != "passed":
        return _outcome(
            "install_failed",
            tool_id,
            command,
            version,
            None,
            detail=receipt.outcome.reason or "",
        )
    entry = str(
        backend.delivery(selection, policy=AssetPolicy("host-prepare")).executable
    )
    return _register(
        root,
        asset,
        command,
        version,
        entry,
        description,
        "aria2",
        reused=receipt.outcome.reused,
        source_verified=True,
        status="installed",
        environ=environ,
    )


def _uv_install(uv, asset, release, runner):
    result = runner(
        [uv, "tool", "install", f"{asset.package or asset.tool_id}=={release.version}"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=dict(os.environ),
    )
    if result.returncode != 0:
        raise HostToolError(
            "uv_install_failed",
            (result.stderr or result.stdout or "")[:300],
        )


def _register(
    root,
    asset,
    command,
    version,
    entry,
    description,
    prepared_via,
    reused,
    source_verified,
    status,
    environ=None,
):
    root = Path(root)
    database = tools_database(root)
    store = open_record_store(database)
    try:
        store.assets.put(asset)
        store._db.execute(
            "INSERT OR REPLACE INTO tool_install"
            " (tool_id, command, version, entry, description, prepared_via,"
            " reused, source_verified, registered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset.tool_id,
                command,
                version,
                entry,
                description,
                prepared_via,
                1 if reused else 0,
                1 if source_verified else 0,
                _now(),
            ),
        )
        store._db.commit()
    finally:
        store.close()
    synced = _write_tools_json(root, environ)
    outcome = _outcome(
        status,
        asset.tool_id,
        command,
        version,
        entry,
        description=description,
        prepared_via=prepared_via,
        reused=reused,
        source_verified=source_verified,
    )
    if not synced:
        outcome["status"] = "registered_not_synced"
        outcome["detail"] = "registration saved; tools.json not synced"
    return outcome


def _outcome(
    status,
    tool_id,
    command,
    version,
    entry,
    detail="",
    description=None,
    prepared_via=None,
    reused=None,
    source_verified=None,
):
    value = {
        "status": status,
        "tool_id": tool_id,
        "command": command,
        "version": version,
        "entry": entry,
    }
    if detail:
        value["detail"] = detail
    if description is not None:
        value["description"] = description
    if prepared_via is not None:
        value["prepared_via"] = prepared_via
    if reused is not None:
        value["reused"] = reused
    if source_verified is not None:
        value["source_verified"] = source_verified
    return value


def refresh_tools(root=None, environ=None):
    """Regenerate tools.json from the registration facts — explicit rebuild.

    Only registrations whose command currently resolves in the target shell
    are listed; entry-not-ready tools stay registered but unlisted. Returns
    the number of entries written; a write failure raises ``HostToolError``
    with ``list_not_written``.
    """
    environ = os.environ if environ is None else environ
    root = user_data_root() if root is None else Path(root)
    database = tools_database(root)
    if not database.exists():
        raise HostToolError("not_registered", "no local registration database")
    store = open_record_store(database)
    try:
        rows = store._db.execute(
            "SELECT command, description, entry FROM tool_install ORDER BY command"
        ).fetchall()
    finally:
        store.close()
    entries = []
    seen = set()
    for command, description, entry in rows:
        if command in seen:
            continue
        # Only entries the target shell actually resolves are listed; a
        # registered native payload whose PATH is not prepared stays
        # registered but unlisted (entry is a recorded fact, not exposure).
        if _which(command, environ) is None:
            continue
        seen.add(command)
        entries.append({"command": command, "description": description})
    if not _atomic_write_json(tools_json(root), entries):
        raise HostToolError("list_not_written", str(tools_json(root)))
    return len(entries)


def uninstall_tool(tool_id, *, root=None, uv="uv", runner=subprocess.run):
    """Remove the registration and (for uv tools) the installed environment.

    Native payloads stay in the existing asset store — this path does not
    delete verified artifacts. The shared list is refreshed afterwards.
    """
    root = user_data_root() if root is None else Path(root)
    database = tools_database(root)
    if not database.exists():
        raise HostToolError("not_registered", tool_id)
    store = open_record_store(database)
    try:
        row = store._db.execute(
            "SELECT prepared_via, command FROM tool_install WHERE tool_id = ?",
            (tool_id,),
        ).fetchone()
        if row is None:
            raise HostToolError("not_registered", tool_id)
        prepared_via, command = row
        store._db.execute("DELETE FROM tool_install WHERE tool_id = ?", (tool_id,))
        store._db.commit()
    finally:
        store.close()
    if prepared_via == "uv":
        runner(
            [uv, "tool", "uninstall", command],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    refresh_tools(root=root)
    return {"status": "uninstalled", "tool_id": tool_id, "command": command}


def _write_tools_json(root, environ=None):
    """Snapshot sync from the committed registrations; True when written."""
    try:
        refresh_tools(root=root, environ=environ)
        return True
    except HostToolError:
        return False


def _atomic_write_json(path, entries):
    """Stable-sorted JSON via a temp file in the same directory."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(entries, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return True
    except OSError:
        return False
