# Test evidence

The test cases that verify a specification, read from a real test report.

The report is written by the project's own test run and converted into
Sphinx-Needs items by `ub-test-reports`. The conversion writes
`.tmp/test-needs.json`, and the report itself stays in `.tmp/junit.xml`. The
three artifacts are separate on purpose: the report is the evidence, the
conversion is a projection of it, and this manual's `needs.json` is a
projection of the documentation.

A test case names the specification it verifies through the `verifies` link,
and the specification names the test cases that verify it in return. The
result of a case — passed, failed, errored or skipped — is the one the report
recorded; a link says which contract a test points at, never that the
contract holds.

```{needimport} ../.tmp/test-needs.json
```
