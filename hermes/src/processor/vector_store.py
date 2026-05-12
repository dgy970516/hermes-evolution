class VectorStore:
    """Level 3 - 长期上下文向量存储"""

    def __init__(self, db_path: str = "./data/knowledge"):
        self.db_path = db_path
        self._collection = None

    async def initialize(self):
        # TODO: Initialize ChromaDB/Qdrant client
        pass

    async def add_document(self, text: str, metadata: dict):
        # TODO: Embed and store
        pass

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        # TODO: Hybrid search (vector + keyword)
        return []

    async def delete_old(self, days: int = 30):
        # TODO: Cleanup old entries
        pass
