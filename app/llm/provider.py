from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import get_settings


class ProviderError(RuntimeError):
    pass


class ProviderTimeout(ProviderError):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: str = "end_turn"
    raw: Any = field(default=None, repr=False)


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
    ) -> LLMResponse: ...


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "anthropic package is not installed, run pip install -r requirements.txt"
            ) from exc

        if not api_key or api_key == "sk-ant-replace-me":
            raise ProviderError("ANTHROPIC_API_KEY is not configured")

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._model = model

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        import anthropic

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 1500,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeout(str(exc)) from exc
        except anthropic.APIError as exc:
            raise ProviderError(str(exc)) from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        calls = tuple(
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            for block in response.content
            if getattr(block, "type", "") == "tool_use"
        )

        return LLMResponse(
            text=text,
            tool_calls=calls,
            stop_reason=response.stop_reason or "end_turn",
            raw=response,
        )


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "openai package is not installed, run pip install -r requirements.txt"
            ) from exc

        if not api_key or api_key == "sk-proj-replace-me":
            raise ProviderError("OPENAI_API_KEY is not configured")

        self._client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    @staticmethod
    def _to_openai_messages(messages: list[dict], system: str | None) -> list[dict]:
        converted: list[dict] = []
        if system:
            converted.append({"role": "system", "content": system})

        for message in messages:
            content = message["content"]
            if isinstance(content, str):
                converted.append({"role": message["role"], "content": content})
                continue

            tool_calls = []
            text_parts = []
            for block in content:
                if block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"]),
                            },
                        }
                    )
                elif block.get("type") == "tool_result":
                    converted.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block["content"],
                        }
                    )
                elif block.get("type") == "text":
                    text_parts.append(block["text"])

            if tool_calls or text_parts:
                entry: dict[str, Any] = {"role": message["role"]}
                entry["content"] = "\n".join(text_parts) or None
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                converted.append(entry)

        return converted

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        import openai

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._to_openai_messages(messages, system),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
                for tool in tools
            ]

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.APITimeoutError as exc:
            raise ProviderTimeout(str(exc)) from exc
        except openai.APIError as exc:
            raise ProviderError(str(exc)) from exc

        choice = response.choices[0]
        calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in (choice.message.tool_calls or [])
        )

        return LLMResponse(
            text=choice.message.content or "",
            tool_calls=calls,
            stop_reason=choice.finish_reason or "stop",
            raw=response,
        )


def get_provider() -> LLMProvider:
    settings = get_settings()

    try:
        if settings.llm_provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ProviderError("ANTHROPIC_API_KEY is not set")
            return AnthropicProvider(
                settings.anthropic_api_key,
                settings.llm_model,
                settings.llm_timeout_seconds,
            )

        if settings.llm_provider == "openai":
            if not settings.openai_api_key:
                raise ProviderError("OPENAI_API_KEY is not set")
            return OpenAIProvider(
                settings.openai_api_key, settings.llm_model, settings.llm_timeout_seconds
            )
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(
            f"{settings.llm_provider} provider could not be initialised: {exc}"
        ) from exc

    raise ProviderError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
