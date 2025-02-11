# news_crawler.py

from bs4 import BeautifulSoup
import asyncio
from urllib.parse import urljoin, urlparse
import aiohttp
from datetime import datetime
from typing import List, Dict, Set
import re
import json
import os
import logging

class NewsCrawler:
    def __init__(self, 
                 output_dir: str = "crawled_news",
                 exclude_external_links: bool = True,
                 exclude_social_media_links: bool = True,
                 exclude_domains: List[str] = None,
                 max_depth: int = 3):
        self.output_dir = output_dir
        self.exclude_external_links = exclude_external_links
        self.exclude_social_media_links = exclude_social_media_links
        self.exclude_domains = set(exclude_domains or [])
        self.visited_urls: Set[str] = set()
        self.max_depth = max_depth
        self.url_depths: Dict[str, int] = {}
        
        # News-specific patterns
        self.news_patterns = {
            'article_selectors': [
                'article', '.article', '.post', '.story', '.news-item',
                '[data-type="article"]', '.article-body', '.story-body'
            ],
            'date_selectors': [
                'time', '.published', '.post-date', '.article-date',
                'meta[property="article:published_time"]', '.timestamp',
                '.date', '[data-timestamp]'
            ],
            'author_selectors': [
                '.author', '.byline', '.writer', 'meta[name="author"]',
                '.article-author', '.story-author'
            ],
            'category_selectors': [
                '.category', '.section', '.topic', 'meta[property="article:section"]',
                '.article-category', '.news-category'
            ]
        }
        
        self.social_media_patterns = [
            r'facebook\.com', r'twitter\.com', r'linkedin\.com',
            r'instagram\.com', r'youtube\.com', r'tiktok\.com'
        ]
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename=os.path.join(output_dir, 'crawler.log')
        )
        self.logger = logging.getLogger(__name__)
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)

    def _is_news_url(self, url: str, base_domain: str) -> bool:
        """Validate if URL is a news article."""
        parsed_url = urlparse(url)
        
        if not parsed_url.netloc:
            return False

        if parsed_url.netloc in self.exclude_domains:
            return False

        if self.exclude_social_media_links:
            if any(re.search(pattern, url.lower()) for pattern in self.social_media_patterns):
                return False

        if self.exclude_external_links and parsed_url.netloc != base_domain:
            return False

        # News-specific path checks
        path = parsed_url.path.lower()
        news_indicators = [
            '/article/', '/news/', '/story/', '/politics/',
            '/business/', '/tech/', '/science/', '/health/',
            '/sports/', '/culture/', '/opinion/', '/analysis/'
        ]
        
        if any(indicator in path for indicator in news_indicators):
            return True
            
        # Skip non-article pages
        skip_patterns = [
            '/tag/', '/author/', '/about/', '/contact/',
            '/search/', '/login/', '/register/', '/subscribe/',
            '/privacy/', '/terms/', '/sitemap/', '/rss/',
            '/feed/', '/category/', '/topics/'
        ]
        if any(pattern in path for pattern in skip_patterns):
            return False

        return True

    def _extract_news_content(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract news article content and metadata."""
        article_data = {
            "title": None,
            "content": "",
            "timestamp": None,
            "author": None,
            "category": None,
            "summary": None,
            "source_url": url,
            "related_articles": []
        }

        # Extract title
        title_selectors = [
            'h1', 'article h1', '.article-title', '.post-title', 
            'meta[property="og:title"]', 'meta[name="twitter:title"]'
        ]
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                article_data["title"] = title_elem.get('content', None) or title_elem.get_text(strip=True)
                break

        # Extract content
        for selector in self.news_patterns['article_selectors']:
            content_elem = soup.select_one(selector)
            if content_elem:
                # Clean unwanted elements
                for unwanted in content_elem.select('script, style, nav, header, footer, .ad, .advertisement, .social-share'):
                    unwanted.decompose()
                
                # Get paragraphs
                paragraphs = content_elem.find_all('p')
                if paragraphs:
                    article_data["content"] = ' '.join(p.get_text(strip=True) for p in paragraphs)
                    # Create summary from first paragraph
                    if len(paragraphs[0].get_text(strip=True)) > 100:
                        article_data["summary"] = paragraphs[0].get_text(strip=True)
                break

        # Extract metadata
        for selector in self.news_patterns['date_selectors']:
            date_elem = soup.select_one(selector)
            if date_elem:
                article_data["timestamp"] = (date_elem.get('datetime') or 
                                          date_elem.get('content') or 
                                          date_elem.get_text(strip=True))
                break

        for selector in self.news_patterns['author_selectors']:
            author_elem = soup.select_one(selector)
            if author_elem:
                article_data["author"] = author_elem.get('content', None) or author_elem.get_text(strip=True)
                break

        for selector in self.news_patterns['category_selectors']:
            category_elem = soup.select_one(selector)
            if category_elem:
                article_data["category"] = category_elem.get('content', None) or category_elem.get_text(strip=True)
                break

        # Find related articles
        related_links = soup.select('.related-articles a, .read-more a, .similar-articles a')
        article_data["related_articles"] = [
            urljoin(url, link['href']) for link in related_links if 'href' in link.attrs
        ][:5]

        return article_data

    async def _fetch_url(self, session: aiohttp.ClientSession, url: str) -> tuple:
        """Fetch URL content with proper headers."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    return await response.text(), None
                return None, f"HTTP {response.status}"
        except asyncio.TimeoutError:
            return None, "Timeout error"
        except Exception as e:
            return None, str(e)

    async def crawl_news(self, start_url: str, max_pages: int = 100) -> List[Dict]:
        """Crawl news website and extract articles."""
        base_domain = urlparse(start_url).netloc
        self.logger.info(f"Starting news crawl of {start_url}")
        
        results = []
        to_visit = {(start_url, 0)}  # (url, depth)
        
        async with aiohttp.ClientSession() as session:
            while to_visit and len(self.visited_urls) < max_pages:
                # Process URLs in parallel batches
                current_batch = []
                for _ in range(min(5, len(to_visit))):
                    if to_visit:
                        url, depth = to_visit.pop()
                        if url not in self.visited_urls and depth <= self.max_depth:
                            current_batch.append((url, depth))
                
                if not current_batch:
                    continue
                
                # Fetch and process URLs in parallel
                tasks = [self._process_news_url(session, url, depth, base_domain) 
                        for url, depth in current_batch]
                batch_results = await asyncio.gather(*tasks)
                
                # Handle results
                for url_results in batch_results:
                    if url_results:
                        article_data, new_urls = url_results
                        if article_data:
                            results.append(article_data)
                        for new_url, new_depth in new_urls:
                            if (new_url not in self.visited_urls and 
                                new_url not in [u for u, _ in to_visit] and 
                                new_depth <= self.max_depth):
                                to_visit.add((new_url, new_depth))
        
        # Save results
        saved_file = self.save_results(results, base_domain)
        self.logger.info(f"Crawl completed. Processed {len(self.visited_urls)} pages, found {len(results)} articles")
        
        return results

    async def _process_news_url(self, session: aiohttp.ClientSession, url: str, depth: int, base_domain: str) -> tuple:
        """Process a single news URL."""
        self.visited_urls.add(url)
        self.logger.info(f"Crawling: {url} (depth: {depth})")
        
        html_content, error = await self._fetch_url(session, url)
        if error:
            self.logger.error(f"Error fetching {url}: {error}")
            return None
        
        soup = BeautifulSoup(html_content, 'html.parser')
        article_data = None
        new_urls = set()
        
        # Check for article content
        if any(soup.select_one(selector) for selector in self.news_patterns['article_selectors']):
            article_data = self._extract_news_content(soup, url)
            
        # Find new URLs
        for link in soup.find_all('a', href=True):
            new_url = urljoin(url, link['href'])
            if self._is_news_url(new_url, base_domain):
                new_urls.add((new_url, depth + 1))
        
        return article_data, new_urls

    def save_results(self, results: List[Dict], domain: str) -> str:
        """Save crawled news results."""
        if not results:
            return None
        
        # Create domain directory
        domain_dir = os.path.join(self.output_dir, domain.replace('.', '_'))
        os.makedirs(domain_dir, exist_ok=True)
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"news_results_{timestamp}.json"
        filepath = os.path.join(domain_dir, filename)
        
        # Save with metadata
        output_data = {
            "metadata": {
                "domain": domain,
                "crawl_timestamp": datetime.now().isoformat(),
                "total_articles": len(results),
                "total_pages_crawled": len(self.visited_urls)
            },
            "articles": results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Saved {len(results)} articles to {filepath}")
        return filepath

# Example usage
async def main():
    crawler = NewsCrawler(
        output_dir="crawled_news",
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_domains=['ads.example.com'],
        max_depth=3
    )
    
    url = "https://www.theguardian.com/education"
    
    try:
        results = await crawler.crawl_news(url, max_pages=10)
        print(f"\nCrawl Summary:")
        print(f"Total pages crawled: {len(crawler.visited_urls)}")
        print(f"Articles found: {len(results)}")
        print(f"Results saved in: {crawler.output_dir}")
        
    except Exception as e:
        print(f"Error during crawling: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
