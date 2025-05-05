import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain.chains import create_extraction_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import requests

# STEP 1: Query SearXNG
def search_searxng(query: str, searxng_url: str = "http://localhost:8080", limit: int = 5) -> List[str]:
    """
    Search using local SearXNG instance and return top URLs
    
    Args:
        query: Search query
        searxng_url: URL of your SearXNG instance
        limit: Number of results to return
        
    Returns:
        List of URLs from search results
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {
        "q": query,
        "format": "json",
        "language": "en",
        "safesearch": 1,
        "pageno": 1
    }
    
    try:
        res = requests.get(f"{searxng_url}/search", params=params, headers=headers, timeout=10)
        res.raise_for_status()
        results = res.json().get("results", [])
        return [r["url"] for r in results[:limit] if "url" in r]
    except requests.exceptions.RequestException as e:
        print(f"Error searching with SearXNG: {e}")
        return []

# STEP 2: Load and clean page content
def fetch_documents(urls: List[str]) -> List[dict]:
    """
    Fetch and clean web page content
    
    Args:
        urls: List of URLs to fetch
        
    Returns:
        List of cleaned documents
    """
    if not urls:
        return []
    
    try:
        loader = AsyncChromiumLoader(urls)
        raw_docs = loader.load()
        transformer = BeautifulSoupTransformer()
        return transformer.transform_documents(raw_docs, tags_to_extract=["p", "article", "main"])
    except Exception as e:
        print(f"Error loading documents: {e}")
        return []

# STEP 3: Summarize with GPT-4o
def summarize_docs(docs: List[dict], query: str) -> str:
    """
    Generate a summary of the documents in relation to the original query
    
    Args:
        docs: List of documents to summarize
        query: Original search query
        
    Returns:
        Generated summary
    """
    if not docs:
        return "No content available to summarize."
    
    # Combine document content
    combined_content = "\n\n".join([doc.page_content for doc in docs])
    
    # Create a summary prompt
    prompt = ChatPromptTemplate.from_template("""
    You are a helpful research assistant. Analyze the following web content 
    in relation to the user's query and provide a concise summary with key insights.
    Focus on information most relevant to the query.
    
    User Query: {query}
    
    Web Content:
    {content}
    
    Summary:
    """)
    
    llm = ChatOpenAI(model="gpt-4.1-nano", temperature=0.8)
    chain = prompt | llm | StrOutputParser()
    
    try:
        return chain.invoke({"query": query, "content": combined_content})
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "Summary generation failed."

# Main function
def main():
    # Configure OpenAI API key - in production, use environment variables or secure storage
    os.environ["OPENAI_API_KEY"] = "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"  # Remove this from code in production!
    
    search_query = "best strategies for solving robin boundry problems"
    print(f"Searching for: {search_query}")
    
    # Get search results
    urls = search_searxng(search_query)
    print(f"\nFound {len(urls)} results:")
    for i, url in enumerate(urls, 1):
        print(f"{i}. {url}")
    
    # Fetch and clean documents
    docs = fetch_documents(urls)
    
    # Generate summary
    if docs:
        summary = summarize_docs(docs, search_query)
        print("\n🔍 Summary:")
        print(summary)
    else:
        print("\nNo documents available for summarization.")

if __name__ == "__main__":
    main()