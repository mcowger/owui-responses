"""Token counting and budget helpers for the context window manager."""

from typing import Any, Dict, List, Optional

from owui_manifolds.filters.context_constants import MESSAGE_OVERHEAD_TOKENS

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None


class TokenCalculator:
    """Token counter, backed by tiktoken when available."""

    def __init__(self):
        self._encoding = None
        self.model_info: Optional[Dict[str, Any]] = None

    def set_model_info(self, model_info: dict):
        self.model_info = model_info

    def get_encoding(self):
        if not TIKTOKEN_AVAILABLE:
            return None
        if self._encoding is None:
            try:
                self._encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass
        return self._encoding

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        encoding = self.get_encoding()
        if encoding:
            try:
                return len(encoding.encode(str(text)))
            except Exception:
                pass
        return len(str(text)) // 4

    def calculate_image_tokens(self) -> int:
        """Flat per-image token estimate. Images are never inspected or described -
        just budgeted for with a flat constant (Valves.default_image_tokens)."""
        if self.model_info:
            return self.model_info.get("image_tokens", 1500)
        return 1500


class ContextTokenMixin:
    def count_tokens(self, text: str) -> int:
        return self.token_calculator.count_tokens(text)

    def extract_text_from_content(self, content) -> str:
        if isinstance(content, list):
            return " ".join(
                item.get("text", "") for item in content if item.get("type") == "text"
            )
        return str(content) if content else ""

    def count_message_tokens(self, message: dict) -> int:
        if not message:
            return 0
        content = message.get("content", "")
        total = 0
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    total += self.count_tokens(item.get("text", ""))
                elif item.get("type") == "image_url":
                    total += self.token_calculator.calculate_image_tokens()
        else:
            total = self.count_tokens(content)
        return total + MESSAGE_OVERHEAD_TOKENS

    def count_messages_tokens(self, messages: List[dict]) -> int:
        return sum(self.count_message_tokens(m) for m in messages)

    def calculate_target_tokens(
        self, model_name: str, current_user_tokens: int, context_target_percent: int
    ) -> int:
        safe_limit = self.get_model_token_limit(model_name)
        budget_limit = safe_limit * context_target_percent / 100
        response_buffer = min(
            self.valves.response_buffer_max,
            max(
                self.valves.response_buffer_min,
                int(safe_limit * self.valves.response_buffer_percent / 100),
            ),
        )
        target = budget_limit - current_user_tokens - response_buffer
        return int(max(target, self.valves.min_target_tokens))
