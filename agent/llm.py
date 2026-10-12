"""The agent's 'brain': Claude via the Anthropic API, or a scripted demo brain (no key needed)."""
import json
import re


class DemoLLM:
    """Scripted brain: replays canned outputs so the whole cycle runs without an API key."""

    demo = True
    model = "demo"


class ClaudeLLM:
    demo = False

    def __init__(self, api_key: str, model: str):
        import anthropic

        if not api_key:
            raise ValueError("An Anthropic API key is required (or use demo mode).")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, system: str, prompt: str, max_tokens: int = 8000) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def complete_json(self, system: str, prompt: str, max_tokens: int = 8000):
        text = self.complete(system, prompt, max_tokens)
        try:
            return extract_json(text)
        except ValueError:
            fix = self.complete(
                "You repair malformed JSON. Reply with valid JSON only.",
                f"Return this as valid JSON, nothing else:\n\n{text}",
                max_tokens,
            )
            return extract_json(fix)

    def complete_code(self, system: str, prompt: str, max_tokens: int = 12000) -> str:
        text = self.complete(system, prompt, max_tokens)
        m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
        return (m.group(1) if m else text).strip() + "\n"


def extract_json(text: str):
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    candidate = m.group(1) if m else text
    start = min([i for i in (candidate.find("{"), candidate.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("No JSON found")
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(str(e)) from e


def make_llm(demo: bool, api_key: str = "", model: str = ""):
    if demo:
        return DemoLLM()
    from .config import DEFAULT_MODEL

    return ClaudeLLM(api_key, model or DEFAULT_MODEL)
