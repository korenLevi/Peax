"""Claude tool-use loop. The model picks tools; Python computes; the model narrates."""
from __future__ import annotations

from dataclasses import dataclass, field

import anthropic

from agent import config as C
from agent import tools
from agent.prompts import SYSTEM_PROMPT


@dataclass
class ToolCall:
    name: str
    input: dict
    result: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)


class AirportAgent:
    def __init__(self, model: str | None = None, params: tools.ScoringParams | None = None,
                 client: anthropic.Anthropic | None = None):
        self.model = model or C.MODEL
        self.params = params or tools.ScoringParams()
        self.client = client or anthropic.Anthropic()
        self.messages: list[dict] = []

    def ask(self, user_text: str) -> Turn:
        self.messages.append({"role": "user", "content": user_text})
        calls: list[ToolCall] = []
        usage = {"input_tokens": 0, "output_tokens": 0}

        for _ in range(C.MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=tools.TOOL_SCHEMAS,
                messages=self.messages,
            )
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
            # Keep thinking/tool_use blocks intact when replaying history.
            self.messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in response.content]})

            if response.stop_reason != "tool_use":
                text = "".join(b.text for b in response.content if b.type == "text")
                if response.stop_reason == "refusal":
                    text = text or "The model declined to answer this request."
                return Turn(text=text, tool_calls=calls, stop_reason=response.stop_reason, usage=usage)

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = tools.run_tool(block.name, dict(block.input), self.params)
                calls.append(ToolCall(block.name, dict(block.input), result))
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": tools.to_json(result), "is_error": "error" in result})
            self.messages.append({"role": "user", "content": results})

        return Turn(text="Stopped after too many tool rounds without a final answer.", tool_calls=calls,
                    stop_reason="max_rounds", usage=usage)

    def reset(self):
        self.messages = []
