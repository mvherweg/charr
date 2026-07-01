# 0024. charr-eval discovers manifests from files or directories and names each by its absolute path

- Status: Accepted
- Date: 2026-07-01

## Context

[ADR-0011](0011-dataset-manifest-as-unit.md) made the dataset unit a manifest and said each is reported under a display
name "defaulting to the manifest's filename stem". That naming was a passing detail there; in practice it breaks. The
generator emits one `labels.jsonl` per style-config directory (`config-00/labels.jsonl`, `config-01/labels.jsonl`; see
[ADR-0019](0019-multi-config-style-sweep.md)), so every dataset shares the stem `labels`. Scoring a sweep then merged
all configs into a single per-manifest section (the stem is the group key) - the exact breakdown the per-manifest report
exists to give was lost, and the substrate's `manifest` field could not tell the configs apart either.

Two concerns were tangled through the filesystem path and are better separated:

- **Discovery** - which manifests a run scores. A caller may have a single manifest, several manifests that do not share
  a directory tree, or a dataset root with manifests somewhere beneath it. Passing individual file paths (shell globs)
  covers the first two but is awkward for a tree.
- **Naming** - the label each manifest carries in the report and in the persisted substrate.

Constraints on naming: `charr-eval` must score any conforming dataset and deliberately does not depend on
`charr-datagen` ([ADR-0010](0010-three-packages-eval-drives-charr.md)), so it cannot read the generator's `meta.json`
(where a friendly `config-00` name lives). The manifest format carries no name field and JSONL has no header
([ADR-0012](0012-manifest-encoding-jsonl.md) deferred adding one). And the substrate is a published, portable contract
([ADR-0022](0022-charr-review-package-and-substrate-contract.md)) that `charr-review` displays verbatim, so whatever
string we pick travels with the data.

## Decision

We will split the two concerns.

- **Discovery: accept files or directories.** A path argument that is a file is scored as one manifest (it need not be
  named `labels.jsonl` - an explicit file is trusted). A path argument that is a directory is searched recursively for
  `labels.jsonl` files (filtered to real files, so a directory or broken symlink named `labels.jsonl` is ignored).
  Results are deduplicated by resolved path and returned in a deterministic (sorted) order. This covers a single
  manifest, several unrelated manifests, and a dataset root, without forcing any particular layout.
- **Naming: each manifest is its resolved absolute path.** The label is computed by one small function at the CLI
  boundary and passed into the runner, so naming policy lives in a single place and the runner does not derive it.

Alternatives considered:

- **Filename stem** (ADR-0011's original): rejected - collides whenever datasets share the conventional `labels.jsonl`
  name, which the generator always produces.
- **Immediate parent-directory name** (e.g. `config-00`): rejected - drops higher path components and still collides
  across separate trees (`runA/config-00/labels.jsonl` vs `runB/config-00/labels.jsonl`).
- **cwd-relative path**: readable and leak-free, but run-dependent (the same manifest gets different names from
  different working directories), so not unambiguous.
- **Directories-only discovery**: rejected - too narrow; a provider may keep several manifests that do not share a tree.
- **A provider-declared dataset name** (the dataset states its own identity): the desired end state, but it needs a
  dataset-contract change (a JSONL header record or a sibling descriptor file, both deferred by ADR-0012) and must stay
  tool-agnostic. Deferred as future work in issue #31; the naming function here is the isolated seam it will replace.

## Consequences

- Pointing `charr-eval` at a dataset root (`charr-eval ./datasets/`) scores every manifest under it; distinct datasets
  never merge in the report, and `charr-review` can separate them.
- Naming policy is a single swappable function, so adopting a provider-declared name later (issue #31) is a local
  change.
- Accepted downside: an absolute path is verbose in the report and bakes machine/home paths into the portable substrate
  (ADR-0022), shown verbatim in `charr-review`. It is unambiguous today but not stable across machines or if the dataset
  moves - a placeholder we accept until issue #31.
- This refines ADR-0011's naming and "pointed at" wording; it does not supersede it - the manifest-as-unit decision
  stands.
