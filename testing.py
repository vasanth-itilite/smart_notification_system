import asyncio
import argparse
import json
import re
import sys
import os
import urllib.parse
import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Set

import aiohttp
from bs4 import BeautifulSoup

# Modified imports - replacing crawl4ai with Playwright directly
from playwright.async_api import async_playwright

# Define enums to replace crawl4ai enums
from enum import Enum, auto

class CacheMode(Enum):
    BYPASS = auto()
    READ_ONLY = auto()
    READ_WRITE = auto()

# Simple config classes to replace crawl4ai configs
class BrowserConfig:
    def __init__(self, browser_type="chromium", headless=True, ignore_https_errors=True, 
                 verbose=False, extra_args=None):
        self.browser_type = browser_type
        self.headless = headless
        self.ignore_https_errors = ignore_https_errors
        self.verbose = verbose
        self.extra_args = extra_args or []

class CrawlerRunConfig:
    def __init__(self, cache_mode=CacheMode.BYPASS, verbose=False, page_timeout=30000):
        self.cache_mode = cache_mode
        self.verbose = verbose
        self.page_timeout = page_timeout


# Custom AsyncWebCrawler implementation to replace crawl4ai
class AsyncWebCrawler:
    def __init__(self, config=None):
        self.config = config or BrowserConfig()
        self.playwright = None
        self.browser = None
        
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        browser_type = getattr(self.playwright, self.config.browser_type)
        self.browser = await browser_type.launch(
            headless=self.config.headless,
            args=self.config.extra_args,
            ignore_https_errors=self.config.ignore_https_errors
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def arun(self, url, config=None):
        config = config or CrawlerRunConfig()
        result = type('Result', (), {})
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, timeout=config.page_timeout, wait_until="networkidle")
            
            # Extract metadata
            title = await page.title()
            content = await page.content()
            
            # Extract text content
            text_content = await page.evaluate('() => document.body.innerText')
            
            # Create a simple result object
            result.html = content
            result.plain_text = text_content
            
            # Convert HTML to markdown (simplified)
            result.markdown = self._html_to_markdown(content, title)
            
            # Add metadata
            result.metadata = {
                "title": title,
                "description": await self._get_meta_description(page),
                "language": await self._get_language(page),
                "author": await self._get_author(page),
            }
            
            return result
        finally:
            await context.close()
    
    async def _get_meta_description(self, page):
        desc = await page.evaluate('''
            () => {
                const meta = document.querySelector('meta[name="description"]') || 
                            document.querySelector('meta[property="og:description"]');
                return meta ? meta.getAttribute('content') : '';
            }
        ''')
        return desc
    
    async def _get_language(self, page):
        lang = await page.evaluate('''
            () => {
                return document.documentElement.lang || '';
            }
        ''')
        return lang
    
    async def _get_author(self, page):
        author = await page.evaluate('''
            () => {
                const meta = document.querySelector('meta[name="author"]');
                return meta ? meta.getAttribute('content') : '';
            }
        ''')
        return author
    
    def _html_to_markdown(self, html, title):
        """Very simple HTML to Markdown conversion"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Start with title
        markdown = f"# {title}\n\n"
        
        # Extract paragraphs
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                markdown += f"{text}\n\n"
        
        # Extract headings
        for i in range(1, 7):
            for h in soup.find_all(f'h{i}'):
                text = h.get_text(strip=True)
                if text:
                    markdown += f"{'#' * i} {text}\n\n"
        
        # Extract lists
        for ul in soup.find_all('ul'):
            for li in ul.find_all('li'):
                text = li.get_text(strip=True)
                if text:
                    markdown += f"* {text}\n"
            markdown += "\n"
        
        return markdown


class DuckDuckGoSearch:
    """A class to handle searching with DuckDuckGo."""
    
    def __init__(self):
        """Initialize the DuckDuckGo search client."""
        self.search_url = "https://html.duckduckgo.com/html/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html',
            'Accept-Language': 'en-US',
            'Referer': 'https://duckduckgo.com/'
        }
    
    async def search(self, query: str, num_results: int = 10) -> List[Dict[str, str]]:
        """Search DuckDuckGo for the given query.
        
        Args:
            query: The search query
            num_results: Maximum number of results to return
            
        Returns:
            List of search results with title, snippet, and URL
        """
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.search_url}?q={encoded_query}"
        
        print(f"Searching DuckDuckGo for: \"{query}\"")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=15) as response:
                    response.raise_for_status()
                    html = await response.text()
                    results = self._parse_results(html, num_results)
                    print(f"Found {len(results)} results")
                    return results
            except Exception as e:
                print(f"DuckDuckGo search failed: {str(e)}")
                return []
    
    def _parse_results(self, html: str, num_results: int) -> List[Dict[str, str]]:
        """Parse search results from DuckDuckGo HTML.
        
        Args:
            html: The HTML content of the search results page
            num_results: Maximum number of results to return
            
        Returns:
            List of search results with title, snippet, and URL
        """
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
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
        
        return results
    
    def _extract_url(self, href: str) -> str:
        """Extract actual URL from DuckDuckGo redirect URL.
        
        Args:
            href: The href attribute from the search result
            
        Returns:
            The extracted URL
        """
        if href.startswith('/'):
            try:
                url_params = urllib.parse.parse_qs(href.split('?')[1])
                return url_params.get('uddg', [href])[0]
            except (IndexError, KeyError):
                return href
        else:
            return href


class DeepWebScraper:
    """An enhanced web scraper class that performs deep crawling and data extraction."""
    
    def __init__(self, 
                 timeout: int = 30,
                 browser_type: str = "chromium",
                 headless: bool = True,
                 max_depth: int = 2,
                 max_pages_per_domain: int = 5):
        """Initialize the web scraper with configurable options.
        
        Args:
            timeout: Maximum time in seconds to wait for a page to load
            browser_type: Browser to use for scraping ("chromium", "firefox", or "webkit")
            headless: Whether to run the browser in headless mode
            max_depth: Maximum depth to crawl from initial URL
            max_pages_per_domain: Maximum number of pages to crawl per domain
        """
        self.timeout = timeout
        self.max_depth = max_depth
        self.max_pages_per_domain = max_pages_per_domain
        self.browser_config = BrowserConfig(
            browser_type=browser_type,
            headless=headless,
            ignore_https_errors=True,
            verbose=False,
            extra_args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        
    def normalize_url(self, url: str) -> Tuple[bool, str]:
        """Validate and normalize a URL.
        
        Args:
            url: The URL to validate and normalize
            
        Returns:
            A tuple of (is_valid, normalized_url)
        """
        # URL validation pattern - supports domains, subdomains with optional http(s)
        url_pattern = re.compile(
            r"^(?:https?://)?(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?:/[^/\s]*)*$"
        )
        
        if not url_pattern.match(url):
            return False, url
            
        # Add https:// if missing
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
            
        return True, url
    
    def get_domain(self, url: str) -> str:
        """Extract the domain from a URL."""
        parsed_url = urllib.parse.urlparse(url)
        return parsed_url.netloc
    
    def is_same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs belong to the same domain."""
        return self.get_domain(url1) == self.get_domain(url2)
    
    def normalize_internal_url(self, base_url: str, href: str) -> Optional[str]:
        """Convert relative URLs to absolute and filter out unwanted URL types."""
        try:
            # Skip URLs that are anchors, javascript, or mailto links
            if not href or href.startswith('#') or href.startswith('javascript:') or \
               href.startswith('mailto:') or href.startswith('tel:'):
                return None
                
            # Create absolute URL if href is relative
            absolute_url = urllib.parse.urljoin(base_url, href)
            
            # Skip non-http/https URLs
            if not absolute_url.startswith('http'):
                return None
                
            # Skip URLs with common file extensions to avoid downloading files
            file_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                              '.zip', '.rar', '.tar', '.gz', '.jpg', '.jpeg', '.png', '.gif', 
                              '.mp3', '.mp4', '.avi', '.mov']
            if any(absolute_url.lower().endswith(ext) for ext in file_extensions):
                return None
                
            return absolute_url
        except Exception:
            return None
    
    async def extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all valid links from HTML content."""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for anchor in soup.find_all('a', href=True):
            normalized_url = self.normalize_internal_url(base_url, anchor['href'])
            if normalized_url and self.is_same_domain(base_url, normalized_url):
                links.append(normalized_url)
                
        return list(set(links))  # Remove duplicates
    
    async def extract_structured_data(self, html: str) -> Dict[str, Any]:
        """Extract structured data like JSON-LD, microdata, and metadata from HTML."""
        structured_data = {
            "json_ld": [],
            "meta_tags": {},
            "open_graph": {},
            "twitter_cards": {},
        }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                json_data = json.loads(script.string)
                structured_data["json_ld"].append(json_data)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Extract meta tags
        for meta in soup.find_all('meta'):
            if meta.get('name') and meta.get('content'):
                structured_data["meta_tags"][meta['name']] = meta['content']
            elif meta.get('property') and meta.get('content'):
                if meta['property'].startswith('og:'):
                    # OpenGraph tags
                    structured_data["open_graph"][meta['property'][3:]] = meta['content']
                elif meta['property'].startswith('twitter:'):
                    # Twitter card tags
                    structured_data["twitter_cards"][meta['property'][8:]] = meta['content']
        
        return structured_data
    
    async def extract_tables(self, html: str) -> List[Dict[str, Any]]:
        """Extract tables from HTML content."""
        soup = BeautifulSoup(html, 'html.parser')
        tables = []
        
        for table_idx, table in enumerate(soup.find_all('table')):
            table_data = {"id": table_idx, "caption": "", "headers": [], "rows": []}
            
            # Extract caption if present
            caption = table.find('caption')
            if caption:
                table_data["caption"] = caption.get_text(strip=True)
            
            # Extract headers
            headers = []
            header_row = table.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    headers.append(th.get_text(strip=True))
                table_data["headers"] = headers
            
            # Extract rows
            for row in table.find_all('tr')[1:] if headers else table.find_all('tr'):
                row_data = []
                for cell in row.find_all(['td', 'th']):
                    row_data.append(cell.get_text(strip=True))
                table_data["rows"].append(row_data)
            
            tables.append(table_data)
        
        return tables
    
    async def scrape_url(self, 
                         url: str, 
                         extract_metadata: bool = True,
                         extract_structured: bool = True,
                         extract_tables: bool = True) -> Dict[str, Any]:
        """Scrape a webpage using Playwright with enhanced extraction.
        
        Args:
            url: The URL to scrape
            extract_metadata: Whether to extract metadata from the page
            extract_structured: Whether to extract structured data
            extract_tables: Whether to extract tables
            
        Returns:
            Dictionary with the scraping results
        """
        is_valid, normalized_url = self.normalize_url(url)
        
        if not is_valid:
            print(f"Invalid URL: {url}")
            return {
                "success": False,
                "url": url,
                "error": "Invalid URL format"
            }
        
        print(f"Scraping: {normalized_url}")
        
        try:
            # Configure settings
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                verbose=False,
                page_timeout=self.timeout * 1000,  # Convert to milliseconds
            )
            
            # Use AsyncWebCrawler for the actual scraping
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                result = await asyncio.wait_for(
                    crawler.arun(
                        url=normalized_url,
                        config=run_config,
                    ),
                    timeout=self.timeout,
                )
                
                # Extract content from the result
                response_data = {
                    "success": True,
                    "url": normalized_url,
                    "title": "",  # Will be populated later
                    "markdown": getattr(result, "markdown", ""),
                    "plain_text": getattr(result, "plain_text", ""),
                    "html": getattr(result, "html", "")[:20000] if hasattr(result, "html") else "",  # Limit HTML size
                }
                
                # Extract links for deep crawling
                response_data["links"] = await self.extract_links(response_data["html"], normalized_url)
                
                # Add metadata if requested and available
                if extract_metadata and hasattr(result, "metadata") and result.metadata:
                    # Handle both object and dictionary metadata formats
                    if isinstance(result.metadata, dict):
                        response_data["title"] = result.metadata.get("title", "")
                        response_data["metadata"] = {
                            "title": result.metadata.get("title", ""),
                            "description": result.metadata.get("description", ""),
                            "language": result.metadata.get("language", ""),
                            "author": result.metadata.get("author", ""),
                        }
                    else:
                        response_data["title"] = getattr(result.metadata, "title", "")
                        response_data["metadata"] = {
                            "title": getattr(result.metadata, "title", ""),
                            "description": getattr(result.metadata, "description", ""),
                            "language": getattr(result.metadata, "language", ""),
                            "author": getattr(result.metadata, "author", ""),
                        }
                
                # Extract structured data if requested
                if extract_structured and response_data["html"]:
                    response_data["structured_data"] = await self.extract_structured_data(response_data["html"])
                
                # Extract tables if requested
                if extract_tables and response_data["html"]:
                    response_data["tables"] = await self.extract_tables(response_data["html"])
                
                print(f"Successfully scraped: {normalized_url}")
                return response_data
                
        except asyncio.TimeoutError:
            print(f"Timeout while scraping: {normalized_url}")
            return {
                "success": False,
                "url": normalized_url,
                "error": f"Operation timed out after {self.timeout} seconds"
            }
        except Exception as e:
            print(f"Error scraping {normalized_url}: {str(e)}")
            return {
                "success": False, 
                "url": normalized_url,
                "error": str(e)
            }
    
    async def deep_crawl(self, start_url: str) -> Dict[str, Any]:
        """Perform deep crawling starting from the given URL.
        
        Args:
            start_url: The URL to start crawling from
            
        Returns:
            Dictionary with the crawling results
        """
        is_valid, normalized_url = self.normalize_url(start_url)
        
        if not is_valid:
            return {
                "success": False,
                "url": start_url,
                "error": "Invalid URL format"
            }
        
        domain = self.get_domain(normalized_url)
        print(f"Starting deep crawl on domain: {domain}")
        
        # Track visited URLs and pages to crawl
        visited_urls = set()
        urls_to_crawl = [(normalized_url, 0)]  # (url, depth)
        domain_page_count = 0
        
        all_results = {
            "success": True,
            "start_url": normalized_url,
            "domain": domain,
            "pages": []
        }
        
        while urls_to_crawl and domain_page_count < self.max_pages_per_domain:
            current_url, depth = urls_to_crawl.pop(0)
            
            if current_url in visited_urls:
                continue
                
            visited_urls.add(current_url)
            
            # Scrape the current URL
            print(f"Crawling [{depth}/{self.max_depth}]: {current_url}")
            result = await self.scrape_url(current_url)
            
            if result["success"]:
                domain_page_count += 1
                all_results["pages"].append(result)
                
                # If we haven't reached max depth, add links to queue
                if depth < self.max_depth:
                    links = result.get("links", [])
                    for link in links:
                        if link not in visited_urls and self.get_domain(link) == domain:
                            urls_to_crawl.append((link, depth + 1))
            
            # Simple progress report
            print(f"Progress: {domain_page_count}/{self.max_pages_per_domain} pages crawled")
            
        print(f"Deep crawl completed: {domain_page_count} pages crawled on domain {domain}")
        return all_results


class DeepScraperService:
    """Service class to handle web searching and deep scraping operations."""
    
    def __init__(self, max_depth: int = 2, max_pages_per_domain: int = 5):
        self.scraper = DeepWebScraper(max_depth=max_depth, max_pages_per_domain=max_pages_per_domain)
        self.search_engine = DuckDuckGoSearch()
    
    async def search_and_deep_scrape(self, 
                                    query: str, 
                                    num_results: int = 3,
                                    perform_deep_crawl: bool = True) -> Dict[str, Any]:
        """Search for a query and perform deep scraping on the resulting URLs.
        
        Args:
            query: The search query
            num_results: Maximum number of search results to deep scrape
            perform_deep_crawl: Whether to perform deep crawling on each result
            
        Returns:
            Dictionary with search results and deeply scraped content
        """
        # First, search for the query
        search_results = await self.search_engine.search(query, num_results)
        
        if not search_results:
            return {
                "query": query,
                "success": False,
                "error": "No search results found",
                "search_results": [],
                "scraped_content": []
            }
        
        # Extract URLs from search results
        urls = [result["url"] for result in search_results]
        
        # Deep scrape each URL
        print(f"Deep scraping {len(urls)} domains...")
        
        if perform_deep_crawl:
            # For deep crawling, process each domain
            scrape_tasks = [self.scraper.deep_crawl(url) for url in urls]
        else:
            # For simple scraping, just get the main page
            scrape_tasks = [self.scraper.scrape_url(url, extract_structured=True, extract_tables=True) for url in urls]
            
        scraped_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        
        # Process results, handling any exceptions
        processed_results = []
        for i, result in enumerate(scraped_results):
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "url": urls[i],
                    "error": str(result)
                })
            else:
                processed_results.append(result)
        
        # Count successful scrapes
        successful = sum(1 for result in processed_results if result.get("success", False))
        print(f"Successfully deep scraped {successful} out of {len(urls)} domains")
        
        timestamp = datetime.datetime.now().isoformat()
        
        return {
            "query": query,
            "success": True,
            "timestamp": timestamp,
            "deep_crawl_enabled": perform_deep_crawl,
            "search_results": search_results,
            "scraped_content": processed_results
        }

    async def analyze_deep_scrape_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze deep scrape results to extract key insights.
        
        Args:
            results: The results from search_and_deep_scrape
            
        Returns:
            Dictionary with analysis of deep scrape results
        """
        analysis = {
            "summary": {
                "total_domains": len(results["scraped_content"]),
                "successful_domains": sum(1 for r in results["scraped_content"] if r.get("success", False)),
                "total_pages": 0,
                "tables_found": 0,
                "structured_data_found": 0,
            },
            "domain_insights": [],
            "common_entities": {},
            "content_summary": "",
        }
        
        # Analyze each domain
        all_text = []
        for domain_result in results["scraped_content"]:
            if not domain_result.get("success", False):
                continue
            domain = domain_result.get("domain", None)
            if domain is None and "url" in domain_result:
                domain = self.scraper.get_domain(domain_result["url"])
            elif domain is None:
                # Fallback if both domain and url are missing
                domain = "unknown_domain"
                
            domain_pages = domain_result.get("pages", [domain_result])
            analysis["summary"]["total_pages"] += len(domain_pages)
            
            domain_insight = {
                "domain": domain,
                "pages_crawled": len(domain_pages),
                "tables_found": 0,
                "has_structured_data": False,
            }
            
            # Collect text and analyze pages
            for page in domain_pages:
                all_text.append(page.get("plain_text", ""))
                
                # Count tables
                if page.get("tables"):
                    tables_count = len(page["tables"])
                    domain_insight["tables_found"] += tables_count
                    analysis["summary"]["tables_found"] += tables_count
                
                # Check for structured data
                if page.get("structured_data") and any(page["structured_data"].values()):
                    domain_insight["has_structured_data"] = True
                    analysis["summary"]["structured_data_found"] += 1
            
            analysis["domain_insights"].append(domain_insight)
        
        # Generate content summary
        combined_text = " ".join(all_text)
        # Truncate to avoid overwhelming analysis
        if len(combined_text) > 5000:
            combined_text = combined_text[:5000] + "..."
            
        analysis["content_summary"] = f"Total content extracted: {len(combined_text)} characters"
        
        return analysis


# Interactive mode function (missing in original)
async def interactive_deep_search():
    """Run the deep scraper in interactive mode."""
    print("Deep Web Search and Scraper - Interactive Mode")
    print("============================================")
    
    # Get configuration
    depth = int(input("Enter crawl depth (1-3, default: 2): ") or "2")
    max_pages = int(input("Enter max pages per domain (1-10, default: 5): ") or "5")
    
    service = DeepScraperService(max_depth=depth, max_pages_per_domain=max_pages)
    
    while True:
        print("\n")
        query = input("Enter search query (or 'exit' to quit): ")
        if query.lower() in ('exit', 'quit', 'q'):
            break
            
        num_results = int(input("Number of domains to scrape (1-5, default: 3): ") or "3")
        deep_crawl = input("Perform deep crawling? (y/n, default: y): ").lower() != 'n'
        
        print(f"\nSearching for '{query}' and scraping top {num_results} results...")
        results = await service.search_and_deep_scrape(
            query,
            num_results=num_results,
            perform_deep_crawl=deep_crawl
        )
        
        # Print summary
        print("\n--- Search Results ---")
        if results["success"]:
            for i, result in enumerate(results["search_results"]):
                print(f"{i+1}. {result['title']}")
                print(f"   URL: {result['url']}")
                print(f"   Snippet: {result['snippet']}")
                print()
                
            # Add analysis to results
            analysis = await service.analyze_deep_scrape_results(results)
            
            # Print analysis summary
            print("\n--- Analysis ---")
            print(f"Total domains scraped: {analysis['summary']['successful_domains']}/{analysis['summary']['total_domains']}")
            print(f"Total pages crawled: {analysis['summary']['total_pages']}")
            print(f"Tables found: {analysis['summary']['tables_found']}")
            
            # Save option
            save = input("\nSave results to file? (y/n, default: n): ").lower() == 'y'
            if save:
                filename = input("Enter filename (without extension): ") or f"search_{int(datetime.datetime.now().timestamp())}"
                if not filename.endswith('.json'):
                    filename += '.json'
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                print(f"Results saved to {filename}")
        else:
            print(f"Search failed: {results.get('error', 'Unknown error')}")


async def main():
    """Main function to handle command line arguments or run interactively."""
    parser = argparse.ArgumentParser(description="Deep Web Search and Scraper")
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--domains", "-d", type=int, default=3, help="Number of domains to scrape (default: 3)")
    parser.add_argument("--depth", "-p", type=int, default=2, help="Crawl depth (default: 2)")
    parser.add_argument("--max-pages", "-m", type=int, default=5, help="Max pages per domain (default: 5)")
    parser.add_argument("--no-deep-crawl", action="store_true", help="Disable deep crawling")
    parser.add_argument("--output", "-o", help="Output file (JSON)")
    parser.add_argument("--markdown-dir", "-md", help="Directory to save markdown files")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    
    args = parser.parse_args()
    
    # If no arguments or interactive mode requested, run interactively
    if len(sys.argv) == 1 or args.interactive:
        await interactive_deep_search()
        return
    
    # Process command line query
    if args.query:
        service = DeepScraperService(max_depth=args.depth, max_pages_per_domain=args.max_pages)
        results = await service.search_and_deep_scrape(
            args.query, 
            num_results=args.domains,
            perform_deep_crawl=not args.no_deep_crawl
        )
        
        # Print a summary
        print("\n--- Search Results Summary ---")
        if results["success"]:
            for i, result in enumerate(results["search_results"]):
                domain = service.scraper.get_domain(result['url'])
                scrape_status = "✓" if i < len(results["scraped_content"]) and results["scraped_content"][i]["success"] else "✗"
                
                print(f"{i+1}. [{scrape_status}] {result['title']} ({domain})")
                print(f"   URL: {result['url']}")
                
                # Show stats if available
                if i < len(results["scraped_content"]) and results["scraped_content"][i].get("success"):
                    if not args.no_deep_crawl:
                        pages_count = len(results["scraped_content"][i].get("pages", []))
                        print(f"   Pages crawled: {pages_count}")
                    else:
                        # For single page scrape, show a preview
                        content = results["scraped_content"][i].get("plain_text", "")
                        preview = content[:150] + "..." if len(content) > 150 else content
                        print(f"   Preview: {preview}")
                print()
            
            # Add analysis to results
            analysis = await service.analyze_deep_scrape_results(results)
            results["analysis"] = analysis
            
            # Print analysis summary
            print("\n--- Deep Scrape Analysis ---")
            print(f"Total domains scraped: {analysis['summary']['successful_domains']}/{analysis['summary']['total_domains']}")
            print(f"Total pages crawled: {analysis['summary']['total_pages']}")
            print(f"Tables found: {analysis['summary']['tables_found']}")
            print(f"Pages with structured data: {analysis['summary']['structured_data_found']}")
            
        else:
            print(f"Search failed: {results.get('error', 'Unknown error')}")
            
        # Save to file if requested
        if args.output:
            output_file = args.output
            if not output_file.endswith('.json'):
                output_file += '.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"Results saved to {output_file}")
        
        # Save markdown files if requested
        if args.markdown_dir:
            os.makedirs(args.markdown_dir, exist_ok=True)
            
            # Process each domain result
            for domain_idx, domain_result in enumerate(results["scraped_content"]):
                if not domain_result.get("success", False):
                    continue
                    
                # Get pages - either from deep crawl or single page
                pages = domain_result.get("pages", [domain_result])
                
                for page_idx, page in enumerate(pages):
                    if page.get("success") and page.get("markdown"):
                        # Create a safe filename
                        safe_title = re.sub(r'[^\w\s-]', '', page.get("title", f"result_{domain_idx+1}_{page_idx+1}"))
                        safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')
                        md_filename = f"d{domain_idx+1:02d}_p{page_idx+1:02d}-{safe_title[:30]}.md"
                        
                        with open(os.path.join(args.markdown_dir, md_filename), 'w', encoding='utf-8') as md_file:
                            # Add a header with metadata
                            md_file.write(f"# {page.get('title', 'Untitled')}\n\n")
                            md_file.write(f"URL: {page.get('url')}\n\n")
                            
                            if page.get("metadata"):
                                md_file.write(f"Description: {page['metadata'].get('description', '')}\n\n")
                                
                            # Add table data if available
                            if page.get("tables"):
                                md_file.write(f"## Tables Found ({len(page['tables'])})\n\n")
                                for table in page["tables"]:
                                    if table.get("caption"):
                                        md_file.write(f"### {table['caption']}\n\n")
                                    else:
                                        md_file.write(f"### Table {table['id'] + 1}\n\n")
                                        
                                    # Create markdown table
                                    if table["headers"]:
                                        md_file.write("| " + " | ".join(table["headers"]) + " |\n")
                                        md_file.write("| " + " | ".join(["---"] * len(table["headers"])) + " |\n")
                                        
                                    for row in table["rows"]:
                                        md_file.write("| " + " | ".join(row) + " |\n")
                                    
                                    md_file.write("\n")
                            
                            md_file.write("---\n\n")
                            # Write the markdown content
                            md_file.write(page["markdown"])
                            
            print(f"Markdown files saved to {args.markdown_dir}/")
        
        if not args.output:
            # If no output file specified, print full JSON to stdout
            print("\n--- Full Results Summary (truncated) ---")
            # Print a truncated version to prevent overwhelming the console
            summary_results = {
                "query": results["query"],
                "success": results["success"],
                "timestamp": results["timestamp"],
                "search_results": [{"title": r["title"], "url": r["url"]} for r in results["search_results"]],
                "analysis": results.get("analysis", {}),
            }
            print(json.dumps(summary_results, ensure_ascii=False, indent=2))
            print("\nNote: Full results not shown. Use --output to save complete data.")
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())