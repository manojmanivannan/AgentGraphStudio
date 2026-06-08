import asyncio
import logging
import math
import uuid

import dspy
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.config import settings
from canvas_server.database import get_session_factory
from canvas_server.models.canvas import AgentDocument, AgentDocumentChunk, AgentNode

logger = logging.getLogger("canvas_server.runner.rag_helper")


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into paragraph-aligned chunks of at most max_chars."""
    if not text:
        return []

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        p_len = len(p)
        if current_len + p_len > max_chars:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]
            current_len = p_len
        else:
            current_chunk.append(p)
            current_len += p_len + 2  # +2 for \n\n

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # Fallback split for any block that is still longer than max_chars
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > max_chars:
            for i in range(0, len(chunk), max_chars):
                final_chunks.append(chunk[i : i + max_chars])
        else:
            final_chunks.append(chunk)

    return final_chunks


def get_embedder() -> dspy.Embedder:
    provider = settings.mem0_embedder_provider
    model_name = settings.mem0_embedder_model

    if provider and not model_name.startswith(f"{provider}/"):
        model_name = f"{provider}/{model_name}"

    try:
        try:
            import litellm

            litellm.drop_params = True
        except ImportError:
            pass
    except Exception:
        pass

    kwargs = {}
    if provider == "openai":
        kwargs["encoding_format"] = "float"
        if "text-embedding-3" in model_name:
            kwargs["dimensions"] = settings.mem0_embedder_dimensions

    if provider == "ollama":
        embedder = dspy.Embedder(
            model=model_name, api_base=settings.llm_base_url, **kwargs
        )
    else:
        embedder = dspy.Embedder(
            model=model_name,
            api_key=settings.llm_api_key,
            api_base=settings.llm_base_url,
            **kwargs,
        )
    return embedder


class RAGIndexManager:
    _tasks: dict[uuid.UUID, asyncio.Task] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def trigger_reindex(cls, agent_id: uuid.UUID):
        """Trigger a background task to index (or re-index) all documents for the agent."""
        async with cls._lock:
            # Cancel any running indexing task for this agent
            if agent_id in cls._tasks:
                task = cls._tasks[agent_id]
                if not task.done():
                    task.cancel()
                    logger.info(
                        "Cancelled active indexing task for agent: %s", agent_id
                    )

            cls._tasks[agent_id] = asyncio.create_task(cls._reindex_agent(agent_id))

    @classmethod
    async def _reindex_agent(cls, agent_id: uuid.UUID):
        try:
            logger.info("Starting background RAG indexing for agent: %s", agent_id)
            factory = get_session_factory()
            async with factory() as session:
                # 1. Fetch agent and its documents
                stmt = select(AgentNode).where(AgentNode.id == agent_id)
                res = await session.execute(stmt)
                agent = res.scalar_one_or_none()
                if not agent:
                    logger.warning("RAG indexing failed: agent %s not found", agent_id)
                    return

                # Fetch documents
                stmt = select(AgentDocument).where(
                    AgentDocument.agent_node_id == agent_id
                )
                res = await session.execute(stmt)
                documents = res.scalars().all()

                # 2. Delete existing chunks for this agent
                await session.execute(
                    delete(AgentDocumentChunk).where(
                        AgentDocumentChunk.agent_node_id == agent_id
                    )
                )
                await session.flush()

                if not documents:
                    await session.commit()
                    logger.info("No documents to index for agent: %s", agent_id)
                    return

                # 3. Chunk documents
                all_chunks = []
                for doc in documents:
                    chunks = chunk_text(doc.content, agent.rag_chunk_size)
                    for idx, chunk_content in enumerate(chunks):
                        all_chunks.append(
                            {
                                "canvas_id": agent.canvas_id,
                                "agent_node_id": agent_id,
                                "document_id": doc.id,
                                "chunk_index": idx,
                                "content": chunk_content,
                            }
                        )

                if not all_chunks:
                    await session.commit()
                    return

                # 4. Generate embeddings
                texts = [c["content"] for c in all_chunks]
                try:
                    embedder = get_embedder()
                    embeddings_raw = embedder(texts)

                    # Convert to standard Python float lists if they are numpy arrays or other wrappers
                    embeddings = []
                    for vec in embeddings_raw:
                        if hasattr(vec, "tolist"):
                            embeddings.append(vec.tolist())
                        else:
                            embeddings.append(list(vec))
                except Exception as e:
                    logger.warning(
                        "Failed to generate embeddings during index: %s. Using zero vector fallback.",
                        e,
                    )
                    dims = settings.mem0_embedder_dimensions
                    embeddings = [[0.0] * dims for _ in range(len(all_chunks))]

                # 5. Insert chunks with embeddings
                for chunk_data, emb in zip(all_chunks, embeddings, strict=False):
                    chunk_obj = AgentDocumentChunk(
                        id=uuid.uuid4(),
                        canvas_id=chunk_data["canvas_id"],
                        agent_node_id=chunk_data["agent_node_id"],
                        document_id=chunk_data["document_id"],
                        chunk_index=chunk_data["chunk_index"],
                        content=chunk_data["content"],
                        embedding=emb,
                    )
                    session.add(chunk_obj)

                await session.commit()
                logger.info(
                    "Successfully indexed %d chunks for agent: %s",
                    len(all_chunks),
                    agent_id,
                )
        except asyncio.CancelledError:
            logger.info("RAG indexing task for agent %s was cancelled", agent_id)
            raise
        except Exception as e:
            logger.error(
                "Error running RAG indexing for agent %s: %s",
                agent_id,
                e,
                exc_info=True,
            )


async def run_rag_search(
    agent_id: uuid.UUID, query: str, session: AsyncSession | None = None
) -> str:
    """Embed the user's query and retrieve top 5 matching chunks from database using similarity search."""
    if not session:
        factory = get_session_factory()
        async with factory() as session:
            return await _run_rag_search_impl(agent_id, query, session)
    return await _run_rag_search_impl(agent_id, query, session)


async def _run_rag_search_impl(
    agent_id: uuid.UUID, query: str, session: AsyncSession
) -> str:
    # 1. Embed query
    try:
        embedder = get_embedder()
        query_embs = embedder([query])
        query_emb_raw = query_embs[0]
        query_embedding = (
            query_emb_raw.tolist()
            if hasattr(query_emb_raw, "tolist")
            else list(query_emb_raw)
        )
    except Exception as e:
        logger.warning(
            "Query embedding failed: %s. Falling back to first few corpus chunks.", e
        )
        # Fallback if embedding fails: fetch first 5 chunks by index
        stmt = (
            select(AgentDocumentChunk)
            .where(AgentDocumentChunk.agent_node_id == agent_id)
            .order_by(AgentDocumentChunk.chunk_index.asc())
            .limit(5)
        )
        res = await session.execute(stmt)
        chunks = res.scalars().all()
        return "\n\n---\n\n".join([c.content for c in chunks])

    # 2. Retrieve top matching chunks
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind else "postgresql"

    if dialect_name == "postgresql":
        # pgvector similarity search using the vector cosine distance operator.
        # Use op('<=>') instead of the comparator helper to avoid SQLAlchemy
        # TypeDecorator comparator resolution issues.
        stmt = (
            select(AgentDocumentChunk)
            .where(AgentDocumentChunk.agent_node_id == agent_id)
            .order_by(AgentDocumentChunk.embedding.op("<=>")(query_embedding))
            .limit(5)
        )
        res = await session.execute(stmt)
        chunks = res.scalars().all()
    else:
        # SQLite / other dialects: retrieve all chunks and compute cosine similarity in Python
        stmt = select(AgentDocumentChunk).where(
            AgentDocumentChunk.agent_node_id == agent_id
        )
        res = await session.execute(stmt)
        all_chunks = res.scalars().all()
        if not all_chunks:
            return ""

        # Compute cosine similarity in Python
        scored_chunks = []
        for c in all_chunks:
            # c.embedding is stored as list of floats
            emb = c.embedding
            if emb:
                dot_product = sum(
                    a * b for a, b in zip(emb, query_embedding, strict=False)
                )
                mag1 = math.sqrt(sum(a * a for a in emb))
                mag2 = math.sqrt(sum(b * b for b in query_embedding))
                score = dot_product / (mag1 * mag2) if (mag1 > 0 and mag2 > 0) else 0.0
            else:
                score = 0.0
            scored_chunks.append((score, c))

        # Sort descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        chunks = [c for score, c in scored_chunks[:5]]

    if not chunks:
        logger.info("RAG search: no chunks found for agent %s", agent_id)
        return ""

    logger.debug("RAG search complete, retrieved %d passages", len(chunks))
    return "\n\n---\n\n".join([c.content for c in chunks])
