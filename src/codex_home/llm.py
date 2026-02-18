from __future__ import annotations

from dataclasses import dataclass

import httpx

from codex_home.config import Settings


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    model: str


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, model: str, prompt: str, max_tokens: int = 400) -> LLMResult:
        if self.settings.is_fast_mode():
            synthetic = (
                "FAST_MODE_RESPONSE\n"
                "Generated deterministic planning text.\n"
                f"Prompt length: {len(prompt)} characters."
            )
            prompt_tokens = max(1, len(prompt) // 4)
            completion_tokens = max(1, len(synthetic) // 4)
            return LLMResult(
                content=synthetic,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=round((prompt_tokens + completion_tokens) * 0.000001, 6),
                model=model,
            )

        headers = {"Content-Type": "application/json"}
        if self.settings.litellm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.litellm_api_key}"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{self.settings.litellm_base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        # LiteLLM can emit cost in additional fields; default to 0 if absent.
        cost = float(data.get("_hidden_params", {}).get("response_cost", 0.0))
        return LLMResult(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            model=model,
        )
