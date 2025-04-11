import requests
import urllib.parse
import time
import random
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import re
import json

class SearchEngine:
    def __init__(self):
        self.base_url = "https://html.duckduckgo.com/html/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html',
            'Accept-Language': 'en-US',
            'Referer': 'https://duckduckgo.com/'
        }

    def search(self, query, num_results=10):
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?q={encoded_query}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return self._parse_results(response.text, num_results)
        except Exception as e:
            return {"error": f"Search failed: {str(e)}", "results": []}

    def _parse_results(self, html, num_results):
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        # Note: Update these selectors if DuckDuckGo changes its HTML structure
        for result in soup.select('.result')[:num_results]:
            title_elem = result.select_one('.result__title a')
            snippet_elem = result.select_one('.result__snippet')
            
            if title_elem and snippet_elem:
                url = self._extract_url(title_elem.get('href'))
                results.append({
                    'title': title_elem.text.strip(),
                    'snippet': snippet_elem.text.strip(),
                    'url': url
                })
                
        return {"results": results}

    def _extract_url(self, href):
        if href.startswith('/'):
            url_params = urllib.parse.parse_qs(href.split('?')[1])
            return url_params.get('uddg', [href])[0]
        else:
            return href

class URLCleaner:
    @staticmethod
    def clean(url):
        if url.startswith('https://duckduckgo.com/y.js?'):
            try:
                response = requests.head(url, allow_redirects=True, timeout=5)
                return response.url
            except:
                return url
        return url

class WebScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15',
            ]),
            'Accept': 'text/html',
            'Accept-Language': 'en-US'
        }

    def scrape(self, url):
        cleaned_url = URLCleaner.clean(url)
        try:
            response = requests.get(cleaned_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser', from_encoding=response.encoding)
            
            # Remove unwanted elements
            for elem in soup(["script", "style"]):
                elem.extract()
            
            title = soup.title.text.strip() if soup.title else "No title"
            content = self._extract_main_content(soup)
            
            return {
                "url": cleaned_url,
                "title": title,
                "content": content,
                "success": True
            }
        except requests.exceptions.RequestException as e:
            return {
                "url": cleaned_url,
                "title": "Failed to scrape",
                "content": [f"Request error: {str(e)}"],
                "success": False
            }
        except Exception as e:
            return {
                "url": cleaned_url,
                "title": "Failed to scrape",
                "content": [f"Unexpected error: {str(e)}"],
                "success": False
            }

    def _extract_main_content(self, soup):
        # Find all div elements
        divs = soup.find_all('div')
        
        # Calculate word count for each div
        div_text_lengths = []
        for div in divs:
            text = div.get_text().strip()
            word_count = len(text.split())
            if word_count > 50:  # Filter out small divs (e.g., menus)
                div_text_lengths.append((div, word_count))
        
        if div_text_lengths:
            # Select div with most words
            main_div = max(div_text_lengths, key=lambda x: x[1])[0]
        else:
            main_div = soup.body
        
        # Extract paragraphs from main_div
        paragraphs = []
        for p in main_div.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'li']):
            text = p.get_text().strip()
            if text:
                paragraphs.append(text)
        
        if not paragraphs:
            # Fallback: extract all text from body
            text = soup.get_text().strip()
            sentences = re.split(r'(?<=[.!?])\s+', text)
            paragraphs = [s for s in sentences if len(s) > 10]
        
        return paragraphs

class SearchOrchestrator:
    def __init__(self, searcher, scraper):
        self.searcher = searcher
        self.scraper = scraper

    def execute(self, query, num_results=8, max_paragraphs=50):
        search_data = self.searcher.search(query, num_results)
        
        if not search_data["results"]:
            return json.dumps({
                "query": query,
                "search_results": [],
                "scraped_data": [],
                "error": search_data.get("error", "No results found")
            })

        scraped_data = self._scrape_results(search_data["results"], max_paragraphs)
        
        return json.dumps({
            "query": query,
            "search_results": search_data["results"],
            "scraped_data": scraped_data
        }, ensure_ascii=False, indent=2)

    def _scrape_results(self, search_results, max_paragraphs):
        scraped_data = []
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {
                executor.submit(self.scraper.scrape, result['url']): result 
                for result in search_results
            }
            
            for future in future_to_url:
                try:
                    site_data = future.result()
                    if len(site_data['content']) > max_paragraphs:
                        site_data['content'] = site_data['content'][:max_paragraphs]
                    scraped_data.append(site_data)
                    time.sleep(random.uniform(1, 2))
                except Exception as e:
                    scraped_data.append({
                        "url": future_to_url[future]['url'],
                        "title": "Failed to scrape",
                        "content": [f"Error: {str(e)}"],
                        "success": False
                    })
                    
        return scraped_data

if __name__ == "__main__":
    import sys
    
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Enter your search query: ")
    
    searcher = SearchEngine()
    scraper = WebScraper()
    orchestrator = SearchOrchestrator(searcher, scraper)
    
    results_json = orchestrator.execute(query)
    print(results_json)