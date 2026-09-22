"""Reusable LangChain agent. Conversation state lives in the checkpointer only."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq

from app.core.config import Settings
from app.core.exceptions import ChatError, LLMError
from app.core.logging import get_logger
from app.rag.prompts import resolve_system_prompt
from app.rag.retriever import BusinessRetriever
from app.rag.tools import BusinessContext, build_retrieve_tool

logger = get_logger(__name__)


@dynamic_prompt
def business_system_prompt(request: ModelRequest) -> str:
    context = getattr(request.runtime, "context", None)
    prompt = getattr(context, "system_prompt", None) if context is not None else None
    return resolve_system_prompt(prompt)


def create_chat_model(settings: Settings) -> Any:
    model = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key or None,
        temperature=0.2,
    )
    logger.info("llm_initialized", model=settings.groq_model)
    return model


def build_agent(
    *,
    model: Any,
    retriever: BusinessRetriever,
    checkpointer: Any,
) -> Any:
    """Cache only the compiled graph. Never store customer messages on the agent."""
    tool = build_retrieve_tool(retriever)
    return create_agent(
        model=model,
        tools=[tool],
        middleware=[business_system_prompt],
        context_schema=BusinessContext,
        checkpointer=checkpointer,
        name="business-assistant",
    )


def extract_final_answer(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content and not getattr(message, "tool_calls", None):
            content = message.content
            if isinstance(content, list):
                texts = [part.get("text", "") for part in content if isinstance(part, dict)]
                return "\n".join(text for text in texts if text).strip()
            return str(content).strip()
        if isinstance(message, dict) and message.get("type") == "ai" and message.get("content"):
            if message.get("tool_calls"):
                continue
            return str(message["content"]).strip()
    raise ChatError("The assistant did not produce a customer-facing answer")


async def invoke_agent(
    agent: Any,
    *,
    query: str,
    thread_id: str,
    context: BusinessContext,
) -> str:
    logger.info("agent_started")
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            config={"configurable": {"thread_id": thread_id}},
            context=context,
        )
    except ChatError:
        raise
    except Exception as exc:
        logger.error("agent_execution_failed")
        raise LLMError("The assistant could not complete this request") from exc
    answer = extract_final_answer(result)
    logger.info("agent_completed")
    return answer
