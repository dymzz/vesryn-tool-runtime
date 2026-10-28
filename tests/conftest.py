"""The report's source path is a URL path, not an operating-system path.

The JUnit report is the input of the test-evidence conversion, and the
conversion turns the reported source location into a repository URL. pytest
reports that location with the host's separator, so on Windows the URL would
carry backslashes and resolve to nothing. The plugin's own override states
the location the evidence points at, so every test declares it once, in the
form a URL uses.
"""

from pathlib import Path

import pytest
from ub_test_reports.pytest_plugin import apply_test_metadata


@pytest.fixture(autouse=True)
def _url_shaped_source_path(request, record_property):
    """Declare the test's own source file as a repository-relative URL path."""
    root = Path(request.config.rootpath)
    try:
        relative = Path(request.node.path).resolve().relative_to(root)
    except ValueError:
        return
    apply_test_metadata(
        record_property=record_property,
        metadata={},
        file=relative.as_posix(),
    )
