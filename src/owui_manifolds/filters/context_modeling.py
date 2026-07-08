"""Model selection helpers for the context filter."""

from typing import Any, Dict


class ContextModelingMixin:
    def is_model_excluded(self, model_name: str) -> bool:
        if not self.valves.excluded_models or not model_name:
            return False
        excluded_list = [
            m.strip().lower()
            for m in self.valves.excluded_models.split(",")
            if m.strip()
        ]
        model_lower = model_name.lower()
        return any(excluded in model_lower for excluded in excluded_list)

    def analyze_model(self, model_name: str) -> Dict[str, Any]:
        model_info = self.model_matcher.match_model(
            model_name, self.valves.model_token_table
        )
        model_info["image_tokens"] = self.valves.default_image_tokens
        self.token_calculator.set_model_info(model_info)
        self._current_model_info = model_info
        self.debug_log(
            1,
            f"Model: {model_name} -> limit={model_info['limit']:,} "
            f"cap%={model_info['cap_percent']} warning%={model_info['warning_percent']} "
            f"match={model_info.get('match_type')} pattern={model_info.get('matched_pattern')}",
            "🎯",
        )
        return model_info

    def get_model_token_limit(self, model_name: str) -> int:
        model_info = self.analyze_model(model_name)
        return int(model_info["limit"] * model_info["cap_percent"] / 100)
