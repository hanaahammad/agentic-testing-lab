"""The agent's 'brain'. Three interchangeable brains with the same interface:

  DemoLLM    scripted, free, no model at all (replays prepared outputs)
  ClaudeLLM  Claude through the Anthropic API (cloud, needs an API key)
  OllamaLLM  any model served by Ollama on this machine or the network (local, private, free)

Interface used by the pipeline and the explorer:
  complete(system, prompt) -> str
  complete_json(system, prompt) -> dict | list       (validated, one repair round)
  complete_code(system, prompt) -> str               (the python block of the answer)
  tool_session(system, tools, first_message) -> ToolSession   (for live exploration)
"""
import json
import re
import time

import requests


class DemoLLM:
    """Scripted brain: replays canned outputs so the whole cycle runs without an API key."""

    demo = True
    kind = "demo"
    model = "demo"
    label = "Demo (scripted)"


# ---------------------------------------------------------------- shared helpers
def extract_json(text: str):
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    candidate = m.group(1) if m else text
    starts = [i for i in (candidate.find("{"), candidate.find("[")) if i >= 0]
    if not starts:
        raise ValueError("No JSON found in the answer")
    start = min(starts)
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    try:
        return json.loads(candidate[start: end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if blocks:
        return max(blocks, key=len).strip() + "\n"   # the longest block is the module
    return text.strip() + "\n"


class _Base:
    demo = False

    def complete(self, system: str, prompt: str, max_tokens: int = 8000, json_mode: bool = False) -> str:
        raise NotImplementedError

    def complete_json(self, system: str, prompt: str, max_tokens: int = 8000):
        text = self.complete(system, prompt, max_tokens, json_mode=True)
        try:
            return extract_json(text)
        except ValueError as e:
            fix = self.complete("You repair malformed JSON. Reply with valid JSON only, nothing else.",
                                f"This answer is not valid JSON ({e}). Return the same content as valid JSON:\n\n{text}",
                                max_tokens, json_mode=True)
            return extract_json(fix)

    def complete_code(self, system: str, prompt: str, max_tokens: int = 12000) -> str:
        return extract_code(self.complete(system, prompt, max_tokens))


# ---------------------------------------------------------------- Claude (Anthropic API)
class ClaudeLLM(_Base):
    kind = "claude"

    def __init__(self, api_key: str, model: str):
        import anthropic

        if not api_key:
            raise ValueError("An Anthropic API key is required for the Claude brain.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.label = f"Claude · {model}"

    def complete(self, system, prompt, max_tokens=8000, json_mode=False):
        resp = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in resp.content if b.type == "text")

    def tool_session(self, system, tools, first_message):
        return _ClaudeToolSession(self, system, tools, first_message)


class _ClaudeToolSession:
    def __init__(self, llm, system, tools, first):
        self.llm, self.system, self.tools = llm, system, tools
        self.messages = [{"role": "user", "content": first}]

    def step(self):
        """One model turn -> (texts, calls); calls = [{'id', 'name', 'input'}]; empty calls = finished."""
        resp = self.llm.client.messages.create(model=self.llm.model, max_tokens=2000, system=self.system,
                                               tools=self.tools, messages=self.messages)
        self.messages.append({"role": "assistant", "content": resp.content})
        texts = [b.text.strip() for b in resp.content if b.type == "text" and b.text.strip()]
        calls = [{"id": b.id, "name": b.name, "input": dict(b.input)} for b in resp.content if b.type == "tool_use"]
        return texts, (calls if resp.stop_reason == "tool_use" else [])

    def answer(self, results):
        """results = [(call, result_dict)]"""
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(r)[:6000]} for c, r in results]})


# ---------------------------------------------------------------- Ollama (local models)
class OllamaLLM(_Base):
    """A model served by Ollama. Nothing leaves the machine (or your network) when Ollama runs locally."""

    kind = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", num_ctx: int = 16384,
                 temperature: float = 0.2, timeout: int = 900):
        if not model:
            raise ValueError("Choose an Ollama model (run `ollama pull qwen2.5-coder:7b` first).")
        self.model, self.base = model, base_url.rstrip("/")
        self.options = {"num_ctx": num_ctx, "temperature": temperature}
        self.timeout = timeout
        self.label = f"Ollama · {model}"

    def _chat(self, messages, tools=None, json_mode=False, max_tokens=4096):
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": {**self.options, "num_predict": max_tokens}}
        if tools:
            body["tools"] = tools
        if json_mode:
            body["format"] = "json"
        for attempt in (1, 2):   # one retry: Ollama answers 500 while it (re)loads a model under memory pressure
            try:
                r = requests.post(self.base + "/api/chat", json=body, timeout=self.timeout)
            except requests.RequestException as e:
                raise RuntimeError(f"Ollama is not reachable at {self.base}: {e}") from e
            if r.status_code == 404:
                raise RuntimeError(f"Ollama has no model '{self.model}'. Run: ollama pull {self.model}")
            if r.status_code < 500 or attempt == 2:
                break
            time.sleep(5)
        if r.status_code >= 400:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text[:300]} (close other models or use a smaller one)")
        return r.json()["message"]

    def complete(self, system, prompt, max_tokens=8000, json_mode=False):
        msg = self._chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                         json_mode=json_mode, max_tokens=min(max_tokens, 6000))
        return msg.get("content", "")

    def tool_session(self, system, tools, first_message):
        return _OllamaToolSession(self, system, tools, first_message)


class _OllamaToolSession:
    def __init__(self, llm, system, tools, first):
        self.llm = llm
        # Ollama takes OpenAI-style function tools
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                        "parameters": t["input_schema"]}} for t in tools]
        self.messages = [{"role": "system", "content": system}, {"role": "user", "content": first}]
        self.n = 0

    def step(self):
        msg = self.llm._chat(self.messages, tools=self.tools, max_tokens=1500)
        self.messages.append(msg)
        content = (msg.get("content") or "").strip()
        raw = msg.get("tool_calls") or []
        if not raw and content:
            # Some models (qwen2.5-coder) write the call as JSON text instead of using the tool-call field.
            raw, content = text_tool_calls(content, {t["function"]["name"] for t in self.tools})
        texts = [content] if content else []
        calls = []
        for tc in raw:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            self.n += 1
            calls.append({"id": f"call_{self.n}", "name": fn.get("name", ""), "input": args})
        return texts, calls

    def answer(self, results):
        for c, r in results:
            self.messages.append({"role": "tool", "tool_name": c["name"], "content": json.dumps(r)[:6000]})


def text_tool_calls(text: str, names: set) -> tuple[list, str]:
    """Find {"name": <tool>, "arguments": {...}} objects written as text; return (calls, remaining text)."""
    dec, calls, keep, i = json.JSONDecoder(), [], [], 0
    while i < len(text):
        j = text.find("{", i)
        if j < 0:
            keep.append(text[i:])
            break
        keep.append(text[i:j])
        try:
            obj, end = dec.raw_decode(text, j)
        except json.JSONDecodeError:
            keep.append("{")
            i = j + 1
            continue
        items = obj if isinstance(obj, list) else [obj]
        found = [o for o in items if isinstance(o, dict) and o.get("name") in names]
        if found:
            calls += [{"function": {"name": o["name"], "arguments": o.get("arguments") or o.get("parameters") or {}}}
                      for o in found]
        else:
            keep.append(text[j:end])
        i = end
    rest = re.sub(r"```(?:json)?\s*```|</?tool_call>", "", "".join(keep)).strip()
    return calls, rest


def ollama_models(base_url: str = "http://localhost:11434") -> tuple[list[str], str]:
    """Installed Ollama models, or ([], reason)."""
    try:
        r = requests.get(base_url.rstrip("/") + "/api/tags", timeout=4)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", [])), ""
    except requests.RequestException as e:
        return [], f"Ollama is not reachable at {base_url} ({e.__class__.__name__}). Is the Ollama app running?"


# ---------------------------------------------------------------- factory
def make_llm(demo: bool = False, api_key: str = "", model: str = "", brain: str = "",
             ollama_url: str = "http://localhost:11434"):
    """brain: 'demo' | 'claude' | 'ollama' (the old `demo` flag still works)."""
    brain = brain or ("demo" if demo else "claude")
    if brain == "demo":
        return DemoLLM()
    if brain == "ollama":
        return OllamaLLM(model, ollama_url)
    from .config import DEFAULT_MODEL

    return ClaudeLLM(api_key, model or DEFAULT_MODEL)
