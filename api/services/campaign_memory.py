"""
Campaign Memory Service - RAG for Learning from Past Campaigns

This service stores successful campaigns in a vector database and retrieves
similar ones to improve future idea generation.
"""

import logging
from datetime import datetime
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CampaignMemory:
    """
    Stores and retrieves campaign ideas using vector embeddings (FAISS).

    Use cases:
    - Find similar past campaigns when generating new ideas
    - Learn from high-scoring campaigns
    - Avoid repeating failed approaches
    """

    def __init__(self):
        """Initialize FAISS vector store."""
        self.embeddings = OpenAIEmbeddings(
            api_key=settings.openai_api_key
        )

        # Store in data directory
        self.persist_directory = Path("./data/campaign_memory")
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.index_path = self.persist_directory / "faiss_index"

        # Load existing index or create new
        if self.index_path.exists():
            self.vectorstore = FAISS.load_local(
                str(self.index_path),
                self.embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info(f"Loaded existing campaign memory from: {self.index_path}")
        else:
            # Initialize empty FAISS index
            self.vectorstore = None
            logger.info(f"Campaign memory initialized (empty): {self.persist_directory}")

    async def store_campaign(
        self,
        project_id: str,
        idea_id: str,
        title: str,
        concept: str,
        rationale: str,
        execution: list[str],
        score: float,
        client: str = "",
        country: str = "",
        industry: str = ""
    ):
        """
        Store a campaign idea in vector memory.

        Args:
            project_id: Campaign project ID
            idea_id: Unique idea identifier
            title: Campaign title
            concept: Campaign concept description
            rationale: Why this campaign works
            execution: List of tactical steps
            score: Overall quality score (0-10)
            client: Client name
            country: Target country
            industry: Industry vertical
        """
        try:
            # Combine all text for embedding
            full_text = f"""
Title: {title}

Concept: {concept}

Rationale: {rationale}

Execution Plan:
{chr(10).join(f"{i+1}. {tactic}" for i, tactic in enumerate(execution))}
"""

            # Create document with metadata
            doc = Document(
                page_content=full_text,
                metadata={
                    "project_id": project_id,
                    "idea_id": idea_id,
                    "title": title,
                    "score": score,
                    "client": client,
                    "country": country,
                    "industry": industry,
                    "stored_at": datetime.now().isoformat()
                }
            )

            # Add to vector store (create if first document)
            if self.vectorstore is None:
                self.vectorstore = FAISS.from_documents([doc], self.embeddings)
            else:
                self.vectorstore.add_documents([doc])

            # Save index
            self.vectorstore.save_local(str(self.index_path))

            logger.info(f"Stored campaign: {title} (score: {score}/10)")

        except Exception as e:
            logger.error(f"Error storing campaign: {e}", exc_info=True)

    async def find_similar_campaigns(
        self,
        query: str,
        k: int = 5,
        min_score: float = 7.0,
        country: str | None = None,
        industry: str | None = None
    ) -> list[dict]:
        """
        Find similar successful campaigns.

        Args:
            query: Search query (brief, concept, keywords)
            k: Number of results to return
            min_score: Minimum quality score filter
            country: Filter by country
            industry: Filter by industry

        Returns:
            List of similar campaigns with metadata
        """
        try:
            # Check if vectorstore exists
            if self.vectorstore is None:
                logger.info("No campaigns stored yet")
                return []

            # Search vector store (FAISS doesn't support metadata filtering directly)
            # So we get more results and filter in Python
            results = self.vectorstore.similarity_search(
                query=query,
                k=k * 3  # Get more results to filter
            )

            # Manual filtering by metadata
            filtered_results = []
            for doc in results:
                # Check score
                doc_score = doc.metadata.get("score", 0)
                if doc_score < min_score:
                    continue

                # Check country
                if country and doc.metadata.get("country", "") != country:
                    continue

                # Check industry
                if industry and doc.metadata.get("industry", "") != industry:
                    continue

                filtered_results.append(doc)

                # Stop when we have enough
                if len(filtered_results) >= k:
                    break

            results = filtered_results

            # Format results
            campaigns = []
            for doc in results:
                campaigns.append({
                    "content": doc.page_content,
                    "title": doc.metadata.get("title", ""),
                    "score": doc.metadata.get("score", 0),
                    "client": doc.metadata.get("client", ""),
                    "country": doc.metadata.get("country", ""),
                    "project_id": doc.metadata.get("project_id", "")
                })

            logger.info(f"Found {len(campaigns)} similar campaigns for: {query[:50]}...")
            return campaigns

        except Exception as e:
            logger.error(f"Error finding similar campaigns: {e}", exc_info=True)
            return []

    async def get_best_campaigns(
        self,
        limit: int = 10,
        country: str | None = None,
        industry: str | None = None
    ) -> list[dict]:
        """
        Get highest-scoring campaigns.

        Args:
            limit: Number of campaigns to return
            country: Filter by country
            industry: Filter by industry

        Returns:
            List of top campaigns
        """
        try:
            # This would require a custom retrieval method in Chroma
            # For now, search with a generic query and filter by score
            results = self.vectorstore.similarity_search(
                query="successful creative campaign",
                k=limit * 2,  # Get more, then filter
                filter={
                    "score": {"$gte": 8.0},
                    **({"country": country} if country else {}),
                    **({"industry": industry} if industry else {})
                }
            )

            # Sort by score
            sorted_results = sorted(
                results,
                key=lambda x: x.metadata.get("score", 0),
                reverse=True
            )[:limit]

            campaigns = []
            for doc in sorted_results:
                campaigns.append({
                    "content": doc.page_content,
                    "title": doc.metadata.get("title", ""),
                    "score": doc.metadata.get("score", 0),
                    "client": doc.metadata.get("client", ""),
                    "country": doc.metadata.get("country", "")
                })

            logger.info(f"Retrieved {len(campaigns)} top campaigns")
            return campaigns

        except Exception as e:
            logger.error(f"Error getting best campaigns: {e}", exc_info=True)
            return []

    def get_stats(self) -> dict:
        """Get statistics about stored campaigns."""
        try:
            if self.vectorstore is None:
                return {"total_campaigns": 0, "persist_directory": str(self.persist_directory)}

            # FAISS stores count in index.ntotal
            count = self.vectorstore.index.ntotal if hasattr(self.vectorstore, 'index') else 0

            return {
                "total_campaigns": count,
                "persist_directory": str(self.persist_directory)
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"total_campaigns": 0}


# Singleton instance
_campaign_memory = None


def get_campaign_memory() -> CampaignMemory:
    """Get singleton campaign memory instance."""
    global _campaign_memory
    if _campaign_memory is None:
        _campaign_memory = CampaignMemory()
    return _campaign_memory
