"""
External Tools - Functions for fetching external data (news, etc).
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import os

import sys
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))


# ============================================================
# Response Models
# ============================================================

@dataclass
class NewsArticle:
    """A news article."""
    title: str
    source: str
    url: str
    snippet: str
    date: Optional[str] = None
    relevance: float = 0.0


@dataclass
class NewsResults:
    """Results from a news search."""
    query: str
    total_results: int
    articles: List[NewsArticle]


# ============================================================
# Tool Implementations
# ============================================================

def search_news(query: str, limit: int = 5) -> NewsResults:
    """
    Search for news articles related to a query.
    
    Uses Brave Search API if available, otherwise returns empty results.
    
    Args:
        query: Search query (e.g., "Arsenal injury news")
        limit: Maximum number of results
    
    Returns:
        NewsResults with relevant articles
    """
    # Try to use Brave Search API
    api_key = os.getenv("BRAVE_API_KEY")
    
    if not api_key:
        return NewsResults(
            query=query,
            total_results=0,
            articles=[],
        )
    
    try:
        import requests
        
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        }
        
        params = {
            "q": query,
            "count": limit,
            "freshness": "pw",  # Past week
        }
        
        response = requests.get(
            "https://api.search.brave.com/res/v1/news/search",
            headers=headers,
            params=params,
            timeout=10,
        )
        
        if response.status_code != 200:
            return NewsResults(query=query, total_results=0, articles=[])
        
        data = response.json()
        results = data.get("results", [])
        
        articles = []
        for r in results[:limit]:
            articles.append(NewsArticle(
                title=r.get("title", ""),
                source=r.get("meta_url", {}).get("hostname", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                date=r.get("age", ""),
            ))
        
        return NewsResults(
            query=query,
            total_results=len(articles),
            articles=articles,
        )
        
    except Exception as e:
        print(f"News search error: {e}")
        return NewsResults(query=query, total_results=0, articles=[])


def search_press_conference(team_name: str) -> NewsResults:
    """
    Search for recent press conference news for a team.
    
    Args:
        team_name: Team name
    
    Returns:
        NewsResults with press conference articles
    """
    query = f"{team_name} manager press conference"
    return search_news(query, limit=3)


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing External Tools")
    print("=" * 60)
    
    print("\n1. search_news('Arsenal injury news')")
    results = search_news("Arsenal injury news")
    print(f"   Found {results.total_results} results")
    for article in results.articles[:3]:
        print(f"   - {article.title[:60]}...")
    
    if results.total_results == 0:
        print("   ⚠️  No results - BRAVE_API_KEY may not be set")
    
    print("\n" + "=" * 60)
