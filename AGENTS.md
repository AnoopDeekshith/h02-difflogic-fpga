# Project working instructions

Read `CLAUDE.md` and `docs/PROJECT_CONTEXT.md` for project background.
Use `docs/PROJECT_CHECKLIST.md` to identify the current numbered step.

- Explain concepts simply, one piece at a time, with concrete examples.
- For every completed numbered step, use an independent verification sub-agent
  to review the code, methodology and results. Fix blocking findings and have
  the verifier check the corrections before calling the work verified.
- Include a bounded research-direction assessment: distinguish tested correctness,
  measurement proxies, actual power/energy evidence and unverified novelty.
- Create or update a numbered Markdown walkthrough in `docs/steps/`, explaining
  why, what, how, examples, reproduction commands, evidence and limitations.
  Link older documents and keep the learning index/checklist/context current.
- Preserve failed experiments and provenance. Never report stale output as a
  successful new run or hide a timing/resource failure by weakening constraints.
- Use matched data splits, target, architecture, clock and input sequence in
  research comparisons. Select settings on validation data. Do not equate
  fewer logical transitions with demonstrated lower energy.
- The NumPy model is the reference; scores and predicted class must match RTL,
  including lowest-index tie breaking. Keep historical baseline results distinct
  from experiments using changed training or hardware protocols.
