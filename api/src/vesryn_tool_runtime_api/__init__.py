"""Deliver the module's own Python wheel through the existing Dagger boundary."""

import dagger
from dagger import dag, function, object_type


@object_type
class VesrynToolRuntimeApi:
    @function
    def python_package(self, source: dagger.Directory | None = None) -> dagger.File:
        """Build the fixed module revision without installing runtime dependencies."""
        if source is None:
            source = dag.current_module().source().directory("..")
        package = dag.directory().with_directory("src", source.directory("src"))
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            package = package.with_file(name, source.file(name))
        return (
            dag.container()
            .from_("ghcr.io/astral-sh/uv:python3.14-trixie-slim")
            .with_directory("/package", package)
            .with_workdir("/package")
            .with_exec(["uv", "build", "--wheel", "--out-dir", "/dist"])
            .file("/dist/vesryn_tool_runtime-0.4.0-py3-none-any.whl")
        )
