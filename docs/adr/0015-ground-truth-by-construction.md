# 0015. Synthetic ground truth is established by construction and trusted

- Status: Accepted
- Date: 2026-06-28

## Context

`charr-datagen` needs a per-rule verdict for every chart it emits. There are three ways to get one: **by construction**
(the generator builds a chart to satisfy or violate a rule and records the verdict it built in), **hand-labeling**
(humans label rendered charts), and **model-assisted** (an LLM or the checker labels them). The premise of the whole
package is that we can know labels for free because we control how each chart is made.

The risk that premise carries: a generator bug could mislabel cases and silently corrupt every downstream metric, since
nothing would contradict a wrong label.

## Decision

We will establish synthetic ground truth **by construction** and record the verdict the generator built in. We will
**not** hand-label or model-label synthetic charts.

We will **trust the construction and not add a separate programmatic self-check.** A parallel labeler or self-check is
itself code that can be wrong; the integrity check we rely on instead is **emergent from `charr-eval`**: a systematic
generator mislabel shows up as a whole class the checker appears to "get wrong" the same way, and the remedy is to fix
the generator, not to maintain a second labeler. Eval usage over time tells us whether the generator is reliable.

Human spot-checking is the safety net, made ergonomic by a future review/correction GUI ([issue #4](https://github.com/mvherweg/charr/issues/4)),
which doubles as the labeler for real private datasets (ADR-0010). Borderline and adversarial cases are out of MVP scope;
margins stay clear so a `fail` is unambiguously a fail.

Alternatives considered:

- **Model-assisted labeling** (an LLM or the checker labels): rejected as circular. Grading the checker against labels
  produced by the checker or a peer model measures agreement, not correctness.
- **Hand-labeling synthetic charts:** rejected as unnecessary and costly when construction already knows the answer.
  Hand-labeling is, however, exactly the model for *real* private datasets (ADR-0010): synthetic ground truth is built,
  real ground truth is human-labeled.
- **A programmatic self-check** (assert against the plotting library's figure model before export): rejected for the
  MVP. It is more code that can be wrong, and eval plus occasional human review already covers the failure mode; we
  revisit if the generator proves unreliable in practice.

## Consequences

- Labels are free and exact for synthetic data; there is no labeling pipeline to run.
- The trust is load-bearing: a generator bug mislabels silently until eval or a human notices. We accept this, with
  eval-as-check and the GUI (issue #4) as mitigations and "fix the generator" as the remedy.
- Clean split of responsibility: synthetic ground truth by construction here, real charts human-labeled per ADR-0010.
- This would be revisited - most likely by adding the figure-model self-check - if eval ever shows the generator is
  unreliable.
