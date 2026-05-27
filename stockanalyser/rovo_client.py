"""HTTP+SSE client for the local Rovo Dev CLI (`acli rovodev serve`).

Mirrors the pattern from `atlassian/disturbed-partner` (rovo-dev-only-baseline).
This is the ONE place that knows how to talk to the Rovo server. Skills are
identified by `SkillKey`; the actual prompts live in `.rovodev/subagents/<key>/SKILL.md`.

Phase 1 = simple request/response: we accumulate the SSE stream and return the
final JSON block from the assistant's message. No live streaming exposed to
API clients yet.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from stockanalyser.agents import AgentOutput, SkillKey
from stockanalyser.config import get_settings
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class RovoCLIError(RuntimeError):
    """Raised when the Rovo CLI is unreachable or returns a malformed response."""


class RovoClient:
    """Thin async client around POST /v2/chat (SSE)."""

    def __init__(self, base_url: str | None = None, timeout_sec: int | None = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.rovodev_base_url).rstrip("/")
        self.timeout_sec = timeout_sec or s.per_agent_timeout_sec

    # ─── Health ───────────────────────────────────────────────────────────
    async def health(self) -> bool:
        """Ping `acli rovodev serve`. Endpoint is `/healthcheck` (CLI's spelling)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.base_url}/healthcheck")
                return r.status_code == 200
        except Exception as e:  # noqa: BLE001
            log.warning("rovo_health_check_failed", error=str(e))
            return False

    # ─── Run a skill ──────────────────────────────────────────────────────
    async def run_skill(
        self,
        skill: SkillKey,
        inputs: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> AgentOutput:
        """POST a skill invocation and parse the final JSON response.

        Args:
            skill: Which markdown skill to execute.
            inputs: Self-contained payload (push pattern — skill should NOT
                need to read any file system or DB).
            run_id: Optional correlation id (logged + sent for traceability).

        Returns:
            AgentOutput parsed from the final fenced JSON block in the message.
        """
        prompt = self._build_prompt(skill, inputs, run_id=run_id)

        # `acli rovodev serve` /v2/chat expects:
        #   { "message": "<str>", "output_schema": {...optional JSON schema...} }
        # Passing the AgentOutput schema as `output_schema` nudges the model to
        # return JSON conforming to it (we still parse defensively below).
        payload: dict[str, Any] = {
            "message": prompt,
            "output_schema": AgentOutput.model_json_schema(),
        }
        raw_text = await self._post_chat_and_collect(payload)
        return self._parse_final_json(raw_text)

    @staticmethod
    def _build_prompt(skill: SkillKey, inputs: dict[str, Any], *, run_id: str | None) -> str:
        """Render the skill invocation as a single chat message.

        The skill markdown lives in `.rovodev/subagents/<key>/SKILL.md` and is
        auto-loaded by `acli rovodev serve`. We just need to name it + provide
        the inputs payload.
        """
        inputs_json = json.dumps(inputs, indent=2, default=str)
        run_id_line = f"\nrun_id: `{run_id}`" if run_id else ""
        return (
            f"Use the `{skill.value}` skill to analyse the following inputs.{run_id_line}\n\n"
            f"Inputs:\n```json\n{inputs_json}\n```\n\n"
            "Reply per the skill's output contract — end your message with one "
            "fenced ```json``` block containing the structured result."
        )

    # ─── Internals ────────────────────────────────────────────────────────
    async def _post_chat_and_collect(self, payload: dict[str, Any]) -> str:
        """POST to /v2/chat and accumulate the SSE stream into the assistant text.

        Rovo Dev SSE format (from /openapi.json):
            event: user-prompt
            data: {"content":"...","part_kind":"user-prompt"}

            event: text
            data: {"content":"I'll analyse..."}

            event: tool-call
            data: {"tool_name":"...", ...}

            event: end / stream-end
            data: {...}

        We accumulate `event: text` data.content into the response string. All
        other events are ignored (tool calls, thinking, etc).
        """
        url = f"{self.base_url}/v2/chat"
        chunks: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as c:
                async with c.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"Accept": "text/event-stream"},
                ) as resp:
                    resp.raise_for_status()
                    current_event: str | None = None
                    async for raw in resp.aiter_lines():
                        line = raw.rstrip("\r")
                        if not line:
                            current_event = None  # end of one SSE record
                            continue
                        if line.startswith("event:"):
                            current_event = line.removeprefix("event:").strip()
                            continue
                        if line.startswith("data:"):
                            body = line.removeprefix("data:").strip()
                            try:
                                event_data = json.loads(body)
                            except json.JSONDecodeError:
                                continue
                            if current_event == "text":
                                chunks.append(str(event_data.get("content", "")))
                            elif current_event in {"error", "stream-error"}:
                                raise RovoCLIError(
                                    f"Rovo error event: {event_data.get('content') or event_data}"
                                )
                            # ignore: user-prompt, tool-call, tool-return, thinking, end, stream-end
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text
            except Exception:  # noqa: BLE001
                pass
            raise RovoCLIError(f"Rovo CLI HTTP {e.response.status_code}: {body or e}") from e
        except httpx.HTTPError as e:
            raise RovoCLIError(f"Rovo CLI unreachable: {e}") from e

        return "".join(chunks)

    @staticmethod
    def _parse_final_json(text: str) -> AgentOutput:
        """Extract structured JSON from the assistant text.

        Tries in order:
          1. The whole text as JSON (when `output_schema` forces structured output).
          2. The LAST fenced ```json``` block.
          3. The LAST fenced ``` block (untyped).
        """
        candidates: list[str] = []

        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(stripped)

        candidates.extend(_FENCED_JSON_RE.findall(text))

        if not candidates:
            raise RovoCLIError(
                "No JSON found in agent response. "
                "Skill must return JSON (set `output_schema` or wrap in ```json``` fence)."
            )

        last_err: Exception | None = None
        for c in reversed(candidates):
            try:
                return AgentOutput.model_validate_json(c)
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise RovoCLIError(f"Agent JSON failed schema validation: {last_err}")
