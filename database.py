import os
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

Base = declarative_base()

NO_DB_MODE = os.getenv("NO_DB_MODE", "true").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL")

if not NO_DB_MODE and DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
    engine = None
    AsyncSessionLocal = None


async def get_db():
    if NO_DB_MODE or AsyncSessionLocal is None:
        yield None
        return
    async with AsyncSessionLocal() as session:
        yield session


def get_milvus():
    return MockMilvusClient()


class MockMilvusClient:
    """Simulates Milvus for the frontend without any disk files or segments"""
    def __init__(self):
        self.data = {}
        print("Backend running in NO-DATABASE mode")

    def has_collection(self, _name):
        return True

    def create_collection(self, **kwargs):
        pass

    def load_collection(self, _name):
        pass

    def flush(self, _name):
        pass

    def insert(self, collection_name, data):
        if collection_name not in self.data:
            self.data[collection_name] = []
        self.data[collection_name].extend(data)
        return {"ids": [d.get("id") for d in data]}

    def upsert(self, collection_name, data):
        return self.insert(collection_name, data)

    def query(self, collection_name, filter=None, limit=100, **kwargs):
        if collection_name not in self.data:
            return []
        return self.data[collection_name][:limit]

    def search(self, **kwargs):
        return []

    def delete(self, **kwargs):
        pass
