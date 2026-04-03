# db/es_client.py — Elasticsearch client and index management
# Java equivalent: @Repository ElasticsearchRepository
#
# Index structure (one index per app, scoped by username field):
#   deepsearch
#     ├── text        (keyword + full-text)
#     ├── filename    (keyword)
#     ├── username    (keyword)   ← used to scope search per user
#     ├── chunk_index (integer)
#     └── embedding   (dense_vector, 1024 dims) ← for KNN/vector search

import logging

from elasticsearch import AsyncElasticsearch

from core.config import settings

logger = logging.getLogger(__name__)

# Singleton async ES client
es = AsyncElasticsearch(hosts=[settings.ES_HOST])

# Index mapping — defines field types (like a DB schema)
INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "text":        {"type": "text"},        # full-text search (BM25)
            "filename":    {"type": "keyword"},     # exact match filter
            "username":    {"type": "keyword"},     # exact match filter
            "chunk_index": {"type": "integer"},
            "embedding": {
                "type":       "dense_vector",
                "dims":       1024,                 # must match EMBEDDING_MODEL output
                "index":      True,
                "similarity": "cosine",             # cosine similarity for KNN search
            },
        }
    }
}


async def ensure_index_exists():
    """
    Create the ES index with the correct mapping if it doesn't exist yet.
    Called once on app startup — safe to call multiple times (idempotent).
    Java equivalent: @EnableElasticsearchRepositories auto-creating index
    """
    exists = await es.indices.exists(index=settings.ES_INDEX)
    if not exists:
        await es.indices.create(index=settings.ES_INDEX, body=INDEX_MAPPING)
        logger.info(f"Created ES index: {settings.ES_INDEX}")
    else:
        logger.info(f"ES index already exists: {settings.ES_INDEX}")
