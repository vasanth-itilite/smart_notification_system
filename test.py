import requests
import urllib.parse
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

def search_duckduckgo(query, num_results=10):
    """
    Perform a search on DuckDuckGo and return the results.
    
    Args:
        query (str): The search query
        num_results (int): Number of results to return
    
    Returns:
        list: A list of dictionaries containing search results
    """
    # URL encode the query
    encoded_query = urllib.parse.quote_plus(query)
    
    # Construct the search URL
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    # Set headers to mimic a browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://duckduckgo.com/'
    }
    
    try:
        # Send the request
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract search results
        results = []
        for result in soup.select('.result')[:num_results]:
            title_element = result.select_one('.result__title a')
            snippet_element = result.select_one('.result__snippet')
            
            if title_element and snippet_element:
                title = title_element.text.strip()
                snippet = snippet_element.text.strip()
                url = title_element.get('href')
                
                if url and url.startswith('/'):
                    url_params = urllib.parse.parse_qs(url.split('?')[1])
                    if 'uddg' in url_params:
                        url = url_params['uddg'][0]
                
                results.append({
                    'title': title,
                    'snippet': snippet,
                    'url': url
                })
        
        return results
    
    except Exception as e:
        print(f"Error during search: {e}")
        return []

def clean_url(url):
    """Clean and normalize URLs from search results."""
    # Handle ad URLs that start with duckduckgo.com/y.js
    if url.startswith('https://duckduckgo.com/y.js?'):
        try:
            # Make a HEAD request to follow redirects
            response = requests.head(url, allow_redirects=True, timeout=5)
            return response.url
        except:
            return url
    
    return url

def scrape_website(url):
    """Scrape content from a website URL."""
    url = clean_url(url)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Use the content's detected encoding
        soup = BeautifulSoup(response.content, 'html.parser', from_encoding=response.encoding)
        
        # Get page title
        title = soup.title.text.strip() if soup.title else "No title"
        
        # Remove script and style tags
        for script in soup(["script", "style"]):
            script.extract()
        
        # Extract main content based on common content containers
        main_content = None
        for selector in ['main', 'article', '.content', '#content', '.main', '.article', '.post']:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        # If no main content container found, use the body
        if not main_content:
            main_content = soup.body
        
        paragraphs = []
        if main_content:
            # Get all text paragraphs
            for p in main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'li']):
                text = p.get_text().strip()
                if text:  # Any non-empty paragraph
                    paragraphs.append(text)
        
        # If we didn't get content, try a different approach
        if not paragraphs:
            text = soup.get_text()
            # Remove extra whitespace
            import re
            text = re.sub(r'\s+', ' ', text).strip()
            # Split into sentences
            sentences = re.split(r'(?<=[.!?])\s+', text)
            paragraphs = [s for s in sentences if len(s) > 10]
        
        return {
            "url": url,
            "title": title,
            "content": paragraphs,
            "success": True
        }
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {
            "url": url,
            "title": "Failed to scrape",
            "content": [f"Error: {str(e)}"],
            "success": False
        }

def search_and_scrape(query, num_results=8, max_paragraphs=50):
    """
    Search for a query on DuckDuckGo, scrape the websites from the results,
    and return all the data.
    
    Args:
        query (str): The search query
        num_results (int): Number of search results to process
        max_paragraphs (int): Maximum number of paragraphs to return per site
    
    Returns:
        dict: Dictionary containing search results and scraped content
    """
    print(f"Searching for: {query}")
    search_results = search_duckduckgo(query, num_results)
    
    if not search_results:
        return {
            "query": query,
            "search_results": [],
            "scraped_data": [],
            "error": "No search results found"
        }
    
    print(f"Found {len(search_results)} results. Scraping websites...")
    
    # Scrape websites using multithreading
    scraped_data = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(scrape_website, result['url']): result for result in search_results}
        for future in future_to_url:
            try:
                site_data = future.result()
                
                # Limit number of paragraphs to avoid overwhelming amounts of data
                if len(site_data['content']) > max_paragraphs:
                    site_data['content'] = site_data['content'][:max_paragraphs]
                
                scraped_data.append(site_data)
                print(f"Scraped: {site_data['url']}")
                
                # Sleep a bit to avoid overloading websites
                time.sleep(random.uniform(0.5, 1))
            except Exception as e:
                print(f"Error processing site: {e}")
    
    return {
        "query": query,
        "search_results": search_results,
        "scraped_data": scraped_data
    }

def print_results(results):
    """Print the search and scraping results in a readable format."""
    print(f"\n{'='*80}")
    print(f"RESULTS FOR: {results['query']}")
    print(f"{'='*80}\n")
    
    if "error" in results:
        print(f"ERROR: {results['error']}")
        return
    
    print(f"Found {len(results['search_results'])} search results and scraped {len(results['scraped_data'])} websites.\n")
    
    for i, site in enumerate(results['scraped_data'], 1):
        print(f"\n{'-'*80}")
        print(f"SITE {i}: {site['title']}")
        print(f"URL: {site['url']}")
        print(f"{'-'*80}\n")
        
        if not site['success']:
            print(f"Failed to scrape this site: {site['content'][0]}")
            continue
        
        print(f"CONTENT (showing {len(site['content'])} paragraphs):")
        for j, paragraph in enumerate(site['content'], 1):
            # Limit paragraph length for display
            if len(paragraph) > 300:
                paragraph = paragraph[:300] + "..."
            print(f"{j}. {paragraph}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("Enter your search query: ")
    
    results = search_and_scrape(query)
    print_results(results)
    
    # You can also save the results to a file
    import json
    with open(f"{query.replace(' ', '_')}_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults saved to {query.replace(' ', '_')}_results.json")