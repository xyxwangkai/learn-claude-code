import json
import os
from typing import Any, Dict, List

from anthropic import Anthropic
from openai import AzureOpenAI

MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "anthropic").strip().lower()
MODEL = os.environ["MODEL_ID"]


class BaseProviderAdapter:
    provider_name = "base"

    def __init__(self, client: Any):
        self.client = client

    def create_response(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], system: str):
        raise NotImplementedError

    def get_stop_reason(self, response: Any) -> str:
        raise NotImplementedError

    def get_text_blocks(self, response: Any) -> List[str]:
        raise NotImplementedError

    def get_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def append_assistant_message(self, messages: List[Dict[str, Any]], response: Any) -> None:
        raise NotImplementedError

    def append_tool_results(self, messages: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def make_tool_result(self, call_id: str, output: str) -> Dict[str, Any]:
        raise NotImplementedError

    def make_text_result(self, text: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_final_text_from_messages(self, messages: List[Dict[str, Any]]) -> str:
        raise NotImplementedError

    def compact_tool_results(self, messages: List[Dict[str, Any]], keep_recent: int,
                             preserve_tool_names: set) -> List[Dict[str, Any]]:
        return messages


class AnthropicAdapter(BaseProviderAdapter):
    provider_name = "anthropic"

    def create_response(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], system: str):
        return self.client.messages.create(
            model=MODEL,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=8000,
        )

    def get_stop_reason(self, response: Any) -> str:
        return response.stop_reason

    def get_text_blocks(self, response: Any) -> List[str]:
        return [block.text for block in response.content if hasattr(block, "text")]

    def get_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        calls = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        return calls

    def append_assistant_message(self, messages: List[Dict[str, Any]], response: Any) -> None:
        messages.append({"role": "assistant", "content": response.content})

    def append_tool_results(self, messages: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> None:
        messages.append({"role": "user", "content": results})

    def make_tool_result(self, call_id: str, output: str) -> Dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": output,
        }

    def make_text_result(self, text: str) -> Dict[str, Any]:
        return {"type": "text", "text": text}

    def get_final_text_from_messages(self, messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return ""
        content = messages[-1].get("content")
        if not isinstance(content, list):
            return ""
        blocks = [part.text for part in content if hasattr(part, "text")]
        return "\n".join(blocks).strip()

    def compact_tool_results(self, messages: List[Dict[str, Any]], keep_recent: int,
                             preserve_tool_names: set) -> List[Dict[str, Any]]:
        tool_results = []
        for msg in messages:
            if msg["role"] == "user" and isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        tool_results.append(part)
        if len(tool_results) <= keep_recent:
            return messages

        tool_name_map = {}
        for msg in messages:
            if msg["role"] != "assistant":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if getattr(block, "type", None) == "tool_use":
                    tool_name_map[block.id] = block.name

        for result in tool_results[:-keep_recent]:
            if not isinstance(result.get("content"), str) or len(result["content"]) <= 100:
                continue
            tool_name = tool_name_map.get(result.get("tool_use_id", ""), "unknown")
            if tool_name in preserve_tool_names:
                continue
            result["content"] = f"[Previous: used {tool_name}]"
        return messages


class OpenAIAzureAdapter(BaseProviderAdapter):
    provider_name = "openai_azure"

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted = []
        for tool in tools:
            converted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            })
        return converted

    def to_provider_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user" and isinstance(content, str):
                converted.append({"role": "user", "content": content})
                continue

            if role == "assistant" and isinstance(content, dict):
                converted.append({
                    "role": "assistant",
                    "content": content.get("text", ""),
                    "tool_calls": content.get("tool_calls") or [],
                })
                continue

            if role == "tool" and isinstance(content, str):
                converted.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": content,
                })
                continue

            converted.append(msg)
        return converted

    def create_response(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], system: str):
        return self.client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": system}] + self.to_provider_messages(messages),
            tools=self.format_tools(tools),
            tool_choice="auto",
            max_tokens=8000,
            stream=False,
        )

    def get_stop_reason(self, response: Any) -> str:
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "tool_calls":
            return "tool_use"
        return finish_reason or "stop"

    def get_text_blocks(self, response: Any) -> List[str]:
        text = response.choices[0].message.content or ""
        return [text] if text else []

    def get_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        calls = []
        for tool_call in response.choices[0].message.tool_calls or []:
            try:
                parsed_input = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                parsed_input = {}
            calls.append({
                "id": tool_call.id,
                "name": tool_call.function.name,
                "input": parsed_input,
            })
        return calls

    def append_assistant_message(self, messages: List[Dict[str, Any]], response: Any) -> None:
        message = response.choices[0].message
        tool_calls = []
        for tool_call in message.tool_calls or []:
            tool_calls.append({
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            })
        messages.append({
            "role": "assistant",
            "content": {
                "text": message.content or "",
                "tool_calls": tool_calls,
            },
        })

    def append_tool_results(self, messages: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> None:
        for result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "content": result["content"],
            })

    def make_tool_result(self, call_id: str, output: str) -> Dict[str, Any]:
        return {
            "tool_call_id": call_id,
            "content": output,
        }

    def make_text_result(self, text: str) -> Dict[str, Any]:
        return {
            "tool_call_id": "message",
            "content": text,
        }

    def get_final_text_from_messages(self, messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return ""
        content = messages[-1].get("content")
        if not isinstance(content, dict):
            return ""
        return str(content.get("text", "")).strip()

    def compact_tool_results(self, messages: List[Dict[str, Any]], keep_recent: int,
                             preserve_tool_names: set) -> List[Dict[str, Any]]:
        return messages


def build_client() -> Any:
    if MODEL_PROVIDER == "anthropic":
        if os.getenv("ANTHROPIC_BASE_URL"):
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        return Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))

    if MODEL_PROVIDER == "openai_azure":
        return AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            default_headers={
                "X-TT-LOGID": os.getenv("AZURE_OPENAI_LOGID", "local-debug")
            },
        )

    raise ValueError(
        f"Unsupported MODEL_PROVIDER '{MODEL_PROVIDER}'. "
        "Expected 'anthropic' or 'openai_azure'."
    )


def build_adapter(client: Any) -> BaseProviderAdapter:
    if MODEL_PROVIDER == "anthropic":
        return AnthropicAdapter(client)
    if MODEL_PROVIDER == "openai_azure":
        return OpenAIAzureAdapter(client)
    raise ValueError(
        f"Unsupported MODEL_PROVIDER '{MODEL_PROVIDER}'. "
        "Expected 'anthropic' or 'openai_azure'."
    )
