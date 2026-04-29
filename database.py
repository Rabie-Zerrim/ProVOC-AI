import os

# NO DATABASE MODE - EVERYTHING IN MEMORY OR MOCKED
# To avoid all conflicts and ModuleNotFoundErrors

def get_milvus():
    return MockMilvusClient()

def get_db():
    # Return dummy session
    yield None

class MockMilvusClient:
    """Simulates Milvus for the frontend without any disk files or segments"""
    def __init__(self):
        self.data = {}
        print("🚀 Backend running in NO-DATABASE mode")
    
    def has_collection(self, name): return True
    def create_collection(self, **kwargs): pass
    def load_collection(self, name): pass
    def flush(self, name): pass
    
    def insert(self, collection_name, data):
        if collection_name not in self.data: self.data[collection_name] = []
        self.data[collection_name].extend(data)
        return {"ids": [d.get("id") for d in data]}
        
    def upsert(self, collection_name, data):
        return self.insert(collection_name, data)
        
    def query(self, collection_name, filter="", limit=10, **kwargs):
        if collection_name not in self.data: return []
        return self.data[collection_name][:limit]

    def search(self, **kwargs):
        return []

    def delete(self, **kwargs):
        pass
