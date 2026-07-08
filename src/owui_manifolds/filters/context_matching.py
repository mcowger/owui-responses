"""Model-name matching for context-window budgets."""

import fnmatch
from typing import Any, Dict, List, Tuple

from owui_manifolds.filters.context_constants import (
    NO_TABLE_ROWS_FALLBACK_CAP_PERCENT,
    NO_TABLE_ROWS_FALLBACK_LIMIT,
    NO_TABLE_ROWS_FALLBACK_WARNING_PERCENT,
)


class ModelMatcher:
    """Matches a model name to a context-window size and cap/warning percents using
    an admin-editable table (see Filter.Valves.model_token_table) of

        pattern,max_tokens,cap_percent,warning_percent

    rows, instead of a hardcoded pattern list. `pattern` is a glob (fnmatch-style,
    e.g. "claude-sonnet-4-5*") matched against the lowercased model name; rows are
    tried in order and the first match wins, so more specific patterns must be
    listed before broader ones (e.g. "claude-sonnet-4-5*" before "claude-sonnet-*").
    A trailing "*" row acts as the catch-all default for unrecognized models.
    """

    def parse_table(self, table_text: str) -> List[Tuple[str, int, int, int]]:
        rows = []
        for raw_line in (table_text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = [f.strip() for f in line.split(",")]
            if len(fields) != 4:
                continue
            pattern, max_tokens, cap_percent, warning_percent = fields
            try:
                rows.append(
                    (
                        pattern.lower(),
                        int(max_tokens),
                        int(cap_percent),
                        int(warning_percent),
                    )
                )
            except ValueError:
                continue
        return rows

    def match_model(self, model_name: str, table_text: str) -> Dict[str, Any]:
        model_lower = (model_name or "").lower().strip()
        # Pipe/manifold ids look like "<pipe_id>.<provider>/<model>"; the bare
        # upstream model name is always everything after the last "/", so slicing
        # there alone is sufficient. (Deliberately *not* also splitting on "."
        # first - that would mangle plain versioned names with no pipe prefix at
        # all, like "gpt-5.4-mini" or "glm-5.2-flash".)
        model_lower = model_lower.rsplit("/", 1)[-1]

        if model_lower:
            for pattern, limit, cap_percent, warning_percent in self.parse_table(
                table_text
            ):
                if fnmatch.fnmatchcase(model_lower, pattern):
                    return {
                        "limit": limit,
                        "cap_percent": cap_percent,
                        "warning_percent": warning_percent,
                        "match_type": "matched",
                        "matched_pattern": pattern,
                    }

        # Only reachable if model_token_table has no rows at all (its default
        # trailing "*" row otherwise matches everything).
        return {
            "limit": NO_TABLE_ROWS_FALLBACK_LIMIT,
            "cap_percent": NO_TABLE_ROWS_FALLBACK_CAP_PERCENT,
            "warning_percent": NO_TABLE_ROWS_FALLBACK_WARNING_PERCENT,
            "match_type": "default",
            "hint": f"model_token_table has no usable rows; using built-in fallback for '{model_name}'.",
        }
