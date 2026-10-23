"""Explicit aria2 acquisition and immutable native payload delivery; no tool runner."""

import hashlib
import ntpath
import os
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from filelock import FileLock, Timeout

from .asset_index import AssetFile, AssetIndex, AssetReceipt, native_asset_directory
from .assets import AssetError, AssetPolicy, AssetSelection, _contains, _sha256
from .contracts import ToolResult


def _hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Aria2Source:
    """A separately prepared aria2 executable, pinned by version and file digest."""

    executable: str
    version: str
    sha256: str

    def __post_init__(self):
        if (
            not isinstance(self.executable, str)
            or not Path(self.executable).is_absolute()
        ):
            raise AssetError("invalid_location")
        if not isinstance(self.version, str) or not re.fullmatch(
            r"\d+\.\d+\.\d+", self.version
        ):
            raise AssetError("invalid_backend")
        _sha256(self.sha256)


@dataclass(frozen=True)
class NativeAssetDelivery:
    """Verified local content for ordinary File/Directory import, never permission."""

    receipt: AssetReceipt
    entry: str

    def __post_init__(self):
        if (
            not isinstance(self.receipt, AssetReceipt)
            or self.receipt.selection.release.backend != "aria2"
            or self.receipt.outcome.status != "passed"
            or self.entry not in {item.path for item in self.receipt.files}
        ):
            raise AssetError("invalid_receipt")

    @property
    def directory(self):
        return Path(self.receipt.locator)

    @property
    def executable(self):
        return self.directory / self.entry

    def document(self):
        return {
            "selection_id": self.receipt.selection.selection_id,
            "artifact_id": self.receipt.selection.artifact_id,
            "target": self.receipt.selection.target.document(),
            "directory": str(self.directory),
            "entry": self.entry,
            "source_sha256": self.receipt.verified_source_sha256,
            "files": [
                {"path": item.path, "sha256": item.sha256}
                for item in self.receipt.files
            ],
        }


def _member_name(name):
    """Require portable relative names before using stdlib archive extractors."""
    name = name.removesuffix("/")
    parts = name.split("/")
    if (
        not name
        or "\\" in name
        or ":" in name
        or "\0" in name
        or PurePosixPath(name).is_absolute()
        or any(part in {"", ".", ".."} or ntpath.isreserved(part) for part in parts)
    ):
        raise AssetError("unsafe_archive")
    return name


def _stream_hash(stream):
    # PE headers are bounded here; payload hashing itself is streamed.
    header = stream.read(65536)
    checksum = hashlib.sha256(header)
    while block := stream.read(1024 * 1024):
        checksum.update(block)
    return checksum.hexdigest(), header


def _binary_target(header, target):
    """Verify ELF/PE OS and machine, without executing a foreign payload."""
    machines = {
        "x86_64": (62, 0x8664, 2),
        "aarch64": (183, 0xAA64, 2),
        "x86": (3, 0x14C, 1),
    }
    if target.arch not in machines or target.os not in {"linux", "windows"}:
        raise AssetError("unsupported_target")
    elf, pe, bits = machines[target.arch]
    valid = False
    if (
        target.os == "linux"
        and len(header) >= 20
        and header[:4] == b"\x7fELF"
        and header[4] == bits
        and header[5] in {1, 2}
        and header[6] == 1
        and header[7] in {0, 3}
    ):
        endian = "<" if header[5] == 1 else ">"
        kind, machine = struct.unpack_from(endian + "HH", header, 16)
        valid = machine == elf and kind in {2, 3}
    if target.os == "windows" and len(header) >= 64 and header[:2] == b"MZ":
        offset = struct.unpack_from("<I", header, 60)[0]
        valid = (
            offset + 6 <= len(header)
            and header[offset : offset + 4] == b"PE\0\0"
            and struct.unpack_from("<H", header, offset + 4)[0] == pe
        )
    if not valid:
        raise AssetError("artifact_target_mismatch")


class Aria2NativeBackend:
    """Acquire only when explicitly allowed; verify every reuse against its source.

    Supported native payloads are raw ELF/PE binaries, ZIP and tar archives with
    ordinary files/directories. A target may differ from the acquisition host;
    this class never executes the prepared CLI or starts Dagger.
    """

    def __init__(
        self, index, *, aria2, timeout=300, max_files=10000, max_bytes=512 * 1024 * 1024
    ):
        if not isinstance(index, AssetIndex) or not isinstance(aria2, Aria2Source):
            raise AssetError("invalid_backend")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
            or type(max_files) is not int
            or max_files < 1
            or type(max_bytes) is not int
            or max_bytes < 1
        ):
            raise AssetError("invalid_backend")
        self.index = index
        self.root = index.root
        self.aria2 = aria2
        self.timeout = timeout
        self.max_files = max_files
        self.max_bytes = max_bytes

    def _check(self, selection, policy):
        if not isinstance(selection, AssetSelection) or not isinstance(
            policy, AssetPolicy
        ):
            raise AssetError("invalid_selection")
        if (
            selection.release.backend != "aria2"
            or selection.release.distribution != "native"
        ):
            raise AssetError("invalid_backend")
        if not policy.enabled:
            raise AssetError("selection_disabled")
        if not _contains(policy.specifier, selection.release.version):
            raise AssetError("no_matching_version")
        if selection.target.os not in {
            "linux",
            "windows",
        } or selection.target.arch not in {"x86_64", "aarch64", "x86"}:
            raise AssetError("unsupported_target")
        # Check before the common index can open a locator through a link.
        self._path(self.index.path)
        self._path(native_asset_directory(self.root, selection))

    def _path(self, path):
        path = Path(path)
        if not path.resolve().is_relative_to(self.root):
            raise AssetError("invalid_location")
        for parent in (path, *path.parents):
            if parent == self.root:
                break
            if parent.is_symlink() or parent.is_junction():
                raise AssetError("invalid_location")
        return path

    def _archive(self, selection):
        return self._path(
            self.root
            / "downloads"
            / ("sha256-" + selection.release.sha256)
            / "artifact"
        )

    def _verify_source(self, archive, selection):
        if not archive.is_file():
            raise AssetError("local_missing")
        if archive.stat().st_size > self.max_bytes:
            raise AssetError("asset_too_large")
        if _hash(archive) != selection.release.sha256:
            raise AssetError("integrity_mismatch")

    def _kind(self, selection):
        suffix = urlsplit(selection.release.source).path.lower()
        if suffix.endswith(".zip"):
            return "zip"
        if suffix.endswith(
            (".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar.zst")
        ):
            return "tar"
        return "raw"

    def _manifest(self, archive, selection):
        """Derive expected file hashes from the verified source, without writes."""
        files, headers, names = [], {}, set()
        count, size = 0, 0

        def member(name, length):
            nonlocal count, size
            name = _member_name(name)
            count += 1
            size += length
            if count > self.max_files or size > self.max_bytes:
                raise AssetError("asset_too_large")
            if name.casefold() in names:
                raise AssetError("unsafe_archive")
            names.add(name.casefold())
            return name

        def content(name, stream):
            checksum, header = _stream_hash(stream)
            files.append(AssetFile(name, checksum))
            if PurePosixPath(name).name in {
                selection.release.entrypoint,
                selection.release.entrypoint + ".exe",
            }:
                headers[name] = header

        kind = self._kind(selection)
        if kind == "zip":
            with zipfile.ZipFile(archive) as package:
                for item in package.infolist():
                    # filename normalizes Windows separators and truncates NUL;
                    # check the original archive name before stdlib extraction.
                    name = member(item.orig_filename, item.file_size)
                    mode = stat.S_IFMT(item.external_attr >> 16)
                    if (
                        mode not in {0, stat.S_IFREG, stat.S_IFDIR}
                        or item.flag_bits & 1
                    ):
                        raise AssetError("unsafe_archive")
                    if not item.is_dir():
                        with package.open(item) as stream:
                            content(name, stream)
        elif kind == "tar":
            with tarfile.open(archive, "r:*") as package:
                for item in package:
                    name = member(item.name, item.size)
                    if not (item.isfile() or item.isdir()) or item.sparse is not None:
                        raise AssetError("unsafe_archive")
                    if item.isfile():
                        with package.extractfile(item) as stream:
                            content(name, stream)
        else:
            name = member(selection.release.entrypoint, archive.stat().st_size)
            with archive.open("rb") as stream:
                content(name, stream)
        if len(headers) != 1:
            raise AssetError(
                "entrypoint_missing" if not headers else "entrypoint_ambiguous"
            )
        entry, header = next(iter(headers.items()))
        _binary_target(header, selection.target)
        return tuple(sorted(files, key=lambda item: item.path)), entry

    def _verify_payload(self, directory, files):
        directory = self._path(directory)
        expected = {item.path: item.sha256 for item in files}
        actual = {}
        if not directory.is_dir():
            raise AssetError("local_missing")
        for path in directory.rglob("*"):
            self._path(path)
            if path.is_dir():
                continue
            if not stat.S_ISREG(path.lstat().st_mode):
                raise AssetError("invalid_location")
            name = path.relative_to(directory).as_posix()
            if name not in expected:
                raise AssetError("integrity_mismatch")
            actual[name] = _hash(path)
        if actual != expected:
            raise AssetError("integrity_mismatch")

    def _extract(self, archive, selection, directory, files, entry):
        directory.mkdir()
        kind = self._kind(selection)
        if kind == "zip":
            with zipfile.ZipFile(archive) as package:
                package.extractall(directory)
        elif kind == "tar":
            with tarfile.open(archive, "r:*") as package:
                package.extractall(directory, filter="data")
        else:
            shutil.copyfile(archive, directory / entry)
        if selection.target.os == "linux":
            (directory / entry).chmod(0o755)
        self._verify_payload(directory, files)

    def _download(self, selection, directory):
        executable = Path(self.aria2.executable)
        if _hash(executable) != self.aria2.sha256:
            raise AssetError("backend_integrity_mismatch")
        version = subprocess.run(
            [str(executable), "--no-conf=true", "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=directory,
            timeout=self.timeout,
            check=False,
        )
        if version.returncode:
            return ToolResult(
                "failed",
                version.returncode,
                executed=True,
                reason="backend_version_check_failed",
            )
        match = re.search(
            rb"^aria2 version ([0-9.]+)\r?$", version.stdout, re.MULTILINE
        )
        if match is None or match.group(1).decode() != self.aria2.version:
            raise AssetError("backend_version_mismatch")
        if urlsplit(selection.release.source).scheme != "https":
            raise AssetError("unsupported_source")
        result = subprocess.run(
            [
                str(executable),
                "--no-conf=true",
                "--no-netrc=true",
                "--check-certificate=true",
                "--enable-rpc=false",
                "--enable-dht=false",
                "--enable-dht6=false",
                "--follow-torrent=false",
                "--follow-metalink=false",
                "--auto-file-renaming=false",
                "--allow-overwrite=false",
                "--continue=false",
                "--file-allocation=none",
                "--max-tries=1",
                "--connect-timeout=30",
                "--timeout=30",
                "--summary-interval=0",
                "--dir=" + str(directory),
                "--out=artifact",
                "--checksum=sha-256=" + selection.release.sha256,
                selection.release.source,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=directory,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode:
            return ToolResult(
                "failed",
                result.returncode,
                executed=True,
                complete=True,
                current=True,
                reason="download_failed",
            )
        return None

    def _passed(self, selection, files, *, reused):
        return AssetReceipt(
            selection,
            ToolResult(
                "passed", 0, executed=True, complete=True, current=True, reused=reused
            ),
            str(native_asset_directory(self.root, selection)),
            files,
            verified_source_sha256=selection.release.sha256,
        )

    def _prepare(self, selection, allow_network, source_artifact):
        archive = self._archive(selection)
        destination = self._path(native_asset_directory(self.root, selection))
        self._path(self.root / "downloads").mkdir(parents=True, exist_ok=True)
        # Unique staging is always inside this explicit root; failed work is discarded.
        with tempfile.TemporaryDirectory(
            prefix=".prepare-", dir=self.root / "downloads"
        ) as temporary:
            temporary = Path(temporary)
            source_lock = self._path(
                self.root / "locks" / ("source-" + selection.release.sha256 + ".lock")
            )
            with FileLock(source_lock, timeout=self.index.timeout):
                if archive.exists():
                    self._verify_source(archive, selection)
                else:
                    if source_artifact is not None:
                        shutil.copyfile(source_artifact, temporary / "artifact")
                    elif allow_network:
                        failed = self._download(selection, temporary)
                        if failed is not None:
                            return AssetReceipt(selection, failed)
                    else:
                        return AssetReceipt(
                            selection,
                            ToolResult("unavailable", None, reason="offline_missing"),
                        )
                    self._verify_source(temporary / "artifact", selection)
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(temporary / "artifact", archive)
            files, entry = self._manifest(archive, selection)
            reused = destination.exists()
            if reused:
                self._verify_payload(destination, files)
            else:
                staged = temporary / "payload"
                self._extract(archive, selection, staged, files, entry)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staged, destination)
            return self._passed(selection, files, reused=reused)

    def prepare(self, selection, *, policy, allow_network=False, source_artifact=None):
        """Return/record the shared receipt. Failures never replace an installation.

        ``policy`` is the host's current acquisition policy, including disablement.
        Network access defaults off. ``source_artifact`` explicitly restores an
        external cache artifact, checked against the same trusted release digest.
        Neither this operation nor its passed outcome admits a business tool call.
        """
        self._check(selection, policy)
        if type(allow_network) is not bool:
            raise AssetError("invalid_policy")
        # Refuse a corrupt shared index before downloading or publishing anything.
        self.index.installed(selection)
        locks = self._path(self.root / "locks")
        locks.mkdir(parents=True, exist_ok=True)
        lock = self._path(locks / (selection.artifact_id + ".lock"))
        try:
            with FileLock(lock, timeout=self.index.timeout):
                try:
                    receipt = self._prepare(selection, allow_network, source_artifact)
                except Timeout:
                    raise
                except subprocess.TimeoutExpired, KeyboardInterrupt:
                    receipt = AssetReceipt(
                        selection,
                        ToolResult(
                            "interrupted",
                            None,
                            executed=True,
                            reason="backend_interrupted",
                        ),
                    )
                except AssetError as error:
                    receipt = AssetReceipt(
                        selection,
                        ToolResult("failed", 1, executed=True, reason=error.code),
                    )
                except OSError:
                    receipt = AssetReceipt(
                        selection,
                        ToolResult("unavailable", None, reason="backend_unavailable"),
                    )
                except tarfile.TarError, zipfile.BadZipFile, EOFError, ValueError:
                    receipt = AssetReceipt(
                        selection,
                        ToolResult(
                            "failed", 1, executed=True, reason="invalid_archive"
                        ),
                    )
                self.index.record(receipt)
                return receipt
        except Timeout:
            raise AssetError("index_busy") from None

    def delivery(self, selection, *, policy):
        """Read-only revalidation for a host's existing File/Directory transport."""
        self._check(selection, policy)
        state = self.index.installed(selection)
        if state["status"] != "present":
            raise AssetError(state["reason"])
        archive = self._archive(selection)
        self._verify_source(archive, selection)
        files, entry = self._manifest(archive, selection)
        self._verify_payload(native_asset_directory(self.root, selection), files)
        return NativeAssetDelivery(self._passed(selection, files, reused=True), entry)
