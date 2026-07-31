# Delegation Fork Turns Implementation Plan

**Outcome:** Hermes `delegate_task` can start a child with no parent history, all effective parent history, or the last N semantic parent turns. Existing callers remain fresh by default. Named delegation routes can select a default fork mode, and the active default profile can use fresh scouts with forked workers and reviewers.

**Exact base:** `727a81e1d6c970fb196e9c1d76f1725b28a37e7c` on `main` (`main...origin/main [ahead 1]`), clean before this plan.

**Primary references:**
- Codex V2 schema and parser at OpenAI Codex revision `d97cb0dcad1df443462ade6c32b57e1c64a8a068`:
  - `codex-rs/core/src/tools/handlers/multi_agents_spec.rs`
  - `codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs`
- Codex fork construction, sanitization, cache-baseline handling, and lineage:
  - `codex-rs/core/src/agent/control/spawn.rs`
  - `codex-rs/core/src/thread_rollout_truncation.rs`
  - `codex-rs/core/src/session/turn.rs`
- Eric Provencher, “Practical multi-agent orchestration in Codex”:
  - https://x.com/pvncher/status/2080707291603407077

## Frozen public and configuration contract

### Public selector

`delegate_task` adds `fork_turns` at the call level and inside each batch task.

Accepted model-facing values are strings:
- `"none"`: inherit no parent history.
- `"all"`: inherit all eligible effective parent history.
- positive integer string such as `"3"`: inherit the most recent N eligible semantic turns.

Parsing trims whitespace and treats `none` and `all` case-insensitively. Invalid strings, zero, negative values, booleans, and non-string model-tool values fail with a clear error. An omitted or empty selector continues through the default-resolution chain instead of silently selecting `all`.

Precedence is:
1. Per-task `fork_turns`.
2. Call-level `fork_turns`.
3. Selected route `default_fork`.
4. Global compatibility default `"none"`.

A route can define `default_fork` with the same selector grammar. There is no new top-level `delegation.default_fork` setting in this scope. Routes without `default_fork` remain fresh.

The selected route still applies to the whole batch. Per-task fork overrides do not change route, model, provider, reasoning effort, role, tools, or credentials.

### Active default-profile route values

After the new runtime is loaded, `/Users/raynor-prs/.hermes/config.yaml` will use:

```yaml
delegation:
  routes:
    scout:
      default_fork: none
    worker:
      default_fork: all
    reviewer:
      default_fork: all
```

Existing model, provider, and reasoning values remain unchanged. Explicit `fork_turns` always overrides these route values.

### Fork snapshot and semantic turns

A fork is a dispatch-time copy. It never mutates the parent and never receives later parent or sibling messages.

The active parent turn is handled separately:
- The in-progress assistant `delegate_task` call and any incomplete tool chain are never inherited.
- The active visible user request is folded into the child’s final task message.
- The final task message contains the active request, delegated goal, and explicit context exactly once.

Eligible inherited history is sanitized:
- Keep completed visible user messages.
- Keep completed assistant final-answer text.
- Keep model-visible `api_content` for those retained messages when present so retained bytes remain stable.
- Keep visible multimodal user content through the established message-content representation.
- Drop system and developer messages; the child has its own stable system instructions.
- Drop hidden reasoning, assistant tool-call messages, tool results, approvals, delegation lifecycle records, display-hidden scaffolding, and internal-only metadata.
- A semantic turn starts with an eligible user or trigger-style synthesized user input and must have a completed assistant final answer after sanitization.
- N counts semantic turns, not raw messages.
- If sanitization would leave an incomplete or same-role boundary, drop the incomplete boundary rather than invoke role-sequence repair.

For behavior equivalence with Codex, the active request and delegated task appear together in the final user task message because Hermes has no distinct inter-agent communication role.

### Stable child packet

All modes use one child packet path:
- Stable child system instructions hold role, tool, lifecycle, ownership, and completion rules.
- Goal and context are not embedded in a unique ephemeral system suffix.
- One structured final user task message carries the active request, goal, and context.
- `"none"` uses the same packet with an empty inherited history.

This removes the current duplicated goal while preserving the documented goal/context/role/tool/result behavior.

### Compression and context limits

- `"all"` forks the parent’s current effective live context. If the parent already compressed, the child inherits the effective compressed replacement context. It does not expand archived pre-compression history.
- Numeric forks select only turns that remain provable in effective context. A compacted summary is an inherited baseline for `"all"`, not a synthetic counted turn for N. Numeric selection must not claim access to turns that compaction removed.
- The final task message is appended before size preflight.
- The child reuses Hermes’s existing preflight compression path. Compression changes only the child.
- The parent is never compressed as a side effect of delegation.
- No silent fallback from `"all"` to N or `"none"` is allowed.
- If compression is blocked, fails, or cannot fit the child request, the child returns a clear failure through the existing delegation result path.

### Cache contract

The guarantee is provider-neutral byte stability and cache eligibility, not a provider cache-hit guarantee:
- Retained historical model-visible bytes are copied without mutation.
- Fork selection and sanitization are deterministic.
- The child system prompt is stable for a given role/tool contract.
- The task-specific packet is the final user message.
- Route model/provider changes and removed tool traffic can reduce cache reuse.
- This scope does not add provider-specific reference-context IDs, cache baselines, or token accounting.

### Compatibility and invariants

- Omitted `fork_turns` with no route default remains current fresh-child behavior.
- Single, batch, synchronous nested, asynchronous top-level, cancellation, timeout, result ordering, live transcript, lineage, depth, and concurrency behavior remain unchanged.
- Leaf and depth enforcement remain code-enforced. Inherited orchestration prose cannot grant tools or delegation authority.
- Context inheritance does not grant new tools, credentials, approvals, roles, routes, filesystem access, or external-effect authority.
- Parent message dictionaries are never mutated.
- Prompt role alternation remains valid by construction. Do not rely on defensive repair.

## Explicit exclusions

- No global fork-on default.
- No raw transcript fork.
- No inherited hidden reasoning, tool calls/results, approvals, parent system prompt, or developer prompt.
- No sibling communication system or Codex-style inboxes.
- No provider-specific cache-reference implementation.
- No new compression algorithm, staging history, high-water mark, or silent context downgrade.
- No model/provider/reasoning/role changes in existing routes.
- No change to the CCM repository or trading systems.

## Dependencies and sequencing

1. Implement and prove the public fork and route-resolution behavior on the exact clean base.
2. Review the complete diff and run affected tests.
3. Restart the active Hermes gateway before adding `default_fork` to active routes. The old loaded validator rejects the new route field.
4. Update active route config and run live probes only after deployment approval.

The core feature and tests are one medium-to-large coherent slice because schema, normalization, history projection, child packet delivery, dispatch forwarding, and route defaults form one public contract. Documentation can be updated in the same slice. Do not split these into independently integrated partial APIs.

## Risks

- **Prompt-cache regression:** unique task content remains in the system prompt. → Move task data to the final user message and assert stable system text across goals.
- **Context leakage:** raw tool output, reasoning, approvals, or hidden scaffolding reaches a child. → Central sanitized projection plus behavior tests for every excluded class.
- **Role corruption:** active parent tool call or incomplete turn creates adjacent roles. → Cut before the active turn, fold active user content into the final task message, and test strict alternation.
- **Compaction expansion:** numeric forks imply access to archived turns. → Select only provable effective turns and test compacted-parent behavior.
- **Parent mutation:** projection or compression edits parent messages. → Deep-copy retained messages and compare the complete parent list before and after.
- **Route breakage:** live config gains `default_fork` before the process knows it. → Restart code first, then edit config.
- **Provider overflow:** near-full inherited history plus task exceeds the child model. → Exercise the existing child preflight path after task append and fail visibly if it cannot fit.

### Task 1: Add the fork selector, route default, and one child packet path

**Paths:**
- Modify `tools/delegate_tool.py`.
- Modify `run_agent.py`.
- Modify `tests/tools/test_delegate.py`.
- Modify `website/docs/user-guide/features/delegation.md`.
- Modify `website/docs/guides/delegation-patterns.md` only if its examples would otherwise contradict the new selector/default contract.

**Changes:**
- Add one parser/domain representation for `none`, `all`, and positive N.
- Extend route validation with `default_fork`.
- Resolve per-task, call, route, and compatibility defaults in one place.
- Add model schema fields at call and task levels.
- Build a copied, sanitized, completed-turn projection from the parent’s live effective messages.
- Build one stable child system instruction packet and one final task user message.
- Pass selected history through the existing `AIAgent.run_conversation(conversation_history=...)` seam.
- Forward `fork_turns` through canonical dispatch and registry fallback paths.
- Update model-facing descriptions so fresh and forked children are both described accurately.

**Behavior-first tests:**
1. RED → GREEN: public single call with explicit `"all"` inherits sanitized completed history, folds the active request into one final task message, preserves role order, and does not mutate the parent.
2. RED → GREEN: omitted selector with no route default remains fresh.
3. RED → GREEN: selector precedence works for per-task, call, route, and global fresh default, including mixed batch tasks.
4. RED → GREEN: `"none"`, `"all"`, and positive N parse as specified; invalid values identify the call or task that failed.
5. RED → GREEN: N counts completed semantic turns and excludes incomplete active/tool-only boundaries.
6. RED → GREEN: sanitization drops reasoning, tool calls/results, approvals, hidden display records, lifecycle messages, and internal metadata while retaining exact eligible model-visible text bytes.
7. RED → GREEN: stable system prompt is identical across different goals; task data appears once in the final user message.
8. RED → GREEN: canonical dispatcher and registry fallback forward the selector.
9. RED → GREEN: route validation accepts valid `default_fork`, rejects invalid values, and leaves old routes unchanged.
10. RED → GREEN: existing async/sync, batch order, depth, role, timeout, and live transcript tests remain green.

**Verification:**
```bash
scripts/run_tests.sh tests/tools/test_delegate.py -q
scripts/run_tests.sh tests/agent/ -q
scripts/run_tests.sh tests/tools/ -q
git diff --check
```
Run any narrower preflight-compression test file identified during implementation. Run the full Python suite if targeted evidence is green and runtime permits.

**Done when:** The public contract works through the real `delegate_task` seam, all affected tests pass without retries being dismissed as green, docs match behavior, and the complete diff has parent review evidence.

### Task 2: Independent review and bounded repairs

**Depends on:** Task 1 green on one exact head.

**Review:**
- Parent inspects the full diff and test output.
- A read-only reviewer checks behavior, cache/alternation invariants, simplification, and exclusions on the exact reviewed head.
- Repair in place if the foundation is sound. Discard and rebuild the slice only if the interpretation or architecture is wrong and replacement is lower risk.

**Done when:** All in-contract findings are fixed, affected checks are rerun, and the exact head is accepted.

### Task 3: Activate the current default-profile routes and live-probe

**Paths/effects:**
- Restart the active Hermes gateway so it loads the new code.
- Modify `/Users/raynor-prs/.hermes/config.yaml` only after restart.
- No credential, model, provider, reasoning, toolset, or profile changes.

**Approval gate:** AJ must explicitly approve the gateway restart and active-config change. This approval was requested but timed out while the plan was written.

**Live evidence:**
- Seed a unique parent-only fact in a controlled probe session.
- `scout` with omitted selector must not know the fact.
- `worker` with omitted selector must receive the fact.
- `reviewer` with omitted selector must receive the fact.
- Explicit `fork_turns: "none"` on `worker` must not receive the fact.
- Explicit `fork_turns: "all"` on `scout` must receive the fact.
- A near-threshold controlled child must use child-only preflight compression or return a clear blocked result; the parent transcript remains unchanged.
- Remove temporary probe files and verify cleanup.

**Done when:** Route defaults and overrides are proven in the loaded runtime, the parent remains unchanged, and probe cleanup is verified.

## Final verification and rollback

- `git status --short --branch`, exact HEAD, complete diff, and `git diff --check` are recorded.
- Targeted and affected Python suites pass through `scripts/run_tests.sh`.
- Documentation describes the compatibility default and route precedence.
- Active route config is read back after any approved change.
- Rollback is: remove route `default_fork` fields first, restart onto the prior code, then revert the code change. This order keeps the old validator from seeing unknown fields.
