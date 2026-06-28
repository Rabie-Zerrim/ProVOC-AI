from pymilvus import MilvusClient, DataType
from sentence_transformers import SentenceTransformer
import logging
import config

logger = logging.getLogger(__name__)

COLLECTION_NAME = "taste_vectors"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension


class TasteEngine:
    _instance = None

    def __init__(self):
        self._client: MilvusClient | None = None
        self._encoder: SentenceTransformer | None = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "TasteEngine":
        if cls._instance is None:
            cls._instance = TasteEngine()
        return cls._instance

    def _init(self) -> None:
        if self._initialized:
            return
        try:
            uri = config.MILVUS_URI
            token = None
            if "?token=" in uri:
                uri, token = uri.split("?token=", 1)
            self._client = MilvusClient(uri=uri, token=token)
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self._ensure_collection()
            self._initialized = True
            logger.info("TasteEngine initialized")
        except Exception as e:
            logger.warning(f"TasteEngine init failed: {e}")

    def _ensure_collection(self) -> None:
        if COLLECTION_NAME not in self._client.list_collections():
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                dimension=EMBEDDING_DIM,
                metric_type="COSINE",
                auto_id=True,
            )
            logger.info(f"Created collection: {COLLECTION_NAME}")

    def store_review(
        self,
        user_id: str,
        business_id: str,
        business_name: str,
        review_text: str,
        rating: float,
        business_type: str = "",
    ) -> bool:
        self._init()
        if not self._initialized:
            return False
        try:
            text = f"{business_name} {business_type} {review_text}"
            vector = self._encoder.encode(text).tolist()
            self._client.insert(
                collection_name=COLLECTION_NAME,
                data=[{
                    "vector": vector,
                    "user_id": user_id,
                    "business_id": business_id,
                    "business_name": business_name,
                    "rating": rating,
                    "review_text": review_text[:200],
                }],
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to store review vector: {e}")
            return False

    def get_recommendations(
        self,
        user_id: str,
        limit: int = 5,
    ) -> list[dict]:
        self._init()
        if not self._initialized:
            return []
        try:
            import numpy as np

            # Step 1: Get current user's reviewed businesses
            user_reviews = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=f'user_id == "{user_id}"',
                output_fields=["vector", "business_id", "business_name", "rating"],
                limit=20,
            )
            if not user_reviews:
                return []

            reviewed_ids = {r["business_id"] for r in user_reviews}

            # Step 2: Build user taste vector
            vectors = [r["vector"] for r in user_reviews]
            taste_vector = np.mean(vectors, axis=0).tolist()

            # Step 3: Find all other businesses in Milvus
            # that were NOT reviewed by this user
            all_businesses = self._client.query(
                collection_name=COLLECTION_NAME,
                filter=f'user_id != "{user_id}"',
                output_fields=["business_id", "business_name", "rating", "vector", "user_id"],
                limit=100,
            )

            if not all_businesses:
                return []

            # Step 4: Deduplicate by business_id
            seen = {}
            for b in all_businesses:
                bid = b["business_id"]
                if bid not in reviewed_ids and bid not in seen:
                    seen[bid] = b

            if not seen:
                return []

            # Step 5: Score each unseen business by cosine similarity to user taste vector
            taste = np.array(taste_vector)
            scored = []
            for bid, b in seen.items():
                bvec = np.array(b["vector"])
                sim = float(np.dot(taste, bvec) / (
                    np.linalg.norm(taste) * np.linalg.norm(bvec) + 1e-9
                ))
                scored.append({
                    "business_name": b["business_name"],
                    "business_id": bid,
                    "score": round(sim, 3),
                })

            # Step 6: Sort by similarity and return top N
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:limit]

        except Exception as e:
            logger.warning(f"Failed to get recommendations: {e}")
            return []