# Release note candidates from Git

This describes the input and projection for future release notes. It does not
publish a release or replace the [release readiness criteria](release-readiness.md).
The checked-in [configuration](../../cliff.toml) uses git-cliff 2.14.2's native
commit parser, footers and Tera template. Its output is a **candidate** until
the final tree and delivery evidence have been reviewed.

## Delivery facts and history

The final commit on the main branch is the source of a delivery statement. A
PR description and branch commits can explain development, but do not alone
prove what the final merge delivered. Continue using Conventional Commits during
development; an intermediate commit does not need a public release note.

When an impact is confirmed for the commit that will actually reach main, add
`Release-Note: <user-facing impact>` as a final commit footer. Use the native
Conventional Commit `!` or `BREAKING CHANGE: <migration impact>` for an explicit
breaking change. A footer is a statement about that commit, not proof that the
change remains in a later release: check the target tree and subsequent commits.
Unconfirmed effects stay unconfirmed. The parser cannot infer every breaking
change or all user impacts.

The projection considers only the first-parent commits in the chosen range:

- A squash merge keeps the final squash commit's subject and footers, not the
  intermediate branch commits. Hosting services can copy branch messages into
  the squash body, so review that final message and its footers rather than
  assuming copied text is a confirmed delivery statement.
- An ordinary merge keeps the merge commit. A standard `Merge ...` subject is
  normalized for git-cliff's Conventional Commit parser, so footers at the end
  of that merge message are available. Put a breaking description in its
  `BREAKING CHANGE:` footer; a `feat!:` or `fix!:` line embedded in the merge
  body is not the merge commit's Conventional Commit subject.
- A rebase keeps each rebased commit on the first-parent chain. A note on one of
  those commits may still be reverted or superseded by a later commit.

Git and git-cliff cannot determine all net user-visible effects from commit
messages. Review the candidate against the fixed target, including reverts,
partial reverts and replacements. Pass the full SHA of every no-longer-delivered
first-parent entry via git-cliff's `--skip-commit`; do not publish a candidate
that still claims a withdrawn change. This also applies to breaking-change
entries. A revert commit need not name all the effects it reverses, and a revert
of a revert can restore them, so there is no automatic net-change claim here.

## Existing release boundary

The [v0.4.0 GitHub Release](https://github.com/dymzz/vesryn-tool-runtime/releases/tag/v0.4.0)
is the historical authority for its notes, artifacts and attached provenance.
Its annotated tag resolves to `0384f4a2f2278a130a1a95efd9f714caf9f77a74`;
the provenance identifies the same source and
[CI run 40687914023](https://github.com/dymzz/vesryn-tool-runtime/actions/runs/40687914023).
That tagged source was merged as a second parent; it is not an entry on main's
first-parent chain. Replaying that historical source range is different from
selecting a future release target on main.
The existing [changelog](../changelog.md) preserves historical migration and
compatibility facts that cannot be reconstructed from commit messages.

The historical range `v0.3.1..v0.4.0` contains 85 commits, 14 on its
first-parent chain. It includes squash and ordinary merge commits; a breaking
footer is present on a side-branch commit, while a first-parent merge includes
`fix(host-tools)!:` in its body rather than its subject. There is no
`Release-Note:` footer or revert commit in that range. The first-parent
projection therefore cannot recover the published migration assessment. Do not
rewrite the historical release or invent footers to fill that gap.

Tool Runtime's existing CI calls a pinned engineering-ci reusable workflow and
retains its distribution and acceptance artifacts. The v0.4.0 notes and assets
were published through the existing GitHub Release; `gh release` supports a
notes file. Separately, engineering-ci's
[own release workflow](https://github.com/dymzz/engineering-ci/blob/c40fb6996548ec1ce2e3a6555771baf2b4d3762c/.github/workflows/release.yml)
generates GitHub automatic notes and owns its own Manifest, tag conflict and
Draft recovery checks. Its existence does not mean that workflow published
Tool Runtime v0.4.0: this repository currently has a CI workflow but no release
workflow that automatically applies those engineering-ci guards. Connecting a
single reviewed notes source to the actual future publisher and its safeguards
is a separate integration step; this projection creates no publisher, tag or
release.

## Generate for a fixed range

Run these PowerShell commands from the repository root. This example projects
the already merged `3409f8b` commit with an illustrative `v0.4.1` label for
inspection; it does not assert that the package version or release readiness
matches that label. For a future candidate, provide the previous release tag
and its known commit, a **full fixed target commit SHA**, and the proposed version. The target
must be the actual accepted main-branch commit before publication. Do not use
`HEAD`, a moving branch name, or a candidate branch commit as proof of delivery.
Refresh `origin/main` before selecting a future target and retain the resolved
main snapshot with the delivery evidence. The offline check below prefers that
remote-tracking reference over a potentially diverged local main branch; the
publisher still owns the final check against the live main head.

The script uses Git to select first-parent SHAs and git-cliff's native
`--skip-commit` to omit the other commits. It does not parse commit messages or
generate notes itself. The git-cliff 2.14.2 CLI does not expose a first-parent
option; native support would avoid passing one exclusion per side-branch commit.
`ignore_tags` in the configuration prevents unrelated tags, including local
backup tags, from splitting this explicitly selected range. The supplied version
labels the single candidate.

```powershell
$baseTag = 'v0.4.0'
$baseSha = '0384f4a2f2278a130a1a95efd9f714caf9f77a74'
$targetSha = '3409f8baa89a8e936b174acb5d47d659bb415b92'
$version = 'v0.4.1'
# Full first-parent SHAs withdrawn or superseded after review of the target tree.
$omitted = @()

if ($baseSha -notmatch '^[0-9a-f]{40}$' -or $targetSha -notmatch '^[0-9a-f]{40}$') {
    throw 'Use full lowercase commit SHAs for the base and target.'
}
if ($version -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$') {
    throw 'Use an explicit version tag such as v0.4.0.'
}
$actualBase = git rev-parse --verify --quiet "refs/tags/${baseTag}^{commit}"
if ($LASTEXITCODE -ne 0 -or $actualBase -ne $baseSha) {
    throw 'Base tag is missing or does not resolve to the expected commit.'
}
$actualTarget = git rev-parse --verify --quiet "${targetSha}^{commit}"
if ($LASTEXITCODE -ne 0 -or $actualTarget -ne $targetSha) {
    throw 'Target commit is missing or does not resolve to the supplied SHA.'
}
git show-ref --verify --quiet "refs/tags/$version"
if ($LASTEXITCODE -eq 0) {
    $existingTarget = git rev-parse --verify --quiet "refs/tags/${version}^{commit}"
    if ($LASTEXITCODE -ne 0 -or $existingTarget -ne $targetSha) {
        throw 'Version tag already exists and points to a different target.'
    }
} elseif ($LASTEXITCODE -ne 1) {
    throw 'Could not check the version tag.'
}
git merge-base --is-ancestor $baseSha $targetSha
if ($LASTEXITCODE -ne 0 -or $baseSha -eq $targetSha) {
    throw 'The base must be an ancestor of a distinct target commit.'
}
# Reachability also admits intermediate side-branch commits. The target must
# be on main's first-parent chain so its own chain is the delivery history.
$mainRef = 'refs/remotes/origin/main'
git show-ref --verify --quiet $mainRef
if ($LASTEXITCODE -eq 1) {
    $mainRef = 'refs/heads/main'
} elseif ($LASTEXITCODE -ne 0) {
    throw 'Could not check the main branch reference.'
}
$mainSnapshot = git rev-parse --verify --quiet "${mainRef}^{commit}"
if ($LASTEXITCODE -ne 0) {
    throw 'No main branch reference is available to verify the target commit.'
}
$mainFirstParents = @(git rev-list --first-parent $mainSnapshot)
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate main first-parent commits.' }
if ($targetSha -notin $mainFirstParents) {
    throw "The target commit is not on the main first-parent chain: $targetSha"
}
$range = "$baseSha..$targetSha"
$firstParents = @(git rev-list --first-parent $range)
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate first-parent commits.' }
$all = @(git rev-list $range)
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate the fixed range.' }
$skipArgs = @()
foreach ($sha in $all) {
    if ($sha -notin $firstParents) { $skipArgs += '--skip-commit', $sha }
}
foreach ($sha in $omitted) {
    if ($sha -notmatch '^[0-9a-f]{40}$' -or $sha -notin $firstParents) {
        throw "Reviewed exclusion is not a first-parent SHA in the range: $sha"
    }
    $skipArgs += '--skip-commit', $sha
}

# Avoid machine-specific git-cliff configuration overrides.
Get-ChildItem Env: | Where-Object Name -like 'GIT_CLIFF*' | ForEach-Object {
    Remove-Item -LiteralPath "Env:$($_.Name)"
}
New-Item -ItemType Directory -Force .tmp/issue60 | Out-Null
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.tmp/issue60/uv-cache'
$env:UV_TOOL_DIR = Join-Path (Get-Location) '.tmp/issue60/uv-tools'
uvx --from git-cliff==2.14.2 git-cliff --config cliff.toml --offline --no-exec `
    --tag $version @skipArgs --output .tmp/issue60/release-notes.md -- $range
if ($LASTEXITCODE -ne 0) { throw 'git-cliff could not generate the candidate.' }
```

`uvx` is uv's existing native tool runner, not a project-specific installer or
registry. It resolves the pinned version if it is not cached. The generated
file and cache are temporary, under `.tmp/`. Keep the fixed inputs, reviewed
exclusions and configuration with the delivery evidence so the same result can
be regenerated. A missing tag or commit, non-ancestor range and invalid TOML
must fail with a diagnostic; generation alone is not a release decision.

See git-cliff's [command options](https://git-cliff.org/docs/usage/args/) and
[template context](https://git-cliff.org/docs/templating/context/) for its
native range, footer and breaking-change behavior.

### Replay the historical source range

The pre-P5 v0.4.0 tag identifies a merged branch source. Keep its original
`v0.3.1..v0.4.0` range for a retrospective parser exercise, rather than
weakening the future-target check above. After preparing the pinned runner as
above, run this separate read-only replay from the repository root:

```powershell
$historyBase = git rev-parse --verify --quiet 'refs/tags/v0.3.1^{commit}'
if ($LASTEXITCODE -ne 0 -or $historyBase -ne 'adc11947632a284a43296092d8f7a41acd2953c3') {
    throw 'Historical v0.3.1 tag is missing or has a different target.'
}
$historyTarget = git rev-parse --verify --quiet 'refs/tags/v0.4.0^{commit}'
if ($LASTEXITCODE -ne 0 -or $historyTarget -ne '0384f4a2f2278a130a1a95efd9f714caf9f77a74') {
    throw 'Historical v0.4.0 tag is missing or has a different target.'
}
$historyRange = "$historyBase..$historyTarget"
$historyFirstParents = @(git rev-list --first-parent $historyRange)
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate the historical source chain.' }
$historyAll = @(git rev-list $historyRange)
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate the historical range.' }
$historySkipArgs = @()
foreach ($sha in $historyAll) {
    if ($sha -notin $historyFirstParents) { $historySkipArgs += '--skip-commit', $sha }
}
uvx --from git-cliff==2.14.2 git-cliff --config cliff.toml --offline --no-exec `
    --tag v0.4.0 @historySkipArgs --output .tmp/issue60/historical-release-notes.md -- $historyRange
if ($LASTEXITCODE -ne 0) { throw 'Historical git-cliff replay failed.' }
```

This range has no usable first-parent release-note or breaking-change footers,
so its candidate sections are empty. The existing changelog, published notes
and provenance retain the migration and compatibility facts.

## Consume the candidate at the release entry

The generated file is the publisher's input in `gh`'s own shape: both
`gh release create --notes-file <file>` and `gh release edit --notes-file
<file>` read the release notes from a file. This repository therefore
delivers its git-cliff configuration and this output contract, and nothing
more: it creates no publisher, no tag manager, no manifest and no release
state machine, and it does not embed the engineering-ci release workflow.

A non-publishing notes-input rehearsal can run the real `gh` commands against
a local API fixture and compare the submitted `body` and readback with the
generated UTF-8 file. `--draft` still writes a GitHub Draft and can create a
tag, so it is not a no-write mode. A local rehearsal proves file consumption;
it does not exercise live publication permissions or the publisher's gates.

The publisher keeps everything it already owns — the version and SHA checks,
the [Release Readiness](release-readiness.md) C1–C8 assessment, the formal CI
evidence, the tag conflict protection, the Draft recovery, the artifact and
manifest verification and the publication permission. Generating a candidate
is not a release decision, and a successful generation says nothing about
whether the release may be published.

One confirmed source produces the release notes. The publisher applies the
reviewed file as the release notes and does not add GitHub's automatic notes
(`--generate-notes`) or the annotated tag's text (`--notes-from-tag`) to the
same release: two sources make two different statements about what was
delivered. If the publishing workflow currently emits automatic notes,
replacing them with this file is the minimal interface change, and it belongs
to the engineering-ci task that owns that workflow.
