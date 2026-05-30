"""
LLM provider abstraction — supports Ollama (local/free), Google Gemini, Anthropic.
Priority: Ollama > Google > Anthropic.

Set in .env:
  OLLAMA_MODEL=llama3.1        # local, free, no key needed
  GOOGLE_API_KEY=...           # Gemini
  ANTHROPIC_API_KEY=...        # Claude

Public API:
    run_agent_loop(agent_name, system_prompt, user_message, tools, tool_handlers)
        -> (final_text: str, trace: list[dict])

    simple_call(system_prompt, user_message)
        -> final_text: str
"""

import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
load_dotenv()


# ─────────────────────────────────────────────
# Provider detection
# ─────────────────────────────────────────────

def _provider() -> str:
    if os.getenv("OLLAMA_MODEL"):
        return "ollama"
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "google"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise EnvironmentError(
        "No LLM configured.\n"
        "  Free/local : set OLLAMA_MODEL=llama3.1 in .env  (needs Ollama installed)\n"
        "  Google     : set GOOGLE_API_KEY in .env\n"
        "  Anthropic  : set ANTHROPIC_API_KEY in .env"
    )


# ─────────────────────────────────────────────
# Ollama  (local, free, no key)
# ─────────────────────────────────────────────

def _to_ollama_tools(tools: list[dict]) -> list[dict]:
    """Convert our tool format to Ollama/OpenAI function-calling format."""
    result = []
    for t in tools:
        schema = t.get("input_schema", {})
        # Clean properties — keep only keys Ollama understands
        props = {}
        for k, v in schema.get("properties", {}).items():
            props[k] = {kk: vv for kk, vv in v.items()
                        if kk in ("type", "description", "enum")}
        result.append({
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters": {
                    "type":       "object",
                    "properties": props,
                    "required":   schema.get("required", []),
                },
            },
        })
    return result


def _coerce_args(kwargs: dict, tool_name: str, tools: list[dict]) -> dict:
    """Coerce argument types based on the tool schema — Ollama often returns ints as strings."""
    schema = next((t["input_schema"] for t in tools if t["name"] == tool_name), {})
    props  = schema.get("properties", {})
    result = {}
    for k, v in kwargs.items():
        expected = props.get(k, {}).get("type", "string")
        try:
            if expected == "integer" and not isinstance(v, int):
                result[k] = int(v)
            elif expected == "number" and not isinstance(v, float):
                result[k] = float(v)
            elif expected == "boolean" and not isinstance(v, bool):
                result[k] = str(v).lower() in ("true", "1", "yes")
            else:
                result[k] = v
        except (ValueError, TypeError):
            result[k] = v
    return result


def _ollama_loop(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    tool_handlers: dict,
) -> tuple[str, list[dict]]:
    import ollama

    model   = os.getenv("OLLAMA_MODEL", "llama3.1")
    o_tools = _to_ollama_tools(tools)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]
    trace: list[dict] = []

    for _ in range(10):
        resp = ollama.chat(model=model, messages=messages, tools=o_tools)
        msg  = resp.message

        if not msg.tool_calls:
            return (msg.content or "").strip(), trace

        # Serialize the assistant turn properly
        messages.append({
            "role":       "assistant",
            "content":    msg.content or "",
            "tool_calls": [
                {"function": {"name": tc.function.name,
                              "arguments": dict(tc.function.arguments or {})}}
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool call
        for tc in msg.tool_calls:
            fn     = tc.function
            t0     = time.time()
            kwargs = _coerce_args(dict(fn.arguments or {}), fn.name, tools)
            try:
                result = tool_handlers[fn.name](**kwargs)
            except Exception as e:
                result = {"error": str(e)}

            trace.append(_entry(agent_name, fn.name, kwargs, result, t0))
            messages.append({
                "role":    "tool",
                "content": json.dumps(result, default=str),
            })

    return "Max iterations reached.", trace


def _ollama_simple(system_prompt: str, user_message: str) -> str:
    import ollama
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    resp  = ollama.chat(model=model, messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ])
    return (resp.message.content or "").strip()


# ─────────────────────────────────────────────
# Google Gemini  (google-genai SDK)
# ─────────────────────────────────────────────

def _google_key() -> str:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")


def _build_gemini_tools(tools: list[dict]):
    from google.genai import types
    type_map = {
        "string":  types.Type.STRING,
        "integer": types.Type.INTEGER,
        "number":  types.Type.NUMBER,
        "boolean": types.Type.BOOLEAN,
        "array":   types.Type.ARRAY,
        "object":  types.Type.OBJECT,
    }
    declarations = []
    for t in tools:
        schema = t.get("input_schema", {})
        props  = {
            k: types.Schema(
                type=type_map.get(v.get("type", "string"), types.Type.STRING),
                description=v.get("description", ""),
            )
            for k, v in schema.get("properties", {}).items()
        }
        declarations.append(types.FunctionDeclaration(
            name=t["name"], description=t["description"],
            parameters=types.Schema(
                type=types.Type.OBJECT, properties=props,
                required=schema.get("required", []),
            ),
        ))
    return [types.Tool(function_declarations=declarations)]


def _gemini_loop(
    agent_name: str, system_prompt: str, user_message: str,
    tools: list[dict], tool_handlers: dict,
) -> tuple[str, list[dict]]:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError

    client  = genai.Client(api_key=_google_key())
    model   = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    cfg     = types.GenerateContentConfig(system_instruction=system_prompt, tools=_build_gemini_tools(tools))
    contents: list = [types.Content(role="user", parts=[types.Part(text=user_message)])]
    trace: list[dict] = []

    @retry(retry=retry_if_exception_type(ClientError),
           wait=wait_exponential(multiplier=2, min=5, max=60),
           stop=stop_after_attempt(5))
    def _call(c):
        return client.models.generate_content(model=model, contents=c, config=cfg)

    for _ in range(10):
        resp      = _call(contents)
        candidate = resp.candidates[0].content
        fn_calls  = [p.function_call for p in candidate.parts if p.function_call]
        if not fn_calls:
            return "".join(p.text for p in candidate.parts if hasattr(p, "text") and p.text).strip(), trace
        contents.append(candidate)
        result_parts = []
        for fc in fn_calls:
            t0 = time.time()
            try:
                result = tool_handlers[fc.name](**dict(fc.args or {}))
            except Exception as e:
                result = {"error": str(e)}
            trace.append(_entry(agent_name, fc.name, dict(fc.args or {}), result, t0))
            result_parts.append(types.Part(function_response=types.FunctionResponse(
                name=fc.name, response={"result": json.dumps(result, default=str)})))
        contents.append(types.Content(role="user", parts=result_parts))
    return "Max iterations reached.", trace


def _gemini_simple(system_prompt: str, user_message: str) -> str:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError

    client = genai.Client(api_key=_google_key())
    model  = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

    @retry(retry=retry_if_exception_type(ClientError),
           wait=wait_exponential(multiplier=2, min=5, max=60),
           stop=stop_after_attempt(5))
    def _call():
        return client.models.generate_content(
            model=model, contents=user_message,
            config=types.GenerateContentConfig(system_instruction=system_prompt))

    return _call().text.strip()


# ─────────────────────────────────────────────
# Anthropic Claude
# ─────────────────────────────────────────────

def _anthropic_loop(
    agent_name: str, system_prompt: str, user_message: str,
    tools: list[dict], tool_handlers: dict,
) -> tuple[str, list[dict]]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model  = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    msgs   = [{"role": "user", "content": user_message}]
    trace: list[dict] = []
    for _ in range(10):
        resp = client.messages.create(model=model, max_tokens=2048, system=system_prompt, tools=tools, messages=msgs)
        if resp.stop_reason == "end_turn":
            return next((b.text for b in resp.content if hasattr(b, "text")), ""), trace
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                t0 = time.time()
                try:
                    result = tool_handlers[block.name](**block.input)
                except Exception as e:
                    result = {"error": str(e)}
                trace.append(_entry(agent_name, block.name, block.input, result, t0))
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)})
        msgs.append({"role": "assistant", "content": resp.content})
        msgs.append({"role": "user",      "content": tool_results})
    return "Max iterations reached.", trace


def _anthropic_simple(system_prompt: str, user_message: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model  = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    resp   = client.messages.create(model=model, max_tokens=512, system=system_prompt,
                                    messages=[{"role": "user", "content": user_message}])
    return resp.content[0].text.strip()


# ─────────────────────────────────────────────
# Shared helper
# ─────────────────────────────────────────────

def _entry(agent_name: str, tool: str, inp: dict, output: Any, t0: float) -> dict:
    out = output if not isinstance(output, list) or len(output) <= 20 else output[:20]
    return {"agent": agent_name, "tool": tool, "input": inp, "output": out,
            "ts_ms": int(time.time() * 1000), "duration_ms": int((time.time() - t0) * 1000)}


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def run_agent_loop(
    agent_name: str, system_prompt: str, user_message: str,
    tools: list[dict], tool_handlers: dict[str, Any],
) -> tuple[str, list[dict]]:
    p = _provider()
    if p == "ollama":    return _ollama_loop(agent_name, system_prompt, user_message, tools, tool_handlers)
    if p == "google":    return _gemini_loop(agent_name, system_prompt, user_message, tools, tool_handlers)
    return _anthropic_loop(agent_name, system_prompt, user_message, tools, tool_handlers)


def simple_call(system_prompt: str, user_message: str) -> str:
    p = _provider()
    if p == "ollama":    return _ollama_simple(system_prompt, user_message)
    if p == "google":    return _gemini_simple(system_prompt, user_message)
    return _anthropic_simple(system_prompt, user_message)
