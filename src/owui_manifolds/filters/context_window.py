"""Context window selection and early-compression prompting."""

from typing import Any, Callable, Dict, List, Tuple


class ContextWindowMixin:
    async def _ask_compress_now(
        self, event_call: Callable, history_tokens: int, budget: int
    ) -> bool:
        """Blocks (via the client websocket) until the user answers a Yes/Cancel
        confirmation dialog, or times out. Any non-`True` result (decline,
        timeout, disconnected session) is treated as "don't compress yet"."""
        percent_used = int(history_tokens / budget * 100) if budget else 100
        try:
            result = await event_call(
                {
                    "type": "confirmation",
                    "data": {
                        "title": "Context usage warning",
                        "message": (
                            f"Conversation history is at {history_tokens:,} tokens "
                            f"({percent_used}% of your {budget:,}-token budget). Compress "
                            "older messages now to free up space, or continue as-is?"
                        ),
                    },
                }
            )
        except Exception as e:
            self.debug_log(1, f"Warning-threshold confirmation call failed: {e}", "⚠️")
            return False
        return result is True

    async def build_context_window(
        self,
        history_messages: List[dict],
        budget: int,
        anchor_n: int,
        recent_n: int,
        covered_upto: int,
        blocks: List[Dict[str, str]],
        force: bool = False,
    ) -> Tuple[List[dict], int, List[Dict[str, str]], Dict[str, Any]]:
        """Assemble anchor + persisted summary blocks + verbatim "pending" middle +
        recent messages, and compare THAT candidate to budget - not the raw
        history size, which never shrinks and would re-trigger this on every turn.

        Only when the candidate still doesn't fit do we fold all of `pending`
        into one new, permanently-frozen summary block. Blocks are generated
        exactly once and never re-summarized, so a long conversation accumulates
        a short, append-only list of summaries instead of repeatedly
        re-summarizing (and degrading) the same content.

        `force=True` folds `pending` immediately regardless of whether the
        candidate fits the budget - used when the user opts to compress early
        via the warning-threshold prompt, ahead of the hard cap.

        NOTE: `blocks` is intentionally left unbounded here - it is never capped
        or merged. For a pathologically long-lived chat (many fold events) this
        list would itself keep growing the token cost of the "blocks" section.
        Deferred for now per explicit decision; revisit with e.g. a
        max-block-count valve that merges the oldest two blocks if this ever
        becomes a real problem in practice.
        """
        n = len(history_messages)
        if n == 0:
            return (
                [],
                covered_upto,
                blocks,
                {
                    "kept": 0,
                    "summarized_count": 0,
                    "block_count": len(blocks),
                    "folded": False,
                },
            )

        anchor_n = max(0, min(anchor_n, n))
        recent_n = max(0, min(recent_n, n))
        recent_start = max(anchor_n, n - recent_n)
        covered_upto = max(anchor_n, min(covered_upto, recent_start))

        anchor = history_messages[:anchor_n]
        pending = history_messages[covered_upto:recent_start]
        recent = history_messages[recent_start:]

        def block_messages(block_list: List[Dict[str, str]]) -> List[dict]:
            return [
                {
                    "role": "system",
                    "content": f"[Summary of earlier conversation]\n{b['text']}",
                }
                for b in block_list
            ]

        candidate = anchor + block_messages(blocks) + pending + recent
        folded = False

        if (
            pending
            and self.valves.enable_overflow_summary
            and (force or self.count_messages_tokens(candidate) > budget)
        ):
            summary_text = await self.generate_overflow_summary(pending)
            if summary_text:
                blocks = blocks + [{"text": summary_text}]
                covered_upto = recent_start
                folded = True
                pending = []
                candidate = anchor + block_messages(blocks) + pending + recent

        stats = {
            "kept": len(anchor) + len(pending) + len(recent),
            "summarized_count": covered_upto - anchor_n,
            "block_count": len(blocks),
            "folded": folded,
        }
        return candidate, covered_upto, blocks, stats
