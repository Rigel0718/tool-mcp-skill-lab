---
name: code-review
description: >
  Review existing code and code changes for correctness, reliability, and
  test coverage, and report verified findings by severity. Use when the user
  asks to review, inspect, or assess existing code, a diff, pull request,
  commit, or current code changes without modifying the code.
---
# Code Review

Review existing code or code changes and report verified issues without
modifying the code.

## Review Goals

Determine whether the reviewed code:

- behaves correctly,
- remains reliable when failures or unexpected conditions occur,
- and is adequately verified by tests.

The general review intentionally focuses on correctness, reliability, and
tests.

Do not ignore significant issues from other areas when they are discovered
during the review. However, do not perform specialized security, performance,
or architecture analysis unless the user requests it or the review context
requires it.

## Supporting References

When the user explicitly requests a security-focused review, read
`references/security-review.md` and apply its security review criteria
in addition to the general review workflow.

## Workflow

### 1. Understand the review scope

Identify exactly what the user asked to review, such as:

- specific code or files,
- current code changes,
- a diff,
- a commit,
- or a pull request.

Do not unnecessarily expand the review scope.

### 2. Gather relevant context

Inspect enough surrounding code to understand and verify the reviewed
behavior.

When necessary, inspect related callers, callees, tests, configuration,
contracts, or dependencies.

Keep the requested review scope unchanged while gathering additional context
needed to validate potential issues.

### 3. Review the code

Review the scoped code using the following primary criteria.

#### Correctness

Determine whether the code performs its intended behavior correctly.

Look for issues such as:

- incorrect conditions or control flow,
- incorrect calculations or return values,
- missing state handling,
- incorrect behavior in relevant edge cases,
- violated function or API contracts,
- and regressions introduced by the change.

#### Reliability

Determine whether the code remains safe and consistent when failures or
unexpected conditions occur.

Look for issues such as:

- incorrect or missing error handling,
- external operation failures,
- partial failures,
- resource cleanup problems,
- invalid or missing state,
- and inconsistent state after failure.

#### Tests

Determine whether important behavior is meaningfully verified.

Check whether tests:

- verify the intended behavior,
- cover important edge cases,
- cover important failure paths,
- assert the actual required behavior,
- and provide meaningful regression protection.

The presence of tests alone is not sufficient.

### 4. Validate potential findings

Do not report every suspected issue.

A potential issue becomes a finding only when all of the following are true:

**Evidence**

The code and available context provide sufficient evidence that the issue
actually exists.

Inspect additional context when the issue can reasonably be verified before
reporting it.

**Impact**

The issue has a meaningful effect on behavior, reliability, or verification.

Style preferences, cosmetic improvements, and subjective refactoring
suggestions are not findings.

**Actionable**

The location, triggering condition, and impact of the issue can be explained
concretely enough for the user to understand what is wrong.

Do not turn unverified assumptions into findings.

If an issue cannot be verified with the available context, do not report it
as a finding.

### 5. Classify severity

Classify each verified finding according to its impact on merge or release
decisions.

**Blocker**

The code should not be merged in its current state.

Use for issues that cause severe failures such as broken critical behavior,
serious data corruption, or similarly unacceptable consequences.

**Major**

A significant verified issue that should normally be fixed before merge.

Use for meaningful incorrect behavior, important failure-handling problems,
or significant regression risks.

**Minor**

A verified issue with limited impact that does not normally justify blocking
the merge.

Do not use Minor for style preferences, nitpicks, or optional improvements.
Those are not findings.

Severity describes the importance of the finding, not its review category.

### 6. Produce the review

Report verified findings first, ordered by severity.

Use the following format for each finding:

### [Severity] Short finding title

**Location:** `path/to/file.py:line`

Explain the problem, the conditions under which it occurs, the evidence that
supports the finding, and its practical impact.

A brief correction direction may be included when it helps explain the
problem, but do not modify the code unless the user explicitly requests a
separate implementation task.

After the findings, provide a short summary with the number of Blocker,
Major, and Minor findings.

If no verified issues are found, explicitly state:

> No significant findings.

Briefly summarize the reviewed scope instead of inventing findings to fill
the report.