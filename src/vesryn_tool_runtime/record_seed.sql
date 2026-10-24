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

-- Pytest-timeout: abort hanging tests
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('pytest-timeout', 'pytest-timeout', 'uv', 'pytest-timeout', 'pytest');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('pytest-timeout', '2.4.0', NULL, NULL, NULL, '>=3.7',
   'https://files.pythonhosted.org/packages/fa/b6/3127540ecdf1464a00e5a01ee60a1b09175f6913f0644ac748494d9c4b21/pytest_timeout-2.4.0-py3-none-any.whl',
   'sha256',
   'c42667e5cdadb151aeb5b26d114aff6bdf5a907f176a007a30b940d3d865b5c2');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'pytest-timeout', 'Abort hanging tests after a specified timeout duration');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'pytest-timeout', 'timeout'),
  ('ci-quality', 'pytest-timeout', 'pytest-timeout');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('pytest-timeout.run', 'pytest-timeout', 'uv', 'pytest -p pytest_timeout',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Execute test suite with timeout guard against hangs');

-- Pytest-randomly: randomize test order to catch state-dependent failures
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('pytest-randomly', 'pytest-randomly', 'uv', 'pytest-randomly', 'pytest');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('pytest-randomly', '5.0.0', NULL, NULL, NULL, '>=3.10',
   'https://files.pythonhosted.org/packages/10/b4/47e939285caad9a623d021512912ac08dc92a467ad075d179f43729d2934/pytest_randomly-5.0.0-py3-none-any.whl',
   'sha256',
   '8a0d4703115c0c25b38b6e129fc16b1947b9643ff26a41bc1d185d7e5a7689c1');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'pytest-randomly', 'Randomize test execution order to detect order-dependent test failures');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'pytest-randomly', 'randomly'),
  ('ci-quality', 'pytest-randomly', 'random-test'),
  ('ci-quality', 'pytest-randomly', 'pytest-randomly');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('pytest-randomly.run', 'pytest-randomly', 'uv', 'pytest -p randomly',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Execute test suite with randomized ordering');

-- Pytest-xdist: parallelize tests across CPU cores
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('pytest-xdist', 'pytest-xdist', 'uv', 'pytest-xdist', 'pytest');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('pytest-xdist', '3.8.0', NULL, NULL, NULL, '>=3.9',
   'https://files.pythonhosted.org/packages/ca/31/d4e37e9e550c2b92a9cbc2e4d0b7420a27224968580b5a447f420847c975/pytest_xdist-3.8.0-py3-none-any.whl',
   'sha256',
   '202ca578cfeb7370784a8c33d6d05bc6e13b4f25b5053c30a152269fd10f0b88');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'pytest-xdist', 'Parallelize pytest execution across multiple CPU cores or workers');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'pytest-xdist', 'xdist'),
  ('ci-quality', 'pytest-xdist', 'parallel'),
  ('ci-quality', 'pytest-xdist', 'pytest-xdist');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('pytest-xdist.run', 'pytest-xdist', 'uv', 'pytest -n auto',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Execute test suite in parallel across available CPU cores');

-- Beartype: zero-cost runtime type checking
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('beartype', 'beartype', 'uv', 'beartype', 'python');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('beartype', '0.23.1', NULL, NULL, NULL, '>=3.10',
   'https://files.pythonhosted.org/packages/1c/cb/2f6aa982e2860c1156830db3da7f823b71784ed7d533ca289ea9b6c6347a/beartype-0.23.1-py3-none-any.whl',
   'sha256',
   '4461b4dc57e3fdd6c8a8464b22cf118002eea107c33e9fef651c69068ab3cce3');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'beartype', 'Zero-cost runtime type checking and validation for Python');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'beartype', 'runtime-type-check'),
  ('ci-quality', 'beartype', 'type-guard'),
  ('ci-quality', 'beartype', 'beartype');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('beartype.claw', 'beartype', 'uv', 'python -c "import beartype.claw; beartype.claw.beartype_all()"',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Activate runtime type-checking hook across imported packages');

-- Typeguard: runtime type checking and validation for pytest
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('typeguard', 'typeguard', 'uv', 'typeguard', 'pytest');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('typeguard', '4.6.0', NULL, NULL, NULL, '>=3.10',
   'https://files.pythonhosted.org/packages/8f/eb/461d5f167b6f5c7d97696f397c82f82e3480e003fce3f0a1cd1dd26e2eb2/typeguard-4.6.0-py3-none-any.whl',
   'sha256',
   '79878165bb86f2cf5d41d159a0ff1792a796cf496882d2fe1b1c6c7049b9cdd7');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'typeguard', 'Runtime type checking and validation during test execution');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'typeguard', 'typeguard'),
  ('ci-quality', 'typeguard', 'type-check');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('typeguard.pytest', 'typeguard', 'uv', 'pytest --typeguard-packages=:all:',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Run test suite with Typeguard runtime type checking instrumentation');

-- Pytest-cov: test coverage measurement for pytest
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('pytest-cov', 'pytest-cov', 'uv', 'pytest-cov', 'pytest');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('pytest-cov', '7.1.0', NULL, NULL, NULL, '>=3.9',
   'https://files.pythonhosted.org/packages/9d/7a/d968e294073affff457b041c2be9868a40c1c71f4a35fcc1e45e5493067b/pytest_cov-7.1.0-py3-none-any.whl',
   'sha256',
   'a0461110b7865f9a271aa1b51e516c9a95de9d696734a2f71e3e78f46e1d4678');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'pytest-cov', 'Measure code coverage during pytest execution');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'pytest-cov', 'coverage'),
  ('ci-quality', 'pytest-cov', 'cov'),
  ('ci-quality', 'pytest-cov', 'pytest-cov');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('pytest-cov.run', 'pytest-cov', 'uv', 'pytest --cov',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Execute test suite and generate test coverage reporting');

-- Memray: memory profiler for Python
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('memray', 'memray', 'uv', 'memray', 'memray');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('memray', '1.20.0', 'linux', 'x86_64', 'gnu', '>=3.11',
   'https://files.pythonhosted.org/packages/99/20/3ed35c62736666602c8f025f9c8fc5651effb710f1e03bb142071e06ec57/memray-1.20.0-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl',
   'sha256',
   '53231e49d55b10ac10ac8739a2592230f0794320892756f957e0026f99f38618'),
  ('memray', '1.20.0', NULL, NULL, NULL, '>=3.9.0',
   'https://files.pythonhosted.org/packages/99/3b/8f9736cbf698e62cb7efb0e1715a30d6d06b3cffd980b435209eb522d5f8/memray-1.20.0.tar.gz',
   'sha256',
   'ce1f1d900948d57d7db5b5d8d81f4ebfcb798eff674493503ce5bfaafcea84dc');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'memray', 'Memory profiler for Python to track and inspect allocations');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'memray', 'memory-profiler'),
  ('ci-quality', 'memray', 'mem-profile'),
  ('ci-quality', 'memray', 'memray');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('memray.run', 'memray', 'uv', 'memray run',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Profile memory allocations of a Python application or script');

-- Py-spy: sampling profiler for Python programs
INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('py-spy', 'py-spy', 'uv', 'py-spy', 'py-spy');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('py-spy', '0.4.2', 'windows', 'x86_64', 'msvc',
   '>=3.7',
   'https://files.pythonhosted.org/packages/6f/ed/1409cdb557e558a6c98003ab12fdd4284699e158c167c187cb0f124eea4c/py_spy-0.4.2-py2.py3-none-win_amd64.whl',
   'sha256',
   '8b06a353c177677e4e1701b288d8c58e2f8d4208ee81a8048d9f72ba800918f8'),
  ('py-spy', '0.4.2', 'linux', 'x86_64', 'gnu',
   '>=3.7',
   'https://files.pythonhosted.org/packages/f9/34/dd7d3c763a00b7b965e25a5eab0acd1a345dbaf0f45fffe595278873a1c0/py_spy-0.4.2-py2.py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.whl',
   'sha256',
   'aeb0323409199c785f730645e9f4bb7a7b9ca2c481f2c331a55642b5d13fa52f');

INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES
  ('ci-quality', 'py-spy', 'Sampling profiler for Python programs with low overhead');

INSERT INTO tool_group_member_alias (group_id, tool_id, alias) VALUES
  ('ci-quality', 'py-spy', 'pyspy'),
  ('ci-quality', 'py-spy', 'profiler'),
  ('ci-quality', 'py-spy', 'py-spy');

INSERT INTO tool_access
  (access_id, tool_id, method, target, contract, summary)
VALUES
  ('py-spy.record', 'py-spy', 'uv', 'py-spy record',
   '{"input_schema": {"type": "object"}, "output_schema": {"type": "object"}}',
   'Sample and generate flamegraph profiling records for Python processes');

-- Migrated from the retired shared_assets declarations (issue #32).
-- Sources/digests are the verified publisher values; the old JSON
-- files are historical inputs, not a second live source.

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('ripgrep', 'ripgrep', 'github-release', NULL, 'rg.exe');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('ripgrep', '15.2.0', 'windows', 'aarch64', 'msvc',
   NULL,
   'https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/ripgrep-15.2.0-aarch64-pc-windows-msvc.zip',
   'sha256',
   'e4abca10c3a64ebea742667dd7009449d49403db5460dd6873e389fa2945360f');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('hyperfine', 'hyperfine', 'github-release', NULL, 'hyperfine');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('hyperfine', '2.0.0', 'windows', 'x86_64', 'msvc',
   NULL,
   'https://github.com/sharkdp/hyperfine/releases/download/v2.0.0/hyperfine-v2.0.0-x86_64-pc-windows-msvc.zip',
   'sha256',
   '3dec51acee1060908e67948838d6bc0a7aacde0774acebfa4afb220dcf0bc078'),
  ('hyperfine', '2.0.0', 'linux', 'x86_64', 'gnu',
   NULL,
   'https://github.com/sharkdp/hyperfine/releases/download/v2.0.0/hyperfine-v2.0.0-x86_64-unknown-linux-gnu.tar.gz',
   'sha256',
   'ae2beda2ac99c098427e4f755244552daf20e514422889cca6d44421e2d93c87'),
  ('hyperfine', '1.20.0', 'windows', 'x86_64', 'msvc',
   NULL,
   'https://github.com/sharkdp/hyperfine/releases/download/v1.20.0/hyperfine-v1.20.0-x86_64-pc-windows-msvc.zip',
   'sha256',
   '2508c549b049b1d4342d08edc1cb42bfac169082b6e3069431b5bab9822dbb32'),
  ('hyperfine', '1.20.0', 'linux', 'x86_64', 'gnu',
   NULL,
   'https://github.com/sharkdp/hyperfine/releases/download/v1.20.0/hyperfine-v1.20.0-x86_64-unknown-linux-gnu.tar.gz',
   'sha256',
   '63ad53934062118f5b0be11785e0bb1603d4b91667d1921f2fd8df9a8712040a');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('osv-scanner', 'osv-scanner', 'github-release', NULL, 'osv-scanner');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('osv-scanner', '2.6.0', 'linux', 'x86_64', NULL,
   NULL,
   'https://github.com/google/osv-scanner/releases/download/v2.6.0/osv-scanner_linux_amd64',
   'sha256',
   'ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('actionlint', 'actionlint', 'github-release', NULL, 'actionlint');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('actionlint', '1.7.12', 'linux', 'x86_64', NULL,
   NULL,
   'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz',
   'sha256',
   '8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('shellcheck', 'shellcheck', 'github-release', NULL, 'shellcheck');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('shellcheck', '0.11.0', 'linux', 'x86_64', NULL,
   NULL,
   'https://github.com/koalaman/shellcheck/releases/download/v0.11.0/shellcheck-v0.11.0.linux.x86_64.tar.xz',
   'sha256',
   '8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('zizmor', 'zizmor', 'github-release', NULL, 'zizmor');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('zizmor', '1.31.1', 'linux', 'x86_64', 'gnu',
   NULL,
   'https://github.com/woodruffw/zizmor/releases/download/v1.31.1/zizmor-x86_64-unknown-linux-gnu.tar.gz',
   'sha256',
   'd185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('semgrep', 'semgrep', 'oci', NULL, 'semgrep');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('semgrep', '1.99.0', 'linux', 'x86_64', NULL,
   NULL,
   'docker.io/semgrep/semgrep@sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d',
   'sha256',
   '374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d'),
  ('semgrep', '1.99.0', 'linux', 'aarch64', NULL,
   NULL,
   'docker.io/semgrep/semgrep@sha256:08f1c44024049d1a104f57203dab60b3579f17a12fe87bac7bb60130bbc46bfc',
   'sha256',
   '08f1c44024049d1a104f57203dab60b3579f17a12fe87bac7bb60130bbc46bfc');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('lychee', 'lychee', 'oci', NULL, 'lychee');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('lychee', '0.18.0', 'linux', 'x86_64', NULL,
   NULL,
   'docker.io/lycheeverse/lychee@sha256:606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8',
   'sha256',
   '606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8'),
  ('lychee', '0.18.0', 'linux', 'aarch64', NULL,
   NULL,
   'docker.io/lycheeverse/lychee@sha256:b1be296f112676caac52748c7f692eacde9a26fa23f8715b5662af9ad7dd451c',
   'sha256',
   'b1be296f112676caac52748c7f692eacde9a26fa23f8715b5662af9ad7dd451c');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('pyright', 'pyright', 'uv', 'pyright', 'pyright');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('pyright', '1.1.414', NULL, NULL, NULL,
   '>=3.7',
   'https://files.pythonhosted.org/packages/d7/ba/18b6e682ead424ad24bcc134339ae5d1b931cd9ae260540592a058a91279/pyright-1.1.414-py3-none-any.whl',
   'sha256',
   '2a6b4b3298c9eec174c5ed83bd338de6eee82df2992f3e1930e6199d381be36f');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('deptry', 'deptry', 'uv', 'deptry', 'deptry');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('deptry', '0.25.1', 'linux', 'x86_64', 'gnu',
   '>=3.10',
   'https://files.pythonhosted.org/packages/72/9c/6f6f9125bac74b5d5d2af89536cbdb3fa159b6466aa097b74e7e85e8e030/deptry-0.25.1-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl',
   'sha256',
   '14bfcc28b4326ed8c6abb30691b19077d4ef8613cfba6c37ef5b1f471775bf6f');

INSERT INTO tool_asset (tool_id, name, provider, package, entrypoint) VALUES
  ('pylint', 'pylint', 'uv', 'pylint', 'pylint');

INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('pylint', '4.1.3', NULL, NULL, NULL,
   '>=3.10.0',
   'https://files.pythonhosted.org/packages/3f/ba/62b18e2e157d05f976bd490b349b55d8850c2a454a5c313c91af9d2e0baf/pylint-4.1.3-py3-none-any.whl',
   'sha256',
   'a85357cae24f33ad8d86c8f3daaa92c600ae4012b54a57299cee76000e9364cf');

-- vulture: the still-used 2.14 release joins the live declaration
-- (official PyPI url/digest, interpreter floor >=3.8).
INSERT INTO tool_release
  (tool_id, version, platform_os, platform_arch, platform_abi,
   platform_python, source, digest_type, digest)
VALUES
  ('vulture', '2.14', NULL, NULL, NULL,
   '>=3.8',
   'https://files.pythonhosted.org/packages/a0/56/0cc15b8ff2613c1d5c3dc1f3f576ede1c43868c1bc2e5ccaa2d4bcd7974d/vulture-2.14-py2.py3-none-any.whl',
   'sha256',
   'd9a90dba89607489548a49d557f8bac8112bd25d3cbc8aeef23e860811bd5ed9');
