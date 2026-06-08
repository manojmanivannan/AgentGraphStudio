# RAG Support for Worker Agents

## Status

Accepted

## Context

Users need the ability to supply worker agents with domain-specific knowledge via custom text documents. This is a standard Retrieval-Augmented Generation (RAG) pattern, where relevant parts of the uploaded documents are retrieved based on the user's query and injected into the agent's instructions before it executes.

Specifically, the system should allow users to:
1. Upload one or more text documents to a worker agent.
2. Configure a chunk size for splitting those documents.
3. Place a `{{ rag_document }}` placeholder anywhere inside the agent's prompt (role or instructions) which gets replaced by the RAG search results at run time.

Because the system execution is dynamic, and users frequently update canvas nodes, agents, and their attached documents, we need a RAG architecture that integrates cleanly with our canvas persistence model and execution engine.

## Considered Options

### 1. In-Memory DSPy Embeddings Retriever with Run-Time Substitution (Chosen Option)

Store document text directly in a relational table (`agent_documents`) connected to the agent node. At execution time:
- Read documents from the database.
- Split the text into paragraph-aligned chunks using the agent's configured `rag_chunk_size`.
- Dynamically build a `dspy.Embedder` using the configured embedding provider, model, and dimensions (reusing the existing mem0 config env vars).
- Build a temporary `dspy.retrievers.Embeddings` retriever with the chunked corpus.
- Retrieve the top 5 matching chunks for the user's prompt or task description.
- Substitute the retrieved passages into the `{{ rag_document }}` placeholder in the agent instructions/role and construct the agent.
- Implement a graceful fallback to return the first 5 corpus chunks if the embedder backend is unavailable.

* **Pros:**
  * Clean alignment with DSPy's core features.
  * No vector database synchronization overhead. Uploaded documents are simply standard text rows.
  * Easy to clean up: when an agent is deleted or updated, the text document is deleted or synced via standard relational cascading.
  * The template substitution is straightforward and predictable.
* **Cons:**
  * Documents are embedded on every run. However, since agent-scoped documents are typically small to medium in size (e.g., under 100KB), embedding time is negligible (usually under 500ms on local or cloud embedding models).

### 2. Persistent Vector Store Storage (e.g. pgvector or Qdrant collection)

Embed the uploaded documents immediately upon upload, and store their vectors permanently in pgvector or Qdrant. At execution time, query the vector database directly.

* **Pros:**
  * Faster execution since documents are pre-embedded.
* **Cons:**
  * High complexity in keeping vectors in sync. When users save the canvas, the frontend debounces a full save payload. If we delete and recreate agent nodes (or update them), we must manage vector deletes, additions, and updates.
  * Complex collection/index management per agent or per canvas.

### 3. DSPy Built-in ColBERT Retriever

Use DSPy's standard ColBERT server-based retrieval module.

* **Pros:**
  * Built-in support in DSPy.
* **Cons:**
  * Requires running a separate ColBERT indexing server, which increases the infrastructure footprint and runtime complexity significantly.

## Decision

**Option 1: In-Memory DSPy Embeddings Retriever with Run-Time Substitution.**

We implement a simple `agent_documents` relational schema to store document text. Chunks are computed using a paragraph-aligned splitter with a fallback string slicer if a single paragraph exceeds the chunk size. At execution, we embed the chunks in-memory and perform a search using the user's current query or task.

To support this design, we also modify the canvas persistence layer: instead of destroying and recreating all agent nodes on every canvas save, we implement a delta upsert (`CanvasRepo.save_nodes_and_edges`) to preserve agent IDs and avoid triggering CASCADE deletes on the related `agent_documents` table.

The prompt injection occurs in both:
- The main worker execution path (`_run_worker` in `execution.py`)
- The handoff execution path (`_make_handoff_tool` -> `transfer` in `runner.py`)

## Consequences

* **Database Changes:**
  * Added `enable_rag: BOOLEAN` and `rag_chunk_size: INTEGER` columns to `agent_nodes`.
  * Created `agent_documents` table (id, canvas_id, agent_node_id, name, content, created_at) with CASCADE constraints and database indexes.
* **Canvas Persistence:**
  * Refactored canvas save logic to perform node upserts rather than a destructive delete-and-recreate, preserving all attached agent documents.
* **Execution Flow:**
  * Added `rag_helper.py` containing `chunk_text` and `run_rag_search` functions.
  * Dynamic agent assembly: RAG-enabled agents are rebuilt during the run/transfer step if RAG is enabled, replacing the placeholder and updating the agent instance in the runner's dictionary.
* **Configuration Requirements:**
  * RAG uses the same embedder variables as memory: `MEM0_EMBEDDER_PROVIDER`, `MEM0_EMBEDDER_MODEL`, and `MEM0_EMBEDDER_DIMENSIONS`.
* **Robustness & Fallbacks:**
  * If the embedding server is offline or fails, RAG falls back gracefully to selecting the first few document chunks rather than failing the workflow execution, logging warnings to aid troubleshooting.
