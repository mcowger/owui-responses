"""Overflow summary API helpers for the context filter."""

import asyncio
from typing import List, Optional

from owui_manifolds.filters.context_constants import SUMMARY_INPUT_TOKEN_CAP

try:
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None


class ContextSummaryMixin:
    def get_api_client(self):
        if not OPENAI_AVAILABLE or not self.valves.api_key:
            return None
        return AsyncOpenAI(
            base_url=self.valves.api_base,
            api_key=self.valves.api_key,
            timeout=self.valves.request_timeout,
        )

    async def safe_api_call(self, call_func, call_name: str):
        for attempt in range(self.valves.api_error_retry_times + 1):
            try:
                return await call_func()
            except Exception as e:
                if attempt < self.valves.api_error_retry_times:
                    self.debug_log(
                        1,
                        f"{call_name} failed (attempt {attempt + 1}), retrying in "
                        f"{self.valves.api_error_retry_delay}s: {str(e)[:150]}",
                        "🔄",
                    )
                    await asyncio.sleep(self.valves.api_error_retry_delay)
                else:
                    self.debug_log(
                        1, f"{call_name} failed permanently: {str(e)[:150]}", "❌"
                    )
                    return None
        return None

    def _messages_to_text(self, messages: List[dict]) -> str:
        parts = []
        for msg in messages:
            text = self.extract_text_from_content(msg.get("content", ""))
            if text:
                parts.append(f"{msg.get('role', '')}: {text}")
        return "\n\n".join(parts)

    def _cap_summary_input(self, text: str) -> str:
        """Keep only the most recent portion of the excluded text if it would be too
        large to safely hand to the summarization model in one call."""
        if self.count_tokens(text) <= SUMMARY_INPUT_TOKEN_CAP:
            return text
        # cl100k averages ~4 chars/token; trim from the front (oldest content).
        approx_chars = SUMMARY_INPUT_TOKEN_CAP * 4
        return text[-approx_chars:]

    async def generate_overflow_summary(
        self, excluded_messages: List[dict]
    ) -> Optional[str]:
        client = self.get_api_client()
        if not client:
            return None
        text = self._cap_summary_input(self._messages_to_text(excluded_messages))
        if not text.strip():
            return None

        async def _call():
            response = await client.chat.completions.create(
                model=self.valves.summary_model,
                messages=[
                    {"role": "system", "content": self.valves.summary_prompt},
                    {"role": "user", "content": text},
                ],
                max_tokens=self.valves.summary_max_tokens,
            )
            return response.choices[0].message.content

        result = await self.safe_api_call(_call, "overflow summary")
        return result.strip() if isinstance(result, str) and result.strip() else None
