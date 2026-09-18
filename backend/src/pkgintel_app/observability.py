"""Chapter 16: `pkgintel-app` has had no tracing at all until now,
unlike reorder-app, whose own chapter 9 (Book 2) built it years before
this product existed. This module is this product's own first one,
following the exact same real, live-found lesson that chapter's own
`observability.py` already names: `@observe`'s default captures every
argument a decorated function receives, and `qdrant`, `embedder`, and
`model_client` are all real client objects carrying real API keys in
their own internal state. `capture_input=False` here for the identical
reason, `update_current_span(input=...)` records only the tenant id
and the question a person actually asked.

Multi-tenancy is the one real thing this product's own traces need
that reorder-app's single-caller traces never did: which tenant a
trace belongs to, tagged so a real operator can filter Langfuse's own
UI down to one tenant's traffic, across every product that shares this
same Langfuse project. `propagate_attributes`, not a method on the
client at all, guessed wrong the first time this chapter tried
`get_client().update_current_trace(tags=...)`, a real `AttributeError`
caught by actually running the orchestration tests, not assumed to
exist because an older Langfuse version's docs described it that way.
The real, current SDK sets trace-level attributes (`tags`, `user_id`,
`session_id`) through a context manager instead, entered as early as
possible inside the already-`@observe`d root span.
"""

from langfuse import get_client, observe, propagate_attributes
from reliable_agents_labs.cost import estimate_cost
from reliable_agents_labs.models import ModelResult

from pkgintel_app.tenant_rag import ask_rag_agent_for_tenant


@observe(name="pkgintel_app.ask_question", capture_input=False, capture_output=True)
async def ask_rag_agent_for_tenant_traced(
    tenant_id: str,
    question: str,
    qdrant=None,
    embedder=None,
    model_client=None,
    limit: int = 3,
    on_retrieval=None,
    on_model_result=None,
):
    with propagate_attributes(tags=["pkgintel-app", tenant_id], user_id=tenant_id):
        client = get_client()
        client.update_current_span(input={"tenant_id": tenant_id, "question": question})

        def _traced_model_result(result: ModelResult) -> None:
            # Chapter 15's own real dollar figure, attached to the trace
            # that produced it, not just returned to the API caller.
            client.update_current_span(metadata={"cost_usd": estimate_cost(result)})
            if on_model_result is not None:
                on_model_result(result)

        return await ask_rag_agent_for_tenant(
            tenant_id,
            question,
            qdrant=qdrant,
            embedder=embedder,
            model_client=model_client,
            limit=limit,
            on_retrieval=on_retrieval,
            on_model_result=_traced_model_result,
        )
