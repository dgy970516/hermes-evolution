import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("hermes.llm")


@dataclass
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.1

    @classmethod
    def from_dict(cls, d: dict) -> "LLMConfig":
        return cls(
            provider=d.get("provider", "openai"),
            model=d.get("model", "gpt-4o-mini"),
            api_key=d.get("api_key", ""),
            base_url=d.get("base_url", ""),
            max_tokens=d.get("max_tokens", 4096),
            temperature=d.get("temperature", 0.1),
        )


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None

    async def initialize(self):
        p = self.config.provider
        if p == "openai" or p == "openai_compatible":
            await self._init_openai()
        elif p == "anthropic":
            await self._init_anthropic()
        else:
            raise ValueError(f"Unsupported LLM provider: {p}")
        logger.info(f"LLM initialized: provider={p}, model={self.config.model}")

    async def _init_openai(self):
        from openai import AsyncOpenAI
        kwargs = {"api_key": self.config.api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        self._client = AsyncOpenAI(**kwargs)

    async def _init_anthropic(self):
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic(api_key=self.config.api_key)

    async def chat(self, system_prompt: str, user_prompt: str, output_json: bool = False) -> str:
        p = self.config.provider
        if p == "openai" or p == "openai_compatible":
            return await self._chat_openai(system_prompt, user_prompt, output_json)
        elif p == "anthropic":
            return await self._chat_anthropic(system_prompt, user_prompt, output_json)
        raise ValueError(f"Unsupported provider: {p}")

    async def chat_stream(self, system_prompt: str, user_prompt: str):
        """Stream LLM response token by token. Yields text chunks."""
        p = self.config.provider
        if p == "openai" or p == "openai_compatible":
            async for chunk in self._chat_openai_stream(system_prompt, user_prompt):
                yield chunk
        elif p == "anthropic":
            async for chunk in self._chat_anthropic_stream(system_prompt, user_prompt):
                yield chunk
        else:
            yield f"Unsupported provider: {p}"

    async def _chat_openai(self, system_prompt: str, user_prompt: str, output_json: bool) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs = dict(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        if output_json:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def _chat_anthropic(self, system_prompt: str, user_prompt: str, output_json: bool) -> str:
        resp = await self._client.messages.create(
            model=self.config.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        text = resp.content[0].text if resp.content else ""
        if output_json:
            text = self._extract_json(text)
        return text

    async def _chat_openai_stream(self, system_prompt: str, user_prompt: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        stream = await self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def _chat_anthropic_stream(self, system_prompt: str, user_prompt: str):
        async with self._client.messages.stream(
            model=self.config.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def _extract_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start:end + 1]
        return text

    async def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        text = await self.chat(system_prompt, user_prompt, output_json=True)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"LLM returned non-JSON, falling back: {text[:100]}")
            return {}
