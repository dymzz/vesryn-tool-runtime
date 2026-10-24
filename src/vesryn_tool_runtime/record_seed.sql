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
