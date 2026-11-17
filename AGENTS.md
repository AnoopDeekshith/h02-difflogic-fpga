# Project working instructions

Read `CLAUDE.md` and `docs/PROJECT_CONTEXT.md` for project background.
Use `docs/PROJECT_CHECKLIST.md` to identify the current numbered step.

- Explain concepts simply, one piece at a time, with concrete examples.
- Use the `engineering:debug` skill for test failures and other unexpected
  behavior: reproduce, isolate, diagnose the root cause, then fix and verify.
  Debugging summaries should record expected versus actual behavior, exact
  reproduction steps, root cause, fix, verification results and prevention.
  If the cause remains uncertain, say so. Keep the independent verifier required
  below; a debugging report does not replace that review.
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

## Model routing and credit use

- Anoop prefers Sol High for the main implementation work. Use `gpt-6-sol`
  with high reasoning when explicitly selecting a Sol sub-agent.
- Delegate substantial documentation drafting/formatting from verified artifacts
  to `gpt-6-luna` with medium reasoning. Technical conclusions and energy claims
  must come from reviewed evidence, not be invented by the documentation agent.
- Keep routine independent correctness reviews on Sol High. Use `gpt-6-astra`
  with high reasoning for critical measurement methodology, power/energy claims,
  novelty assessment, final paper review and difficult unresolved technical issues.
- Preserve the independent verifier requirement for every completed numbered step.
  Give delegated agents bounded tasks and concise file/evidence handoffs; avoid
  duplicating full-context work or rerunning completed experiments unnecessarily.
- These choices concern sub-agents. Changing the main conversation's model
  requires the app's model selector; do not claim to have changed it via tools.
