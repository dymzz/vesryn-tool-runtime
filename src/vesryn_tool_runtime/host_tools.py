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
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from importlib.resources import files as resource_files
from pathlib import Path

from .asset_index import AssetIndex, asset_root
from .assets import AssetError, AssetPolicy, AssetTarget
from .discovery_records import RecordError, ToolAsset
from .native_assets import Aria2NativeBackend, Aria2Source
from .record_sources import legacy_preparation_definitions
from .record_store import open_record_store

DEFAULT_TOOLS_RESOURCE = "data/default-tools.json"

# The statuses an outcome document may carry. Everything else is raised as a
# HostToolError with a stable code (missing_release, backend_required,
# invalid_backend, native_prepare_failed, no_preparation_definition,
# no_preparation_release, install_incomplete, uv_install_failed,
# entry_conflict, list_not_written, not_registered, invalid_input,
# unknown_tool).
PREPARE_STATUSES = (
    "reused",
    "installed",
    "conflict",
    "install_failed",
    "registered_not_synced",
)
VIA_VALUES = ("uv", "aria2", "external")

# A version-like token in a --version line: "2.16", "15.2.0", "1.31.1-rc1".
_VERSION_TOKEN = re.compile(r"\d+(?:\.\d+)+(?:[-_.]?[0-9A-Za-z]+)*")


class HostToolError(Exception):
    """A stable host-tool reason; never a business tool status."""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(f"Host tool: {code}{': ' + detail if detail else ''}")


def default_tools():
    """The packaged default preparation candidates; a pure read.

    The resource lives at ``vesryn_tool_runtime/data/default-tools.json``
    inside the wheel; reading it registers, downloads and installs nothing.
    """
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
        base = environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
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


def bin_home(environ=None):
    """Exposure directory for entries NOT managed by uv: ~/.vesryn/bin.

    uv-managed CLIs stay in uv's own location (~/.local/bin). Native
    payloads stay verified in the asset store; this directory holds the
    runnable copies so ONE host-side PATH entry exposes every non-uv tool.
    ``VESRYN_BIN_HOME`` overrides (tests and non-default layouts).
    """
    environ = os.environ if environ is None else environ
    override = environ.get("VESRYN_BIN_HOME")
    return Path(override) if override else Path.home() / ".vesryn" / "bin"


def tools_json(root):
    return Path(root) / "tools.json"


def _now():
    return datetime.now(UTC).isoformat()


def _which(command, environ):
    """Resolve a command in the TARGET shell; an empty PATH resolves nothing."""
    return shutil.which(command, path=environ.get("PATH", ""))


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
    if entry.lower().endswith((".bat", ".cmd")):
        # cmd.exe needs the whole line quoted, otherwise a path with
        # spaces is split into two arguments.
        argv = f'cmd /c ""{entry}" --version"'
    else:
        argv = [entry, "--version"]
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
    output = (result.stdout or "").strip()
    if not output:
        output = (result.stderr or "").strip()
    return entry, output


def _reported_versions(text):
    """The version-like tokens a --version line actually reports."""
    if not text:
        return frozenset()
    return frozenset(_VERSION_TOKEN.findall(text))


def _version_matches(reported, selected):
    """True when the reported line contains the selected version.

    Whole tokens only: "2.1" must not match a reported "2.16" and
    "2.16.0" is the same release as "2.16".
    """
    if not selected:
        return False
    if selected in reported:
        return True
    from packaging.version import InvalidVersion, Version

    try:
        wanted = Version(selected)
    except InvalidVersion:
        return False
    for token in reported:
        try:
            if Version(token) == wanted:
                return True
        except InvalidVersion:
            continue
    return False


def _matched_version(reported, candidates):
    """The first candidate the reported line actually contains."""
    for candidate in candidates:
        if _version_matches(reported, candidate):
            return candidate
    return None


def _find_release(asset, version, platform=None):
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
    platform=None,
    uv="uv",
    aria2=None,
    environ=None,
    runner=subprocess.run,
):
    """Check, prepare, register and sync one tool — the single entry.

    Returns an outcome document; ``registered_not_synced`` means the SQLite
    registration committed but the shared JSON did not (explicit rebuild
    via ``refresh_tools``); nothing partial is reported as success.
    """
    environ = os.environ if environ is None else dict(environ)
    root = user_data_root(environ=environ) if root is None else Path(root)
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
    declared_versions = {item.version for item in asset.versions}

    # Probe the target shell FIRST: an already-resolvable entry is reused
    # as-is, but only when it reports the SELECTED version. A same-name
    # entry of another version is an honest conflict — it is never
    # overwritten and never silently registered under another version.
    entry, shown = _probe(command, environ, runner)
    if entry is not None:
        reported = _reported_versions(shown)
        if version is None:
            # No explicit selection: any declared release the entry reports
            # is a legitimate reuse, reported with the version it shows.
            matched = _matched_version(reported, sorted(declared_versions))
        else:
            matched = version if _version_matches(reported, version) else None
        if matched is None:
            return _outcome(
                "conflict",
                tool_id,
                command,
                version,
                entry,
                detail=f"existing entry reports: {(shown or '')[:120]}",
            )
        return _register(
            root,
            asset,
            command,
            matched,
            entry,
            description,
            "external",
            reused=True,
            source_verified=False,
            status="reused",
            environ=environ,
        )

    release = _find_release(asset, version, platform)
    version = release.version

    if asset.provider == "uv":
        _uv_install(uv, asset, release, runner)
        entry, shown = _probe(command, environ, runner)
        if entry is None:
            raise HostToolError(
                "install_incomplete", f"{command} not resolvable after uv install"
            )
        if not _version_matches(_reported_versions(shown), version):
            # The resolved entry is not the selected release (a same-name
            # entry shadows it): the Agent would run another version, so
            # nothing is registered under the selected one.
            return _outcome(
                "conflict",
                tool_id,
                command,
                version,
                entry,
                detail=f"resolved entry reports: {(shown or '')[:120]}",
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
    try:
        index = AssetIndex(asset_root(environ=_run_env(environ)))
        backend = Aria2NativeBackend(
            index, aria2=Aria2Source(executable, _version, sha256)
        )
    except AssetError as error:
        raise HostToolError("invalid_backend", str(error)) from None
    target = AssetTarget(
        release.platform.os, release.platform.arch, abi=release.platform.abi
    )
    # Host preparation selects by tool identity alone: the frozen release
    # facts come straight from the record; no capability contract, Binding
    # or Adapter exists or is fabricated on this path (issue #33).
    from .assets import AssetSelection

    definition = next(
        (item for item in legacy_preparation_definitions() if item.asset_id == tool_id),
        None,
    )
    if definition is None:
        raise HostToolError("no_preparation_definition", tool_id)
    legacy_release = next(
        (
            item
            for item in definition.releases
            if item.version == release.version
            and item.os in {"any", release.platform.os}
            and item.arch in {"any", release.platform.arch}
            and (
                item.abi is None
                or release.platform.abi is None
                or item.abi == release.platform.abi
            )
        ),
        None,
    )
    if legacy_release is None:
        raise HostToolError("no_preparation_release", f"{tool_id} {release.version}")
    try:
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
        payload = backend.delivery(
            selection, policy=AssetPolicy("host-prepare")
        ).executable
    except AssetError as error:
        raise HostToolError("native_prepare_failed", str(error)) from None
    entry = str(
        _expose_native_entry(
            tool_id, Path(payload), root, environ=environ, platform=platform
        )
    )
    return _register(
        root,
        asset,
        command,
        version,
        entry,
        description,
        "aria2",
        # The backend's `reused` means the verified payload was already in
        # the asset store (nothing was downloaded again) — a different fact
        # from the external reuse above, where an existing command of
        # unknown ownership was taken as-is.
        reused=receipt.outcome.reused,
        source_verified=True,
        status="reused" if receipt.outcome.reused else "installed",
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


def _expose_native_entry(tool_id, payload, root, environ=None, platform=None):
    """Copy the verified payload entry into ~/.vesryn/bin (the exposure
    directory for non-uv tools). The verified payload stays in the asset
    store. An existing file with IDENTICAL bytes is our own previous copy
    (idempotent re-exposure after a failed registration); different bytes
    replace our OWN previous copy — an upgrade — while a file of unknown
    ownership is an explicit conflict and is never overwritten."""
    import hashlib

    target = bin_home(environ) / Path(payload).name
    # A Windows entry must carry .exe or the shell cannot resolve it.
    if sys_platform(platform) == "windows" and target.suffix.lower() != ".exe":
        target = target.with_name(target.name + ".exe")
    if target.exists():

        def _hash(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

        if _hash(target) != _hash(payload):
            owner = "an unregistered command"
            database = tools_database(root)
            if database.exists():
                store = open_record_store(database)
                try:
                    row = store._db.execute(
                        "SELECT tool_id FROM tool_install WHERE entry = ?",
                        (str(target),),
                    ).fetchone()
                    owner = row[0] if row else owner
                finally:
                    store.close()
            if owner != tool_id:
                raise HostToolError(
                    "entry_conflict",
                    f"{target} is owned by {owner}",
                )
            # Our own previous copy: an upgrade replaces it.
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload, target)
    return target


def _is_exposed_copy(path):
    """True when a recorded entry is this runtime's own exposure copy."""
    home = bin_home()
    if path.parent == home:
        return True
    # The exposure directory may have been moved through VESRYN_BIN_HOME
    # since the registration; the recorded path is still our own copy.
    return path.parent.name == home.name and path.parent.parent == home.parent


def _same_entry(resolved, recorded):
    """True when the shell resolves exactly the recorded artifact."""
    if not recorded:
        return True
    try:
        return os.path.normcase(os.path.abspath(resolved)) == os.path.normcase(
            os.path.abspath(recorded)
        )
    except OSError, ValueError:
        return False


def _uv_package(tool_id, fallback):
    """The uv package name for a tool; the command is not always it."""
    from .record_sources import bundled_records

    for record in bundled_records():
        if isinstance(record, ToolAsset) and record.tool_id == tool_id:
            return record.package or tool_id
    return fallback


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
        # Idempotent: an identical registration (same tool, same content)
        # just updates the host facts below.
        # The bundled declaration is THE authority for this path: when the
        # stored asset row differs (e.g. the declaration gained a release),
        # sync the row to it. Conflicts are a composition concern, not a
        # sync concern.
        try:
            existing = store.assets.get(asset.tool_id)
        except RecordError:
            existing = None
        if existing is None:
            store.assets.put(asset)
        elif existing != asset:
            # The declaration gained releases; sync the derived row.
            try:
                store.assets.put(asset, sync=True)
            except RecordError as error:
                raise HostToolError("registration_failed", str(error)) from None
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
    AND resolves to the registered artifact are listed; a same-name entry
    from elsewhere is not the verified tool, and an entry-not-ready tool
    stays registered but unlisted. Returns the number of entries written; a
    write failure raises ``HostToolError`` with ``list_not_written``.
    """
    environ = os.environ if environ is None else environ
    root = user_data_root(environ=environ) if root is None else Path(root)
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
        resolved = _which(command, environ)
        if resolved is None:
            continue
        # The shell must resolve the REGISTERED artifact: a same-name
        # command from elsewhere is not the tool that was verified.
        if not _same_entry(resolved, entry):
            continue
        seen.add(command)
        entries.append({"command": command, "description": description})
    if not _atomic_write_json(tools_json(root), entries):
        raise HostToolError("list_not_written", str(tools_json(root)))
    return len(entries)


def uninstall_tool(tool_id, *, root=None, uv="uv", runner=subprocess.run):
    """Remove the registration and (for uv tools) the installed environment.

    Native payloads stay in the existing asset store — this path does not
    delete verified artifacts; only this runtime's own exposure copy in the
    exposure directory is removed. The shared list is refreshed afterwards.
    """
    root = user_data_root() if root is None else Path(root)
    database = tools_database(root)
    if not database.exists():
        raise HostToolError("not_registered", tool_id)
    store = open_record_store(database)
    try:
        row = store._db.execute(
            "SELECT prepared_via, command, entry FROM tool_install WHERE tool_id = ?",
            (tool_id,),
        ).fetchone()
        if row is None:
            raise HostToolError("not_registered", tool_id)
        prepared_via, command, entry = row
        store._db.execute("DELETE FROM tool_install WHERE tool_id = ?", (tool_id,))
        store._db.commit()
    finally:
        store.close()
    if prepared_via == "uv":
        runner(
            [uv, "tool", "uninstall", _uv_package(tool_id, command)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    elif prepared_via == "aria2" and entry:
        # Remove this tool's own exposed copy; the verified payload stays
        # in the asset store.
        exposed = Path(entry)
        if _is_exposed_copy(exposed):
            exposed.unlink(missing_ok=True)
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
        handle, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(entries, indent=2, sort_keys=True) + "\n")
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return True
    except OSError:
        return False
