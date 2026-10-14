"""Local routed-provider adapters for nonpublishing research review.

The adapter is deliberately narrow: Core supplies one exact local target and
one completion callable.  It does not select a provider, retry, fall back,
grant disclosure, fetch sources, or retain provider payloads.
"""

from __future__ import annotations

from typing import Callable

from pipeline.providers import normalize_structured_chat_completion
from pipeline.research_disclosure import ResearchProviderTarget


class LocalResearchClaimProvider:
    """Adapt one exact Core-owned local route to the research protocol."""

    def __init__(
        self,
        target: object,
        completion: Callable[[tuple[dict[str, str], dict[str, str]], str, dict[str, object]], object],
        *,
        available: bool = True,
    ) -> None:
        if not isinstance(target, ResearchProviderTarget) or target.deployment != "local":
            raise ValueError("research provider target must be local")
        if not callable(completion):
            raise TypeError("research completion callable is invalid")
        if not isinstance(available, bool):
            raise TypeError("research provider availability must be a boolean")
        self.target = target
        self._completion = completion
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def propose_claims(self, messages, *, model: str, schema: dict[str, object]) -> str:
        if not self._available:
            raise RuntimeError("research provider is unavailable")
        if model != self.target.model:
            raise ValueError("research provider model does not match its exact target")
        if not isinstance(messages, tuple) or len(messages) != 2:
            raise TypeError("research messages are invalid")
        if not isinstance(schema, dict) or not schema:
            raise TypeError("research response schema is invalid")
        response = self._completion(messages, model, schema)
        return normalize_structured_chat_completion(response).content


class LocalResearchRelationshipProvider(LocalResearchClaimProvider):
    """Adapt one exact Core-owned local route to claim-relationship review.

    This deliberately shares only the local-target and normalized-text seam
    with cited-claim review.  It does not turn relationship proposals into
    verification, a final answer, or a state-changing action.
    """

    def propose_relationships(self, messages, *, model: str, schema: dict[str, object]) -> str:
        return self.propose_claims(messages, model=model, schema=schema)


__all__ = ["LocalResearchClaimProvider", "LocalResearchRelationshipProvider"]
