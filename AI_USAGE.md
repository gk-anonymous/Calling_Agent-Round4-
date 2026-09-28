# AI Usage Log

## Assignment 1 - Collections Ledger

- Tool: GitHub Copilot in VS Code.
- Prompt summary: requested Part B solutions, then asked to verify the package.
- Accepted: SQLite ledger implementation, integer-paise money, idempotent transaction handling, CSV row rejection reporting, and concurrent-payment tests.
- Corrected or qualified: DPD bucket labels overlap at day 90, so the SQL draft uses 91+; collection efficiency returns 0.0 when no EMI is due.


## Assignment 2 - Dialer Campaign Analytics

- Tool: GitHub Copilot in VS Code.
- Prompt summary: requested Assignment 2 Part B implementation and an end-to-end check of its notebook, chart, analysis, and memo.
- Accepted: reuse of the fixed-seed data generator, analysis functions, reproducible notebook, chart output, and quantified synthetic-data memo.
- Corrected or qualified: wrong-number calls count as connected calls but not RPC; results are estimates from seeded synthetic data. Part A was left for independent completion under the no-AI rule.

## Assignment 3 - Fix and Ship

- Tool: GitHub Copilot in VS Code.
- Prompt summary: requested Assignment 3  Part B deployable implementation.
- Accepted: Part B FastAPI app, IST retry scheduler, conditional DynamoDB event storage, SQS FIFO retry queue and worker, tests, container definition, Terraform, and GitHub Actions OIDC workflow.
- Corrected or qualified: moved the workflow to the repository-root `.github/workflows` directory so GitHub can discover it; enabled INFO-level structured logs. For an explicitly authorized interview demo, added a temporary HTTP-only public-subnet mode that disables TLS, the CRM worker, and GitHub OIDC. Terraform formatting/validation, local Docker health, and deployed ALB health passed. The public demo must be destroyed after use.


## Assignment 4 - Collections Assistant Agent

- Tool: GitHub Copilot in VS Code.
- Prompt summary: requested Assignment 4  Part B implementation; focused implementation on the AI-allowed Part B after reviewing the brief's no-AI restriction.
- Accepted: LangChain v1 agent with in-memory mock accounts, an in-memory checkpointer, tool-level identity/payment/callback guards, application-level sensitive-intent escalation, session-scoped identity verification, a deterministic tool/state evaluation, a guided no-key terminal demo, and Gemini live-provider configuration with OpenAI as an option.
- Corrected: the initial LangGraph pin conflicted with the resolved LangChain Core version; compatible LangChain, LangGraph, and provider pins were selected. The scripted fake chat model was updated to accept tool bindings. Added validation against non-finite and sub-paisa promise amounts, prompt-override rejection before the model call, single-thread assistant binding, and fail-closed provider error handling.
- Production caveat: adding a provider key enables live inference but does not remove the mock database, in-memory state, limited phrase detection, or need for consent, monitoring, security, and human escalation controls. A Gemini adapter initialization check used only a dummy test string and made no API request; the exposed key was not copied into files or used.

