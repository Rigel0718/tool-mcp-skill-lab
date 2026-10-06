# Security Review

Perform a security-focused review in addition to the general review criteria.

## Review Areas

### Authorization Boundaries

Check whether privileged operations can bypass permission or approval checks.

### Input and Command Execution

Check whether untrusted input can reach shell commands, file operations,
queries, or other sensitive execution paths without sufficient validation.

### Data Exposure

Check whether logs, errors, tool results, or external responses can expose
sensitive information unexpectedly.

### Trust Boundaries

Check whether data from users, models, MCP servers, tools, or external
systems is trusted without appropriate validation.

### Failure and State Transitions

Check whether failures, retries, approval transitions, or partial execution
can bypass security invariants.