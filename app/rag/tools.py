"""LangChain retrieval tool. Tenant isolation is enforced in runtime context."""

from __future__ import annotations

from dataclasses import dataclass

from langchain.tools import ToolRuntime, tool

from app.core.logging import get_logger
from app.rag.retriever import BusinessRetriever

logger = get_logger(__name__)


@dataclass
class BusinessContext:
    business_uuid: str
    active_namespace: str
    user_phone_number: str
    system_prompt: str = ""


def build_retrieve_tool(retriever: BusinessRetriever):
    @tool
    def retrieve_business_information(
        query: str,
        runtime: ToolRuntime[BusinessContext],
    ) -> str:
        """Search this business knowledge base for facts that answer the customer.

        Use this whenever the customer asks about products, services, policies,
        hours, prices, or any other business-specific information.
        """
        context = runtime.context
        if context is None or not context.business_uuid:
            return "Business knowledge is not available."

        # Namespace is supplied by the server after reading MongoDB. The model
        # cannot choose another tenant's Pinecone namespace.
        chunks = retriever.search(context.business_uuid, context.active_namespace, query)
        if not chunks:
            return "No matching business knowledge was found for this question."

        lines = [chunk.text for chunk in chunks]
        return "Business knowledge:\n" + "\n".join(f"* {line}" for line in lines)

    return retrieve_business_information
