-- Seed records for the issue #27 literal examples.
-- Loaded after record_schema.sql to build data/records.sqlite3.

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('trivy', 'trivy', 'github-release', NULL, 'trivy');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, source, digest_type, digest)
VALUES
  ('trivy', '0.76.1', 'linux', 'x86_64',
   'https://github.com/aquasecurity/trivy/releases/download/v0.76.1/trivy_0.76.1_Linux-64bit.tar.gz',
   'sha256',
   'c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0');

INSERT INTO tool_group (group_id, summary) VALUES
  ('ci-security', 'Security gates for CI'),
  ('ci-release', 'Release readiness checks');

-- The same trivy keeps one tool_id with group-specific purpose text and
-- member-level aliases in each group.
INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-security', 'trivy', 'Vulnerability and configuration scanning'),
  ('ci-release', 'trivy', 'SBOM generation');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-security', 'trivy', 'vuln'),
  ('ci-release', 'trivy', 'sbom');

-- Three distinct entries of one tool, each with its own method, target and
-- contract.
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('vulture', 'vulture', 'uv', 'vulture', 'vulture');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('vulture', '2.16', NULL, NULL, NULL, '>=3.9',
   'https://files.pythonhosted.org/packages/f5/be/f935130312330614811dae2ea9df3f395f6d63889eb6c2e68c14507152ee/vulture-2.16-py3-none-any.whl',
   'sha256',
   '6e0f1c312cef1c87856957e5c2ca9608834a7c794c2180477f30bf0e4cc58eee');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('trivy.scan', 'trivy', 'native', 'trivy scan --exit-code 1',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Vulnerability and configuration scan'),
  ('trivy.sbom', 'trivy', 'dagger', 'engineering_ci.security_sbom',
   '{"dagger": "security_sbom", "args": {"format": "spdx"}}',
   'Generate an SBOM for the release artifact'),
  ('trivy.cli', 'trivy', 'uv', 'trivy',
   '{"input_schema": {"type": "object"}, "passthrough": true}',
   'Direct trivy CLI entry for ad-hoc use');

-- Import Linter: architecture and import boundary enforcement
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('import-linter', 'import-linter', 'uv', 'import-linter', 'lint-imports');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('import-linter', '2.15', NULL, NULL, NULL, '>=3.10',
   'https://files.pythonhosted.org/packages/08/31/4571c20652a4002ed9e500046386f3731a77e23d95a608ae8a87f1fbb2da/import_linter-2.15-py3-none-any.whl',
   'sha256',
   '9aaf16a88ac1e99d5a464cd7f66b6a05f7060bfa761162e0ed441773a267ed3b');

INSERT INTO tool_group (group_id, summary) VALUES
  ('ci-quality', 'Code architecture and quality checks');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'import-linter', 'Lint Python architecture and enforce import boundaries');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'import-linter', 'import-lint'),
  ('ci-quality', 'import-linter', 'imports');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('import-linter.check', 'import-linter', 'uv', 'lint-imports',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Verify project modular architecture and import contracts');

-- Hypothesis: property-based testing and automated test generation
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('hypothesis', 'hypothesis', 'uv', 'hypothesis', 'hypothesis');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('hypothesis', '6.170.9', 'linux', 'x86_64', 'gnu', '>=3.11',
   'https://files.pythonhosted.org/packages/5a/25/1fe15a20048e53dab3a5a9491e8c0c614c001118e603a194ec65a293ece2/hypothesis-6.170.9-cp311-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl',
   'sha256',
   '89f09c589692a71686d9e42272fed3805e091bcbc1193d1873d1d5875d619c88'),
  ('hypothesis', '6.170.9', NULL, NULL, NULL, '>=3.11',
   'https://files.pythonhosted.org/packages/55/c9/c13716786de078854312d651cebf514ad909a5aef8a9cdd86c738a3962d6/hypothesis-6.170.9.tar.gz',
   'sha256',
   '72fd7e6571aaf47439bda2292156a8b86c9afc83aa59b47e8857557576fa8be2');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'hypothesis', 'Property-based testing and automated test generation');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'hypothesis', 'property-test'),
  ('ci-quality', 'hypothesis', 'fuzz');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('hypothesis.cli', 'hypothesis', 'uv', 'hypothesis',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Hypothesis property-based testing and codemod tool');

-- Mutmut: Python mutation testing
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('mutmut', 'mutmut', 'uv', 'mutmut', 'mutmut');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('mutmut', '3.8.0', NULL, NULL, NULL, '>=3.10',
   'https://files.pythonhosted.org/packages/66/2a/a9904a45804c1de50c0c3baad1512b78d5b66d2befd841104b8a62bf0f35/mutmut-3.8.0-py3-none-any.whl',
   'sha256',
   '4c0abcef6b8d1116f2adfaad19df12e1c621e4a402d4367ef15bf8cba497b91d');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'mutmut', 'Mutation testing to find test suite blind spots');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'mutmut', 'mutation-test'),
  ('ci-quality', 'mutmut', 'mutation');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('mutmut.run', 'mutmut', 'uv', 'mutmut run',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Run mutation testing on target modules');

-- Schemathesis: adaptive API testing for OpenAPI and GraphQL
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('schemathesis', 'schemathesis', 'uv', 'schemathesis', 'schemathesis');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('schemathesis', '4.32.4', NULL, NULL, NULL, '>=3.11',
   'https://files.pythonhosted.org/packages/52/04/d21a6dccdc8146b1c29c2274de5408067ed18ade77cf48dbd3a1a3688b07/schemathesis-4.32.4-py3-none-any.whl',
   'sha256',
   '61e3c4868e6385da0ae49acb55519527a8025172ae405ef5f87ccc4c1dc539ec');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'schemathesis', 'Property-based API contract and conformance testing for OpenAPI/GraphQL');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'schemathesis', 'api-test'),
  ('ci-quality', 'schemathesis', 'openapi-test'),
  ('ci-quality', 'schemathesis', 'st');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('schemathesis.run', 'schemathesis', 'uv', 'schemathesis run',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Run automated property-based API testing against schemas');




