"""Shared test fakes. Copied from `reliable-agents-labs`' own tests/
fakes.py rather than imported, same reasoning as every product repo in
this series: test doubles live under `tests/` there and are not part
of the installed package.
"""

from reliable_agents_labs.models import ModelResult


class ScriptedModelClient:
    """A deterministic stand-in for any real ModelClient adapter. Feed it a
    list of canned ModelResults; each call to generate() returns the next
    one.
    """

    def __init__(self, scripted_results: list[ModelResult]) -> None:
        self._results = iter(scripted_results)

    async def generate(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
    ) -> ModelResult:
        return next(self._results)


class FakeEmbeddingClient:
    """Returns the same fixed vector regardless of input text. Chapter
    11's own tests need this precisely because it removes semantic
    similarity as a variable: if two tenants' identical vectors still
    never cross into each other's results, isolation comes from the
    collection boundary itself, not from the embedding happening not to
    match.
    """

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, text: str) -> list[float]:
        return self._vector
