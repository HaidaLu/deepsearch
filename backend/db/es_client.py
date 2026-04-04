# db/es_client.py — Elasticsearch client and index management
import logging

from elasticsearch import AsyncElasticsearch

from core.config import settings

logger = logging.getLogger(__name__)

es = AsyncElasticsearch(hosts=[settings.ES_HOST])

# Index mapping: text (BM25) + embedding (KNN vector search)
INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "text":        {"type": "text"},
            "filename":    {"type": "keyword"},
            "username":    {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "embedding": {
                "type":       "dense_vector",
                "dims":       1024,
                "index":      True,
                "similarity": "cosine",
            },
        }
    }
}


async def ensure_index_exists() -> None:
    """Create the ES index with the correct mapping if it doesn't exist yet."""
    exists = await es.indices.exists(index=settings.ES_INDEX)
    if not exists:
        await es.indices.create(index=settings.ES_INDEX, body=INDEX_MAPPING)
        logger.info("ES index created: %s", settings.ES_INDEX)
    else:
        logger.info("ES index already exists: %s", settings.ES_INDEX)
