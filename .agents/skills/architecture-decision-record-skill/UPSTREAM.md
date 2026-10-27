# Upstream provenance

This directory vendors the upstream ADR Skill **verbatim**. The files here are
not authored in this repository: do not edit them by hand and do not keep an
equivalent local rewrite alongside them. A new upstream revision is picked up
by re-vendoring at a new pinned commit (see [Upgrading](#upgrading)).

## Pinned source

| | |
| --- | --- |
| Upstream repository | `https://github.com/architecture-decision-record/architecture-decision-record` |
| Upstream path | `skills/architecture-decision-record-skill/` |
| Pinned commit | `1924d02fcb544b375374354fa0572d315f82ed0b` |
| Commit date | 2026-09-05 |
| Commit subject | Add Claude Code skills and a published website |
| License | CC BY-NC-SA 4.0 — upstream `LICENSE.md`, vendored here as `LICENSE.md` |

The upstream `SKILL.md` credits `joelparkerhenderson/architecture-decision-record`.
Both accounts publish the same history — the identical commit
`aa9d60f912f72847c1a235b809a3c7e53f04e119` was the tip of both at vendoring
time — so the pinned commit resolves under either account.

## Vendored files

| File | Upstream blob SHA-1 |
| --- | --- |
| `SKILL.md` | `450dc4245e5d2ebaf232fb6c4929af377a918343` |
| `reference/templates.md` | `ac8fd6cf3f74b6f2168cf8da89a55481398966c9` |
| `reference/writing-guide.md` | `1bc6ed96c830da2e593ade4990710a91e48ab045` |
| `LICENSE.md` (upstream repository root) | `5711d22a9cf66669d25838e9fe7e2269c385b9dc` |

The first three files are the whole skill: `SKILL.md` references
`reference/templates.md` and `reference/writing-guide.md` and nothing else.
The SHA-1s are git's own object ids, so they verify the vendored bytes
against upstream exactly:

```sh
git hash-object .agents/skills/architecture-decision-record-skill/SKILL.md
```

## Why this path

`.agents/skills/` is the repository-level skill root that the Codex CLI and the
Gemini CLI resolve for a checkout, so one copy serves every host that works in
this repository. A host whose native rule differs (a plugin manifest's `skills`
path field, a linked skill directory) points at **this** directory instead of
copying it; the content is host-agnostic.

## Upgrading

1. Choose the upstream commit to move to. For a content change that is the
   commit that last touched the skill path:

   ```sh
   gh api -X GET "repos/architecture-decision-record/architecture-decision-record/commits?path=skills/architecture-decision-record-skill" \
     --jq '.[] | "\(.sha)  \(.commit.author.date)  \(.commit.message | split("\n")[0])"'
   ```

2. Re-fetch each file at that commit and replace the local copy byte for byte:

   ```sh
   gh api -X GET "repos/architecture-decision-record/architecture-decision-record/contents/<path>?ref=<commit>" \
     --jq .content | base64 -d > .agents/skills/architecture-decision-record-skill/<path>
   ```

3. Update the pinned commit, the date and the blob SHA-1 table above, then
   run `git hash-object` on every vendored file and confirm the values match
   the upstream blob ids.
