# 0013. Render with matplotlib, seaborn, and plotly; plotly via an optional, graceful backend

- Status: Accepted
- Date: 2026-06-28

## Context

`charr-datagen` synthesizes labeled charts to exercise the checker. It needs rendering backends, and the checker is a
vision model, so the *visual* variety of those backends matters: covering more than one library tests the checker
against real differences in defaults, fonts, palettes, gridlines, and legend placement instead of a single house style.

The most common Python plotting libraries are matplotlib, seaborn, and plotly. seaborn renders through matplotlib (a
styling layer over the same Figure and the lightweight Agg PNG path), so it is cheap to add. plotly is a genuinely
different renderer, but its static PNG export needs `kaleido`, which bundles a headless Chromium build - a heavy
install we do not want to force on everyone who installs `charr-datagen`.

The library a chart is drawn with is one attribute of a generated case, not a separate dataset to multiply by:
`--samples N` yields N images total, with the library chosen per case (the allocation mechanics are
[ADR-0014](0014-stratified-generation-model.md)). Dependencies must stay minimal, MIT-compatible, and GPL-free.

## Decision

We will render with **matplotlib, seaborn, and plotly**, treating the library as a per-case attribute, never a set
multiplier.

- **plotly is opt-in.** plotly + kaleido is an optional extra (`charr-datagen[plotly]`); the base install pulls only
  matplotlib and seaborn. The heavy Chromium cost is paid intentionally by installing the extra.
- **plotly degrades gracefully.** At runtime datagen probes whether plotly and kaleido import. If they do not, plotly
  drops out of the active library set for the run and that is logged loudly ("plotly disabled: kaleido not installed;
  rendering with matplotlib, seaborn"). A missing optional backend never crashes a run.
- **Determinism is per active library set.** A seed reproduces a dataset only for a fixed set of active libraries, so the
  active libraries and the seed are recorded in the run output, and `--libraries` lets a user pin the set explicitly for
  cross-machine reproducibility.
- **Licenses are all permissive:** matplotlib (BSD-style, PSF-compatible), seaborn (BSD-3), plotly (MIT), kaleido (MIT).
  None are GPL.

Alternatives considered:

- **matplotlib only:** rejected. Too little rendering variety; the checker must handle other libraries' defaults, and we
  cannot learn that from one backend.
- **All three as mandatory dependencies** (kaleido always installed): rejected. Forces a Chromium download on every
  install of what is a dev/manual package, against the minimal-dependency policy.
- **plotly static export via orca instead of kaleido:** rejected. orca is deprecated and heavier to operate (a separate
  server process); kaleido is the supported, MIT-licensed path.

## Consequences

- The base install stays light; plotly's variety is available to those who opt in and pay its cost knowingly.
- Runs succeed on machines without the extra, with a clear log, but a dataset is only bit-reproducible within the same
  active library set - recorded in the output so this is transparent rather than surprising.
- Library becomes a second within-cell random axis feeding the generation model in ADR-0014.
- This would be revisited if a fourth library became common enough to matter, or if a lighter static-export path for
  plotly removed the reason to keep it optional.
