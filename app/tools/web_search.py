import os, requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed

def _tavily_search(q: str, top_k: int = 5):
    key = os.getenv("TAVILY_API_KEY")
    r = requests.post("https://api.tavily.com/search",
                      json={"api_key": key, "query": q, "max_results": top_k},
                      timeout=5)
    r.raise_for_status()
    data = r.json()
    out = []
    for item in data.get("results", [])[:top_k]:
        out.append({"title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": (item.get("content", "") or "")[:300]})
    return out

@retry(stop=stop_after_attempt(1), wait=wait_fixed(0))
def _ddg_search(q: str, top_k: int = 5):
    url = "https://duckduckgo.com/html"
    r = requests.get(url, params={"q": q},
                     timeout=5,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for res in soup.select(".result")[:top_k]:
        a = res.select_one(".result__a")
        if not a: continue
        title = a.get_text(strip=True)
        href = a.get("href")
        snippet_el = res.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        out.append({"title": title, "url": href, "snippet": snippet[:300]})
    return out

def search(query: str, top_k: int = 5):
    if os.getenv("TAVILY_API_KEY"):
        try: 
            return _tavily_search(query, top_k)
        except Exception: 
            pass
    return _ddg_search(query, top_k)
