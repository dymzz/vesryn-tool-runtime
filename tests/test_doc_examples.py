"""The manual's self-contained Python examples are executed, not only shown.

Issue #51 P2.4: an example in the public manual is a contract, so the ones
that need nothing but the package are run here. The examples that talk to the
host — tool preparation, Dagger delivery — carry the `python .skip` marker in
the page and are left to the reader. The planning documents under
`superpowers/` are not part of the public manual and are not collected.
"""

import pytest
from pytest_examples import EvalExample, find_examples

PAGES = ("README.md", "docs")

EXAMPLES = [
    example
    for example in find_examples(*PAGES)
    if "skip" not in example.prefix_tags() and "superpowers" not in example.path.parts
]


@pytest.mark.parametrize(
    "example", EXAMPLES, ids=[f"{e.path.as_posix()}:{e.start_line}" for e in EXAMPLES]
)
def test_documented_example_runs(example, eval_example: EvalExample):
    eval_example.run(example)
    eval_example.lint(example)
