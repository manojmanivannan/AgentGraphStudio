import logging

import dspy

from canvas_server.config import settings

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
                final_chunks.append(chunk[i:i + max_chars])
        else:
            final_chunks.append(chunk)

    return final_chunks


async def run_rag_search(documents: list, query: str, chunk_size: int) -> str:
    """Embed documents and retrieve top k matching passages for query."""
    corpus = []
    for doc in documents:
        corpus.extend(chunk_text(doc.content, chunk_size))

    if not corpus:
        logger.info("RAG search: corpus is empty")
        return ""

    provider = settings.mem0_embedder_provider
    model_name = settings.mem0_embedder_model

    if provider and not model_name.startswith(f"{provider}/"):
        model_name = f"{provider}/{model_name}"

    logger.info("RAG search: using model=%s provider=%s k=%d", model_name, provider, min(5, len(corpus)))

    try:
        try:
            import litellm
            litellm.drop_params = True
        except ImportError:
            pass

        kwargs = {}
        if provider == "ollama":
            embedder = dspy.Embedder(
                model=model_name,
                api_base=settings.llm_base_url,
                dimensions=settings.mem0_embedder_dimensions,
                **kwargs
            )
        else:
            embedder = dspy.Embedder(
                model=model_name,
                api_key=settings.llm_api_key,
                api_base=settings.llm_base_url,
                dimensions=settings.mem0_embedder_dimensions,
                **kwargs
            )

        topk = min(5, len(corpus))
        # Embeddings retriever is synchronous in dspy
        search = dspy.retrievers.Embeddings(embedder=embedder, corpus=corpus, k=topk)
        results = search(query)
        passages = results.passages
        logger.debug("RAG search complete, retrieved %d passages", len(passages))
        return "\n\n---\n\n".join(passages)
    except Exception as e:
        logger.warning("RAG search failed: %s. Falling back to first few corpus chunks.", e)
        return "\n\n---\n\n".join(corpus[:5])
