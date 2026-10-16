from typing import Annotated

import dagger
from dagger import DefaultPath, Ignore, check, dag, function, object_type

Source = Annotated[
    dagger.Directory,
    DefaultPath("/"),
    Ignore(
        [
            ".git",
            ".venv",
            ".dagger",
            ".test-tools",
            "dist",
            ".env",
            ".env.*",
            ".log",
            ".codex",
            ".agents",
            ".aws",
            ".secrets",
            "**/__pycache__",
            "**/.pytest_cache",
            "**/.ruff_cache",
        ]
    ),
]
PYTHON = "3.14"
TEST_POLICY = {"test_path": "tests"}


@object_type
class VesrynToolRuntimeCi:
    git_token: dagger.Secret

    @function
    @check
    async def lint(self, source: Source) -> None:
        """Check project lint policy."""
        await dag.engineering_ci().python_lint(
            source=source,
            python_version=PYTHON,
            lint_path=".",
            git_token=self.git_token,
        )

    @function
    @check
    async def format_check(self, source: Source) -> None:
        """Check formatting without changing source."""
        await dag.engineering_ci().python_format_check(
            source=source,
            python_version=PYTHON,
            format_path=".",
            git_token=self.git_token,
        )

    @function
    @check
    async def tests(self, source: Source) -> None:
        """Keep the original pytest failure authoritative."""
        await dag.engineering_ci().python_test(
            source=source,
            python_version=PYTHON,
            git_token=self.git_token,
            **TEST_POLICY,
        )

    @function
    async def test_results(self, source: Source) -> dagger.Directory:
        """Export one pytest execution for the Workflow's gate."""
        return await dag.engineering_ci().python_test_artifacts(
            source=source,
            python_version=PYTHON,
            git_token=self.git_token,
            **TEST_POLICY,
        )
