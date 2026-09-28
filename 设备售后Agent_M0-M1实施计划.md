# DeviceCare M0-M1 Implementation Plan

> **For agentic workers:** Execute task-by-task with review checkpoints. Use checkboxes for tracking. This is an implementation plan, not an assertion that any task is incomplete; audit each item before edits. If your environment provides `subagent-driven-development` or `executing-plans`, follow its instructions. Do not delegate merely because this sentence mentions those skills.

**Goal:** On existing device-agent code, deliver a reproducible local device-after-sales dialogue with four deterministic workflows, persistent interruption/resumption, and server-validated write authorization.

**Architecture:** Reuse Gateway `DialogueState`, `DialogueService`, existing YAML and business backend. A validated flow runner calls a typed tool registry; business backend is authoritative for ownership, confirmation and ticket creation. The RAG adapter is independent and fails explicitly. M2 LLM and M3 LangGraph/MCP are separate follow-on plans after this acceptance gate.

**Tech Stack:** Python 3.11-3.12, FastAPI, Pydantic 2, SQLAlchemy, MySQL, httpx, PyYAML, pytest, Vue/Vite; preserve pinned `uv.lock` unless changes require an update.

## Global Constraints

- Root: `F:\AAA求职相关\device_agent`; Gateway: `atgui_agent/agent_gateway`; backend: `device-service-backend/app`; flow: `atgui_agent/flow_config`; frontend: `atgui_agent/device-service-frontend`.
- Existing edits belong to user/another AI. Inspect before changing; if a task is already implemented, prove it with the stated tests, mark verified and skip changes. Root may not be a Git repository; commit only if a Git repository exists and the user/working agreement expects commits.
- Use synthetic fixtures only. Never print, copy or commit `.env` contents, keys or actual customer data. Do not clear Docker volumes, reset databases or overwrite files to force a clean state.
- No production/public exposure without trusted user identity and resource-level authorization. Client `sender_id`, `customer_id` and `confirmed=true` are not authority. Disable unsafe writes until the authorization gate is complete.
- M1 scope: four YAML workflows plus manual FAQ and safe diagnostic clarification. No LangGraph, Redis, custom MCP, autonomous firmware changes or invented PDF citations.
- Every implementation task is red/green/refactor: run a focused failing test first, then code, then focused + adjacent regressions. Report actual stdout/exit codes; do not mark environment-blocked checks as passing.
- If the current API/schema diverges, retain the existing public frontend contract and make the smallest compatible migration; record a contract decision in the audit log before changing it.

---

## File Ownership Map

| Unit | Responsibility | Existing/new candidate |
|---|---|---|
| HTTP boundary | Parse request, identity, response; no flow decisions | `atgui_agent/agent_gateway/api/{app,routers,schemas,dependencies}.py` |
| Dialogue application | Load/process/commit one turn | `atgui_agent/agent_gateway/service/dialogue_service.py` |
| Task state | Task/step/slots/pause stack/serialization | `atgui_agent/agent_gateway/domain/{state,contexts}.py` |
| Workflow definition | Parse and reject invalid YAML at startup | `atgui_agent/agent_gateway/engine/flow_loader.py` (new if absent) |
| Workflow runtime | Advance bounded steps, pause/confirm/resume | `atgui_agent/agent_gateway/engine/flow_executor.py` (new if absent) |
| Business actions | Typed, fixed-endpoint tool registry | `atgui_agent/agent_gateway/task/tools.py` (new if absent) |
| Persistence | Atomic state + messages and concurrency control | `atgui_agent/agent_gateway/repository/state_repository.py`, `infrastructure/database.py` |
| Business authority | Identity/ownership/confirmation/idempotency | `device-service-backend/app/{api,schemas,models,database,app}.py` and `mysql/initdb` or migrations |
| Adapter / UI | RAG evidence and confirmation display | `agent_gateway/infrastructure/http_client.py`, `agent_gateway/engine/stub_brain.py`, `device-service-frontend/src/App.vue` |

Do not create the candidate file when equivalent functionality already exists. Tests may live beside current `agent_gateway/test/` and backend's existing test layout; avoid importing production modules by changing `sys.path` in every test.

## Task 1: M0 evidence baseline and startup contract

**Files:** Read all paths in map; create `执行盘点与验收记录.md` only after announcing the edit. Modify root `启动说明.txt`, `atgui_agent/README.md`, Compose/Vite only for verified mismatches.

**Interfaces:** Produces a status row for each task (`verified|implemented_unverified|missing|blocked`), exact command/output, version/time, owning file and next action. No runtime API change.

- [ ] Read `.git` presence/status at root and nested folders, recent file modifications, existing tests, docs, route definitions, YAML and current service ports. Check only existence/ignored status of `.env`, not its values. Record whether another AI already implemented each item.
- [ ] Run from root: `uv run pytest -q`; `docker compose -f '.\atgui_agent\docker-compose.yml' config --quiet`. Run `npm run build` from `atgui_agent/device-service-frontend`. Record exit code, count and blocked prerequisites separately. Do not install/launch long-lived services solely to make M0 green without first checking port ownership.
- [ ] Add a contract smoke check in a test or executable diagnostic script against the existing FastAPI app/route table. The assertion must inspect `/health`, `/api/chat`, `/api/chat/history`; do not require a real MySQL connection for import-only checking.

```python
paths = {route.path for route in app.routes}
assert {"/health", "/api/chat", "/api/chat/history"} <= paths
```

- [ ] If a startup command fails due to incorrect path, first demonstrate failure; correct only that path and rerun. In the audit log distinguish “unit test passed” from “actual MySQL/RAG/restart behavior tested”. Root startup file stays authoritative.
- [ ] Gate: baseline status table is complete; no secret value appears in diagnostics; old README claims are relabeled as code-present vs runtime-verified. Stop before Task 2 only for missing authority or destructive operation, not ordinary missing optional RAG.

## Task 2: Validate YAML as data, not executable code

**Files:** `atgui_agent/flow_config/{user_flows,system_flows}.yml`; create/modify `agent_gateway/engine/flow_loader.py`; test `agent_gateway/test/test_flow_loader.py`.

**Interfaces:** `load_flows(path: Path) -> FlowCatalog`; `FlowCatalog.get(flow_id: str) -> FlowDefinition`; `FlowDefinition` exposes entry, slots and steps by ID. Validator rejects duplicate IDs, dangling next links, unknown slot/tool/type and a write tool without confirmation predecessor. Never evaluate a YAML string with Python `eval`.

- [ ] Write tests for current four flow IDs and malformed fixture: unknown `next`, duplicate step, arbitrary action, `${slots.unknown}`, and `write_confirm` without a `confirm` step. Check the *exact* error type/message category, not merely any exception.

```python
def test_rejects_dangling_next(tmp_path):
    path = tmp_path / "bad.yml"
    path.write_text("flows: {x: {entry: a, steps: [{id: a, type: reply, say: ok, next: missing}]}}", encoding="utf-8")
    with pytest.raises(FlowDefinitionError, match="missing"):
        load_flows(path)
```

- [ ] Run `uv run pytest -q atgui_agent/agent_gateway/test/test_flow_loader.py` and capture failing assertion. Implement immutable normalized definitions and validation using `yaml.safe_load`; restrict interpolation to explicit `slots` and `tool` keys, escaping rendered text in UI. Never execute expressions from YAML.
- [ ] Re-run focused tests, then existing chat suite. Confirm YAML tool field names against actual backend `app/schemas.py` (`warranty_deadline`, create ticket inputs); change mismatched YAML only with regression test. Record YAML version/hash and how an in-flight session survives a definition change (pin old version or reject safely and ask to restart).

## Task 3: Read-only workflows with stateful continuation

**Files:** `agent_gateway/engine/flow_executor.py`, `task/tools.py`, `service/dialogue_service.py`, `domain/contexts.py`, `test/test_read_flows.py`; adapt `engine/stub_brain.py` only as fallback.

**Interfaces:** `FlowExecutor.advance(state: DialogueState, user_text: str, tools: ToolRegistry) -> ProcessResult`; no arbitrary endpoint from model/YAML. `ToolRegistry.call(name, args, auth_context)` returns a typed result or a typed tool error. `DialogueService.chat` passes the **loaded state** to the runner and saves its modified state.

- [ ] Start with a failing multi-turn test: first `帮我查保修` asks for `device_id` with zero HTTP calls; second `DEV-2026-0001` calls `check_warranty` once and reports only fixture fields. Add a progress flow test: missing ticket ID asks; submitted ID calls progress once; ownership error shows no data.

```python
first = await service.chat("u1001", "帮我查保修")
assert "设备编号" in first["messages"][0]["text"]
assert fake_device.calls == []
second = await service.chat("u1001", "DEV-2026-0001")
assert fake_device.calls == ["/devices/DEV-2026-0001/warranty"]
```

- [ ] Run focused tests to observe failures. Implement bounded advancement (max 30 steps/turn), slot pattern validation, no duplicate read calls for one turn, explicit 404/403/timeout outcomes, and state-aware continuation. Keep `system_context` higher priority than the task, but detect explicit new intent and cancellation before consuming free text as a slot.
- [ ] Re-run read-flow, existing chat, history and serialization tests. Gate: missing ID never triggers tool; 403 never leaks resource; replaying a reply does not mutate unrelated task state.

## Task 4: Interrupt/resume and durable turn commit

**Files:** `domain/{state,contexts}.py`, `service/dialogue_service.py`, `repository/state_repository.py`, `infrastructure/database.py`; tests `test_task_resume.py`, `test_state_repository.py`.

**Interfaces:** Persist `flow_id`, `flow_version`, `step_id`, validated slots and pause stack. Repository exposes one `commit_turn(sender_id, expected_version, state_dict, messages) -> int` method using one transaction; version conflict is explicit. Existing `load_state/list_messages` remain compatible or are migrated with tests.

- [ ] Write failing test: start create-ticket, fill device number, ask warranty, complete warranty, then receive original next question with original slots intact. Cancellation of the active task leaves unrelated historical tickets untouched. A third nested interruption returns clarification (max stack 2).

```python
await service.chat("u1001", "我要报修")
await service.chat("u1001", "DEV-2026-0001")
await service.chat("u1001", "保修到什么时候")
reply = await service.chat("u1001", "DEV-2026-0001")
assert "故障" in reply["messages"][0]["text"]
```

- [ ] Write repository test injecting failure while inserting one bot message; assert transaction rollback leaves both state version and message count unchanged. Write a conflict test with two loaded versions and assert the second commit fails without appending duplicates.
- [ ] Run tests red. Implement single-transaction state/messages commit and optimistic version or row lock. Preserve legacy JSON in `from_dict`; implement explicit session expiry and old Flow version behavior. **Do not store a second full copy of history in both state JSON and messages table indefinitely**: choose canonical history and migration based on existing data, with compatibility test.
- [ ] Re-run focused and full pytest. If MySQL available, verify reload in a new process plus simultaneous same-session requests; mock-only tests do not satisfy restart durability gate.

## Task 5: Read-only manual knowledge and diagnostic boundary

**Files:** `engine/flow_executor.py` or focused `task/manual.py`, `infrastructure/http_client.py`, `test/test_manual_adapter.py`; backend `/manual/search` adapter only if Gateway uses it by contract.

**Interfaces:** `ManualResult(answer, citations, source_status)` with `source_status` one of `grounded|no_hit|unavailable|synthetic`. Only source-backed citations render as actual manual references.

- [ ] Write tests for real-shaped `shopkeeper_brain` response, empty hits, 5xx, malformed citation and risky steps. Real response must preserve document identifier/title/page or chunk ID; failures show `unavailable`, zero citations. A synthetic fallback never says “手册第 N 页”.

```python
result = await manual_search("型号X", "如何配置 VLAN", fake_rag)
assert result.source_status == "grounded"
assert result.citations[0].chunk_id == "fixture-chunk-1"
```

- [ ] Run tests red; verify actual local RAG API schema read-only before adapting response. Implement model/version disambiguation and bounded timeout. High-risk power/disassembly/data-loss advice goes to human with no autonomous operation. Re-run focused tests and read-only business tests.

## Task 6: Identity, ownership and safe-write gate

**Files:** backend `app/{api,schemas,models,app}.py`, `mysql/initdb` or a migration, Gateway `api/{schemas,dependencies,routers}.py`, `task/tools.py`, frontend `src/App.vue`; tests `test_authorization.py`, `test_confirm_write.py` in corresponding existing test locations.

**Interfaces:** An `AuthContext(principal_id, roles)` is derived server-side, never trusted from `sender_id`. Write intent first creates `confirmation_id` scoped to principal/session/action/resource/normalized payload hash with short expiry. Consuming the confirmation calls a backend write exactly once under a required `idempotency_key`; the backend checks resource ownership. Preserve current API contract for local demo only behind explicit development-only mode.

- [ ] Start with failing tests for unauthenticated read/write, cross-user device/ticket/history read, `confirmed=true` without server token, expired/wrong-payload token, cancel, replay, two concurrent requests with one key, and write timeout followed by result lookup. Confirm existing `AGENT_API_KEY` authenticates the Gateway service only.

```python
response = client.post("/api/chat", json={"sender_id": "u1002", "text": "确认"})
assert response.status_code in (200, 401, 403, 409)
if response.status_code == 200:
    assert "已创建" not in str(response.json())
assert ticket_count() == 0
```

- [ ] Run focused tests red. Decide and record the identity source: if no trusted login exists, restrict **all write endpoints** to explicit loopback synthetic-data demo mode and label this non-production. For a deployable mode, implement actual session/bearer identity, ownership relation and forbidden-by-default behavior; never accept caller-supplied `customer_id` as proof.
- [ ] Implement confirmation issuance/consumption and payload digest server-side, with audit event and TTL. Replace `max+1` with DB-generated unique primary key or UUID/unique constraint; idempotency record and ticket creation commit together. Remove direct `confirmed: true` from YAML as proof of consent; treat it solely as an internal transition hint if backward compatibility requires it.
- [ ] Re-run all security tests and concurrency test with the actual DB engine, not only mocks. Update CORS and frontend confirmation interaction to show exact write summary. Gate: unsafe modes reject writes; no duplicate ticket on double click; no cross-user read through direct `/device/*` proxy.

## Task 7: End-to-end handoff and evidence

**Files:** `启动说明.txt`, `atgui_agent/{README.md,API.md,VIBE_CODING_GUIDE.md}`, `执行盘点与验收记录.md`, tests and fixtures introduced above.

**Interfaces:** No new API; produces reproducible commands, exact environment prerequisites, test counts and feature matrix (`verified|code only|planned|blocked`).

- [ ] Run the full pytest, Compose config, frontend build and both service health checks shown in the approved total design. Check source for hard-coded LAN IP, fake citation, broad CORS and accidental key printing. Do not paste actual `.env` values into evidence.
- [ ] Execute the 10 scenarios in the total design with synthetic accounts. Save expected versus actual tool sequence, HTTP status, returned message and persisted business outcome. For failures, record a precise reproduction and open issue; no “mostly passed” sign-off.
- [ ] Update docs to separate M1 completed from M2/M3 planned; explain standalone RAG unavailable mode and local demo identity limitation. Run the same verification commands once more after doc/config changes.
- [ ] Gate: user can follow the root startup instructions on a local machine, see all 10 scenarios and inspect actual results. If a required component is unavailable, label the scenario `blocked` and do not assert M1 acceptance.

## Review Checkpoint

After each task, provide a short report: existing-work audit, files changed, focused red/green evidence, broader regression evidence, unverified integration assumptions, and next task. Review high-risk Task 4 persistence and Task 6 writes independently before continuing. If Git is available and in-scope, commit only the tested task's files with an explicit message; if not, retain a file-level change ledger without initializing Git.

At M1 acceptance, stop and request a fresh M2 plan based on the actual final interfaces. The approved decision remains: reliable single-orchestrator workflow first; LangGraph/MCP only as evidence-backed optional M3.
