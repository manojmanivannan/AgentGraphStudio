import asyncio
import logging
import math
import re
import uuid

import dspy
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.database import get_session_factory
from canvas_server.exceptions import RAGEmbeddingError
from canvas_server.models.canvas import AgentDocument, AgentDocumentChunk, AgentNode
from canvas_server.provider_config import ProviderConfig, get_provider_config

logger = logging.getLogger("canvas_server.runner.rag_helper")


_SENTENCE_RE = re.compile(r'[^.!?]+(?:[.!?]+["”\']*)?', flags=re.MULTILINE)
_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def _token_count(text: str) -> int:
    return len(_TOKEN_RE.findall(text))


def _split_sentence_tokens(sentence: str, max_tokens: int) -> list[str]:
    tokens = sentence.split()
    if not tokens:
        return []

    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunks.append(" ".join(tokens[i : i + max_tokens]))
    return chunks


def _split_into_sentences(paragraph: str) -> list[str]:
    paragraph = paragraph.replace("\n", " ").strip()
    return [s.strip() for s in _SENTENCE_RE.findall(paragraph) if s.strip()]


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into sentence-aligned chunks using a simple regex token count."""
    if not text:
        return []

    max_tokens = max(1, max_chars)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: list[str] = []

    current_sentences: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        if current_sentences:
            current_sentences.append("\n\n")

        sentences = _split_into_sentences(paragraph)
        for sentence in sentences:
            sentence_tokens = _token_count(sentence)
            if sentence_tokens > max_tokens:
                if current_sentences:
                    chunks.append(" ".join(current_sentences).strip())
                    current_sentences = []
                    current_tokens = 0
                chunks.extend(_split_sentence_tokens(sentence, max_tokens))
                continue

            if current_tokens and current_tokens + sentence_tokens > max_tokens:
                chunks.append(" ".join(current_sentences).strip())
                current_sentences = []
                current_tokens = 0

            current_sentences.append(sentence)
            current_tokens += sentence_tokens

    if current_sentences:
        chunks.append(" ".join(current_sentences).strip())

    return chunks


def get_embedder(config: ProviderConfig | None = None) -> dspy.Embedder:
    active = config or get_provider_config()
    provider = active.llm_provider_type
    model_name = active.mem0_embedder_model

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
            kwargs["dimensions"] = active.mem0_embedder_dimensions

    if provider == "ollama":
        embedder = dspy.Embedder(
            model=model_name, api_base=active.llm_base_url, **kwargs
        )
    else:
        embedder = dspy.Embedder(
            model=model_name,
            api_key=active.llm_api_key,
            api_base=active.llm_base_url,
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
    async def wait_for_indexing(cls, agent_id: uuid.UUID):
        """Wait for an active indexing task for the given agent if one exists."""
        task = cls._tasks.get(agent_id)
        if task and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(
                    "Error waiting for active RAG indexing task for agent %s: %s",
                    agent_id,
                    e,
                )

    @classmethod
    async def reindex_agent_sync(
        cls, agent_id: uuid.UUID, session: AsyncSession | None = None
    ):
        """Synchronously index all documents for an agent and wait for completion."""
        if session is not None:
            await cls._reindex_agent_with_session(agent_id, session)
        else:
            factory = get_session_factory()
            async with factory() as new_session:
                await cls._reindex_agent_with_session(agent_id, new_session)

    @classmethod
    async def _reindex_agent(cls, agent_id: uuid.UUID):
        try:
            logger.info("Starting background RAG indexing for agent: %s", agent_id)
            factory = get_session_factory()
            async with factory() as session:
                await cls._reindex_agent_with_session(agent_id, session)
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

    @classmethod
    async def _reindex_agent_with_session(
        cls, agent_id: uuid.UUID, session: AsyncSession
    ):
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
            try:
                embeddings_raw = await asyncio.wait_for(
                    asyncio.to_thread(embedder, texts), timeout=5.0
                )
            except TimeoutError:
                logger.warning(
                    "Embedding generation timed out after 5s. Using zero vector fallback."
                )
                dims = get_provider_config().mem0_embedder_dimensions
                embeddings = [[0.0] * dims for _ in range(len(all_chunks))]
            else:
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
            dims = get_provider_config().mem0_embedder_dimensions
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
    # 0. Wait for active in-flight indexing task if any
    await RAGIndexManager.wait_for_indexing(agent_id)

    # 1. Embed query
    try:
        embedder = get_embedder()
        try:
            query_embs = await asyncio.wait_for(
                asyncio.to_thread(embedder, [query]), timeout=5.0
            )
        except TimeoutError as e:
            err_msg = (
                f"RAG embedding generation timed out after 5.0s. Please check your "
                f"embedder model ('{get_provider_config().mem0_embedder_model}') and configuration."
            )
            logger.error("Query embedding timed out: %s", err_msg)
            raise RAGEmbeddingError(err_msg) from e
        query_emb_raw = query_embs[0]
        query_embedding = (
            query_emb_raw.tolist()
            if hasattr(query_emb_raw, "tolist")
            else list(query_emb_raw)
        )
    except RAGEmbeddingError:
        raise
    except Exception as e:
        active = get_provider_config()
        err_msg = (
            f"RAG embedding generation failed. Please check your embedder configuration "
            f"(provider: '{active.llm_provider_type}', model: '{active.mem0_embedder_model}', "
            f"base URL: '{active.llm_base_url}').\n"
            f"Details: {e}"
        )
        logger.error("Query embedding failed: %s", err_msg)
        raise RAGEmbeddingError(err_msg) from e

    # 2. Check if chunks exist or on-demand indexing is required
    stmt_check = (
        select(AgentDocumentChunk.id)
        .where(AgentDocumentChunk.agent_node_id == agent_id)
        .limit(1)
    )
    chunk_exists = (await session.execute(stmt_check)).scalar_one_or_none() is not None

    if not chunk_exists:
        stmt_docs = (
            select(AgentDocument.id)
            .where(AgentDocument.agent_node_id == agent_id)
            .limit(1)
        )
        doc_exists = (await session.execute(stmt_docs)).scalar_one_or_none() is not None
        if doc_exists:
            logger.info(
                "No chunks found but documents exist for agent %s. Indexing on-demand.",
                agent_id,
            )
            await RAGIndexManager._reindex_agent_with_session(agent_id, session)

    # 3. Retrieve top matching chunks
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
