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
  description, prepared_via, reused, verified_source, verified_sha256);
- ``<user data root>/vesryn/data/tools.json`` — the strict command/description
  list Agents read, regenerated from the registration facts.

Reading the packaged default list, importing this module and SessionStart do
nothing implicit: no registration, download or installation. Nothing here
modifies host PATH or user config; native PATH exposure stays a host-side
startup concern. External installs missing upstream verification evidence
are registered after the entry/version probe with ``source_verified=False``.
This states only that the installation source has not been established; the
CLI is still available. An executable hash is not a publisher archive hash.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from importlib.resources import files as resource_files
from pathlib import Path, PurePosixPath

from filelock import FileLock, Timeout

from ._uv_tool_packages import (
    inspect_uv_tool,
    normalize_with_packages,
    satisfies_request,
)
from .asset_index import AssetIndex, asset_root, python_asset_directory
from .assets import AssetError, AssetPolicy, AssetTarget
from .discovery_records import RecordError, ToolAsset
from .native_assets import Aria2NativeBackend, Aria2Source
from .record_sources import legacy_preparation_definitions
from .record_store import open_record_store, upgrade_record_store
from .uv_assets import host_platform

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
    """The host OS in the RECORD vocabulary (windows/linux/macos)."""
    os_name, _arch = host_platform(platform)
    return os_name or "posix"


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
    """Resolve and read the entry's own version line; read-only.

    Returns ``(entry, output, ok, detail)``. ``ok`` is False when the probe
    itself failed — a non-zero exit code or a runner error — so a version
    string printed by a failing command is never read as a usable entry.
    """
    entry = _which(command, environ)
    if entry is None:
        return None, None, False, "not resolvable in the target shell"
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
        return entry, None, False, "version probe could not run"
    output = (result.stdout or "").strip()
    if not output:
        output = (result.stderr or "").strip()
    if result.returncode != 0:
        return entry, output, False, f"version probe exited {result.returncode}"
    return entry, output, True, ""


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


def _uv_entry_version(uv, asset, environ, runner, entry, version):
    """The version of a uv tool entry that prints no version line of its own.

    uv states the version of the environment it manages and the entries it
    exposes, so a CLI without a ``--version`` line is still verifiable. The
    version is accepted only when the resolved entry IS that environment's own
    entry and it names the selected release: an entry of another installation
    stays the honest conflict it was before.
    """
    if asset.provider != "uv":
        return None
    try:
        observed = _inspect_packages(uv, asset, environ, runner)
    except HostToolError:
        return None
    if observed is None:
        return None
    if not any(_same_entry(entry, path) for path in observed["entrypoints"]):
        return None
    reported = observed["version"]
    if version is None:
        declared = {item.version for item in asset.versions}
        return reported if reported in declared else None
    return version if _version_matches({reported}, version) else None


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
    with_packages=None,
):
    """Check, prepare, register and sync one tool — the single entry.

    Returns an outcome document; ``registered_not_synced`` means the SQLite
    registration committed but the shared JSON did not (explicit rebuild
    via ``refresh_tools``); nothing partial is reported as success.

    ``with_packages=None`` preserves legacy behavior. An explicit tuple/list
    selects exact additional uv requirements; ``()`` clears that requested
    set. Reuse then requires the actual tool environment, not just CLI version.
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
    try:
        packages = normalize_with_packages(with_packages, asset.package or tool_id)
    except (ValueError, TypeError) as error:
        raise HostToolError("invalid_input", str(error)) from None
    if packages is not None and asset.provider != "uv":
        raise HostToolError("invalid_input", "additional packages require a uv tool")
    declared_versions = {item.version for item in asset.versions}
    _upgrade_host_database(root)
    proof = (None, None)

    # Probe the target shell FIRST: an already-resolvable entry is reused
    # as-is, but only when the probe SUCCEEDED and the entry reports the
    # SELECTED version. A same-name entry of another version — or an entry
    # whose version probe failed — is an honest conflict: it is never
    # overwritten and never silently registered under another version.
    entry, shown, probed, probe_detail = _probe(command, environ, runner)
    if entry is not None:
        if not probed:
            # The probe FAILED: its output is not evidence that the entry
            # works. A uv tool states its version in uv's own listing
            # rather than on a version line, so that is read next -- and
            # only for the entry uv itself owns.
            matched = _uv_entry_version(uv, asset, environ, runner, entry, version)
            if matched is None:
                return _outcome(
                    "conflict",
                    tool_id,
                    command,
                    version,
                    entry,
                    detail=probe_detail,
                )
        else:
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
        # Keep the recorded installation owner and its actual artifact proof.
        # The current declaration is compared with that proof below; a cache
        # hit or successful version probe never creates source evidence.
        prepared_via, verified_source, verified_sha256 = _existing_ownership(
            asset, matched, entry, root
        )
        proof = verified_source, verified_sha256
        environment = None
        if packages is not None:
            observed = _inspect_packages(uv, asset, environ, runner)
            if observed is None or not any(
                _same_entry(entry, path) for path in observed["entrypoints"]
            ):
                return _outcome(
                    "conflict",
                    tool_id,
                    command,
                    matched,
                    entry,
                    detail="entry is not owned by the selected uv tool environment",
                )
            if satisfies_request(observed, asset.package or tool_id, matched, packages):
                environment = observed["environment"]
            version = matched
        if packages is None or environment is not None:
            outcome = _register(
                root,
                asset,
                command,
                matched,
                entry,
                description,
                prepared_via,
                reused=True,
                status="reused",
                environ=environ,
                verified_source=verified_source,
                verified_sha256=verified_sha256,
                platform=platform,
            )
            if environment is not None:
                outcome["environment"] = environment
            return outcome

    release = _find_release(asset, version, platform)
    version = release.version

    if asset.provider == "uv":
        artifact = _verified_artifact(
            asset, release, allow_network=allow_network, environ=environ
        )
        interpreter = _tool_interpreter(
            artifact.name, environ, packages or (), uv, runner
        )
        if interpreter is None:
            # No interpreter on this host can load the artifact's extensions.
            raise HostToolError(
                "interpreter_unavailable",
                f"no GIL-enabled Python {sys.version_info.major}."
                f"{sys.version_info.minor} for {artifact.name}",
            )
        _uv_install(
            uv,
            asset,
            release,
            artifact,
            runner,
            allow_network=allow_network,
            interpreter=interpreter,
            with_packages=packages or (),
            environ=environ,
            reinstall_main=packages is not None
            and proof != (release.source, release.digest),
        )
        entry, shown, probed, probe_detail = _probe(command, environ, runner)
        if entry is None:
            raise HostToolError(
                "install_incomplete", f"{command} not resolvable after uv install"
            )
        if not probed:
            return _outcome(
                "conflict",
                tool_id,
                command,
                version,
                entry,
                detail=probe_detail,
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
        environment = None
        if packages is not None:
            observed = _inspect_packages(uv, asset, environ, runner)
            if (
                observed is None
                or not any(_same_entry(entry, path) for path in observed["entrypoints"])
                or not satisfies_request(
                    observed, asset.package or tool_id, version, packages
                )
            ):
                raise HostToolError(
                    "environment_unverified",
                    "installed tool does not satisfy the complete request",
                )
            environment = observed["environment"]
        outcome = _register(
            root,
            asset,
            command,
            version,
            entry,
            description,
            "uv",
            reused=False,
            status="installed",
            environ=environ,
            verified_source=release.source,
            verified_sha256=release.digest,
            platform=platform,
        )
        if environment is not None:
            outcome["environment"] = environment
        return outcome

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
            and item.source == release.source
            and item.sha256 == release.digest
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
        status="reused" if receipt.outcome.reused else "installed",
        environ=environ,
        verified_source=legacy_release.source,
        verified_sha256=legacy_release.sha256,
        platform=platform,
    )


def _verified_artifact(asset, release, *, allow_network, environ=None, timeout=300):
    """The SELECTED artifact, with its registered digest actually checked.

    The release pins a source URL and the publisher's SHA-256; the file that
    is installed is exactly the file that was verified here. Without network
    permission only an already-verified copy in the asset root is used — a
    missing artifact is an explicit ``offline_missing``, never an unverified
    install.
    """
    import hashlib
    from urllib.error import URLError
    from urllib.parse import urlsplit
    from urllib.request import urlopen

    environ = os.environ if environ is None else environ
    directory = python_asset_directory(
        asset_root(environ=_run_env(environ)),
        asset.tool_id,
        release.version,
        release.digest,
    )
    name = PurePosixPath(urlsplit(release.source).path).name
    if not name:
        # A source URL without a file name names no artifact.
        raise HostToolError("invalid_source", release.source)
    path = directory / name

    def _digest(candidate):
        with candidate.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    if path.exists():
        if not path.is_file():
            raise HostToolError("invalid_source", release.source)
        if _digest(path) == release.digest:
            return path
        # A corrupt cached copy is never installed and never reused.
        path.unlink(missing_ok=True)
    if not allow_network:
        raise HostToolError("offline_missing", release.source)
    directory.mkdir(parents=True, exist_ok=True)
    # A unique temp name in the same directory: two concurrent downloads of
    # the same artifact never write into one file.
    handle, temporary = tempfile.mkstemp(
        dir=directory, prefix=name + ".", suffix=".part"
    )
    try:
        with (
            os.fdopen(handle, "wb") as stream,
            urlopen(release.source, timeout=timeout) as response,
        ):
            shutil.copyfileobj(response, stream)
    except (OSError, URLError, ValueError) as error:
        Path(temporary).unlink(missing_ok=True)
        raise HostToolError("download_failed", str(error)) from None
    if _digest(Path(temporary)) != release.digest:
        Path(temporary).unlink(missing_ok=True)
        raise HostToolError("artifact_mismatch", release.source)
    os.replace(temporary, path)
    return path


def _interpreter_facts(executable):
    """(major, minor, gil_enabled) of an interpreter, or None."""
    try:
        result = subprocess.run(
            [
                str(executable),
                "-c",
                (
                    "import sys; print(sys.version_info[0], sys.version_info[1],"
                    " getattr(sys, '_is_gil_enabled', lambda: True)())"
                ),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    parts = (result.stdout or "").split()
    if result.returncode != 0 or len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), parts[2] == "True"
    except ValueError:
        return None


def _pure_python_artifact(name):
    """True when the wheel carries no compiled extension."""
    from packaging.utils import parse_wheel_filename

    try:
        _, _, _, tags = parse_wheel_filename(name)
    except ValueError:
        return False
    return all(tag.platform == "any" and tag.abi == "none" for tag in tags)


def _uv_interpreters(uv, environ, version, runner=subprocess.run):
    """The GIL-enabled interpreters uv knows for that version, in uv's order.

    uv's own listing is the source. It tells the free-threaded builds apart
    from the ordinary ones — its key and its variant say which a build is —
    and it lists the interpreters uv manages, which are not on the target
    PATH at all. Only an installed interpreter (one with a path) can be
    named; a version uv could download is not one yet.
    """
    result = runner(
        [uv, "python", "list", "--output-format", "json"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_run_env(environ or {}),
    )
    if result.returncode != 0:
        return []
    try:
        entries = json.loads(result.stdout or "[]")
    except ValueError:
        return []
    found = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not path or entry.get("implementation") != "cpython":
            continue
        if entry.get("variant") != "default":
            # The free-threaded build cannot load a GIL-bound wheel.
            continue
        if not str(entry.get("version", "")).startswith(version + "."):
            continue
        found.append(path)
    return found


def _tool_interpreter(name, environ, packages=(), uv="uv", runner=subprocess.run):
    """The interpreter that builds the tool environment — named, not guessed.

    uv picks an interpreter on its own when none is named, and on a
    free-threaded host that pick cannot load the GIL-bound extensions of a
    compiled wheel: the install then fails with "the wheel was built for
    the stable ABI, which requires a GIL-enabled interpreter". The
    interpreter is therefore named — the running one when it can load the
    artifact, otherwise a GIL-enabled interpreter of the SAME version, taken
    from uv's own list. None means no interpreter can load it.

    A requested plugin set is installed into the SAME environment, so the
    interpreter has to load its artifacts too. Published plugin wheels are
    commonly GIL-bound — a cpXY build or the stable ABI — which a
    free-threaded interpreter cannot load: naming the running one leaves the
    backend to build the plugin from source. With plugins requested, a
    GIL-enabled interpreter of the same version is therefore named. The
    running one is kept when nothing compiled goes into the environment, and
    when no such interpreter exists the install is not refused over it.
    """
    running = sys.executable
    facts = _interpreter_facts(running)
    if facts is None:
        return running
    if facts[2]:
        # The running interpreter loads GIL-bound wheels.
        return running
    if not packages and _pure_python_artifact(name):
        # Nothing compiled is going into the environment.
        return running
    version = f"{facts[0]}.{facts[1]}"
    for candidate in _uv_interpreters(uv, environ, version, runner):
        return candidate
    if _pure_python_artifact(name):
        # The plugin set may be pure Python after all: keep the running
        # interpreter rather than refuse an install that could succeed.
        return running
    return None


def _uv_install(
    uv,
    asset,
    release,
    artifact,
    runner,
    *,
    allow_network,
    interpreter=None,
    with_packages=(),
    environ=None,
    reinstall_main=False,
):
    """Install the verified artifact through uv's own tool environment."""
    command = [uv, "--no-config"]
    if not allow_network:
        # The offline requirement reaches the backend itself.
        command.append("--offline")
    command += ["tool", "install"]
    if interpreter:
        # The interpreter is named, not guessed by the backend.
        command += ["--python", str(interpreter)]
    for requirement in with_packages:
        command += ["--with", requirement]
    if reinstall_main:
        command += ["--reinstall-package", asset.package or asset.tool_id]
    command += [str(artifact)]
    result = runner(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=_run_env(environ or {}),
    )
    if result.returncode != 0:
        raise HostToolError(
            "uv_install_failed",
            (result.stderr or result.stdout or "")[:300],
        )


def _inspect_packages(uv, asset, environ, runner):
    try:
        return inspect_uv_tool(
            uv, asset.package or asset.tool_id, environ=environ, runner=runner
        )
    except ValueError, TypeError, OSError, subprocess.SubprocessError:
        raise HostToolError(
            "environment_unverified", "cannot verify the selected uv tool environment"
        ) from None


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


def _declared_release(asset, version, platform=None):
    """The declared release of that version FOR THIS TARGET, or None.

    A version can carry more than one release — deptry ships a manylinux and
    a win_amd64 wheel under the same version — so the release is selected the
    way the preparation selects it: by the target's platform and ABI.
    """
    try:
        return _find_release(asset, version, platform)
    except HostToolError:
        return None


def _existing_ownership(asset, version, entry, root):
    """Recorded installation owner and proof for the same version and entry.

    Download caches and mutable Catalog rows cannot establish what installed
    this entry. Preserve the actual installation proof even if a new
    declaration names different bytes; registration derives its current
    verification result by comparing that proof with the selected release.
    """
    database = tools_database(root)
    if not database.exists():
        return "external", None, None
    store = open_record_store(database)
    try:
        row = store._db.execute(
            "SELECT prepared_via, version, entry, verified_source, verified_sha256"
            " FROM tool_install WHERE tool_id = ?",
            (asset.tool_id,),
        ).fetchone()
    finally:
        store.close()
    if row is not None:
        owner, recorded_version, recorded_entry, source, sha256 = row
        if (
            _version_matches({recorded_version}, str(version))
            and recorded_entry
            and _same_entry(entry, recorded_entry)
        ):
            return owner, source, sha256
    return "external", None, None


def _store_lock(root, timeout=120):
    """The existing write coordination: one lock per local store.

    The registration and the list snapshot it produces are published under
    this lock, so a publisher that was delayed cannot write a stale snapshot
    over a newer one. The lock is taken ONCE per operation — a second
    FileLock instance on the same file would wait for itself.
    """
    return FileLock(str(tools_database(root)) + ".lock", timeout=timeout)


def _upgrade_host_database(root):
    """Upgrade only during explicit host preparation/refresh/uninstall."""
    database = tools_database(root)
    if database.exists():
        try:
            with _store_lock(root):
                upgrade_record_store(database)
        except Timeout:
            raise HostToolError("store_busy", str(root)) from None


def _register(
    root,
    asset,
    command,
    version,
    entry,
    description,
    prepared_via,
    reused,
    status,
    environ=None,
    verified_source=None,
    verified_sha256=None,
    platform=None,
):
    release = _declared_release(asset, version, platform)
    # @need-ids: SPEC_TR_MAIN_ARTIFACT_PROOF
    source_verified = bool(
        release is not None
        and verified_source == release.source
        and verified_sha256 == release.digest
    )
    root = Path(root)
    database = tools_database(root)
    # The registration and the snapshot it produces are published under the
    # store's own lock: a delayed publisher re-reads the committed facts
    # instead of writing a stale list over a newer one.
    try:
        with _store_lock(root):
            if database.exists():
                upgrade_record_store(database)
            synced = _register_locked(
                root,
                database,
                asset,
                command,
                version,
                entry,
                description,
                prepared_via,
                reused,
                verified_source,
                verified_sha256,
                environ,
            )
    except Timeout:
        raise HostToolError("store_busy", str(root)) from None
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


def _register_locked(
    root,
    database,
    asset,
    command,
    version,
    entry,
    description,
    prepared_via,
    reused,
    verified_source,
    verified_sha256,
    environ,
):
    """The registration and its snapshot, published under the store's lock."""
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
            " reused, verified_source, verified_sha256, registered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset.tool_id,
                command,
                version,
                entry,
                description,
                prepared_via,
                1 if reused else 0,
                verified_source,
                verified_sha256,
                _now(),
            ),
        )
        store._db.commit()
    finally:
        store.close()
    try:
        _publish_list(root, environ)
        return True
    except HostToolError:
        return False


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


def _publish_list(root, environ=None):
    """Write the list from the committed facts; the caller holds the lock.

    The snapshot is always built from the CURRENT registrations, so a
    publisher that was delayed publishes the facts as they are now rather
    than the ones it read before it waited for the lock.
    """
    environ = os.environ if environ is None else environ
    database = tools_database(root)
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
    try:
        with _store_lock(root):
            upgrade_record_store(database)
            return _publish_list(root, environ)
    except Timeout:
        raise HostToolError("store_busy", str(root)) from None


def uninstall_tool(tool_id, *, root=None, uv="uv", environ=None, runner=subprocess.run):
    """Remove the registration and (for uv tools) the installed environment.

    The backend's own result decides: when the uninstall fails, the
    registration and the list stay as they are and the failure is reported —
    a partial removal is never presented as a complete uninstall.

    Native payloads stay in the existing asset store — this path does not
    delete verified artifacts; only this runtime's own exposure copy in the
    exposure directory is removed. The shared list is refreshed afterwards,
    in the SAME target environment the preparation used: a rebuild that
    resolved in the host's shell would drop every tool that only exists in
    the target shell.
    """
    environ = os.environ if environ is None else environ
    root = user_data_root(environ=environ) if root is None else Path(root)
    database = tools_database(root)
    if not database.exists():
        raise HostToolError("not_registered", tool_id)
    _upgrade_host_database(root)
    store = open_record_store(database)
    try:
        row = store._db.execute(
            "SELECT prepared_via, command, entry FROM tool_install WHERE tool_id = ?",
            (tool_id,),
        ).fetchone()
    finally:
        store.close()
    if row is None:
        raise HostToolError("not_registered", tool_id)
    prepared_via, command, entry = row

    # The removal happens BEFORE the registration is dropped, so a failed
    # removal keeps the registration and the list entry.
    if prepared_via == "uv":
        result = runner(
            [uv, "tool", "uninstall", _uv_package(tool_id, command)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_run_env(environ),
        )
        if result.returncode != 0:
            raise HostToolError(
                "uninstall_failed",
                (result.stderr or result.stdout or "")[:300],
            )
    elif prepared_via == "aria2" and entry:
        # Remove this tool's own exposed copy; the verified payload stays
        # in the asset store.
        exposed = Path(entry)
        if _is_exposed_copy(exposed):
            try:
                exposed.unlink(missing_ok=True)
            except OSError as error:
                raise HostToolError("uninstall_failed", str(error)) from None

    with _store_lock(root):
        store = open_record_store(database)
        try:
            store._db.execute("DELETE FROM tool_install WHERE tool_id = ?", (tool_id,))
            store._db.commit()
        finally:
            store.close()
        _publish_list(root, environ)
    return {"status": "uninstalled", "tool_id": tool_id, "command": command}


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
