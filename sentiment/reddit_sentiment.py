"""
Reddit Sentiment Analysis Module

Ported from Cryptocurrency-Sentiment-Bot (C#)
Analyzes sentiment from r/CryptoCurrency using VADER and web scraping
No API credentials required - uses Reddit's public JSON endpoints
"""

import requests
import re
import traceback
from datetime import datetime
from typing import List, Dict, Optional
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


class RedditPost:
    """Data model for Reddit posts"""
    def __init__(self, post_data: dict):
        self.id = post_data.get('id', '')
        self.title = post_data.get('title', '')
        self.selftext = post_data.get('selftext', '')
        self.upvotes = post_data.get('ups', 0)
        self.num_comments = post_data.get('num_comments', 0)
        self.created_utc = post_data.get('created_utc', 0)
        self.url = f"https://reddit.com{post_data.get('permalink', '')}"
        
        # Sentiment analysis fields
        self.sentiment_scores = None
        self.detected_coins = []


class RedditSentimentAnalyzer:
    """Main class for Reddit sentiment analysis"""
    
    # Common cryptocurrency patterns
    COIN_PATTERNS = {
        'BTC': ['btc', 'bitcoin'],
        'ETH': ['eth', 'ethereum'],
        'SOL': ['sol', 'solana'],
        'ADA': ['ada', 'cardano'],
        'XRP': ['xrp', 'ripple'],
        'DOGE': ['doge', 'dogecoin'],
        'MATIC': ['matic', 'polygon'],
        'DOT': ['dot', 'polkadot'],
        'AVAX': ['avax', 'avalanche'],
        'LINK': ['link', 'chainlink'],
        'UNI': ['uni', 'uniswap'],
        'ATOM': ['atom', 'cosmos'],
        'LTC': ['ltc', 'litecoin'],
        'BCH': ['bch', 'bitcoin cash'],
        'ALGO': ['algo', 'algorand'],
        'VET': ['vet', 'vechain'],
        'ICP': ['icp', 'internet computer'],
        'FIL': ['fil', 'filecoin'],
        'NEAR': ['near', 'near protocol'],
        'HBAR': ['hbar', 'hedera'],
    }
    
    def __init__(self):
        """Initialize VADER sentiment analyzer"""
        self.analyzer = SentimentIntensityAnalyzer()
        self.session = requests.Session()
        self.session.headers.update({
            # Reddit requires a specific User-Agent format: <platform>:<app ID>:<version string> (by /u/<reddit username>)
            # Using a custom one often works better than faking Chrome in Cloud environments
            'User-Agent': 'python:crypto-alpha-terminal:v1.0.0 (by /u/CryptoTerminalBot)',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        })
    
    def scrape_reddit_posts(
        self,
        subreddit: str = 'CryptoCurrency',
        filter_type: str = 'hot',
        count: int = 100,
        time_range: Optional[str] = None
    ) -> List[RedditPost]:
        """
        Scrape Reddit posts using multiple mirrors to bypass blocks
        """
        import time
        import random
        
        # List of domains to try (Main + Mirrors)
        # Prioritize .json endpoints directly
        # List of domains to try (Main + Mirrors)
        # 1. Official JSON (often blocked in Cloud)
        # 2. Libreddit Mirrors (Privacy front-ends, often work better)
        # 3. RSS Feed (XML) - Most robust fallback
        domains = [
            'https://www.reddit.com/r/{subreddit}/{filter_type}.json', 
            'https://l.opnxng.com',      # Libreddit Mirror 1
            'https://rx.dd84.de',        # Libreddit Mirror 2
            'https://libreddit.bus-hit.me', # Libreddit Mirror 3
            'rss_fallback',              # Special flag for RSS parsing
        ]
        
        posts = []
        
        for domain in domains:
            try:
                print(f"[DEBUG] Trying domain: {domain}")
                
                # Adjust URL format based on domain
                # Adjust URL format based on domain
                if domain == 'rss_fallback':
                    # Skip here, handled in except/else block or special check
                    continue

                if '.json' in domain:
                    # It's already a full URL template
                    url = domain.format(subreddit=subreddit, filter_type=filter_type) + f"?limit={count}"
                else:
                    # It's a base domain (Mirror)
                    url = f"{domain}/r/{subreddit}/{filter_type}.json?limit={count}"
                
                if filter_type == 'top' and time_range:
                    url += f"&t={time_range}"
                
                print(f"[DEBUG] Fetching URL: {url}")
                
                # Add random delay
                time.sleep(random.uniform(0.5, 1.5))
                
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Handle different JSON structures if needed
                    children = data['data']['children']
                    
                    for child in children:
                        post_data = child['data']
                        posts.append(RedditPost(post_data))
                        
                    print(f"✅ Successfully scraped {len(posts)} posts from {domain}")
                    return posts
                else:
                    print(f"❌ Failed to fetch from {domain}: Status {response.status_code}")
                    
            except Exception as e:
                print(f"Error fetching from {domain}: {e}")
                continue
        
        # --- Final Fallback: RSS Feed Parsing ---
        # If all JSON endpoints fail (429/403), try the raw RSS feed which is often unblocked
        try:
            print("[DEBUG] All JSON mirrors failed. Trying RSS Fallback...")
            rss_url = f"https://www.reddit.com/r/{subreddit}/{filter_type}/.rss"
            # RSS needs a different User-Agent usually, or just raw requests
            rss_response = requests.get(rss_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            if rss_response.status_code == 200:
                import feedparser
                feed = feedparser.parse(rss_response.content)
                print(f"✅ RSS Fallback successful: Found {len(feed.entries)} entries")
                
                for entry in feed.entries:
                    # Map RSS entry to RedditPost format
                    # RSS 'content' usually contains HTML, we need to be careful
                    # But for sentiment, title is most important
                    
                    # Extract roughly equivalent fields
                    post_data = {
                        'id': entry.get('id', ''),
                        'title': entry.get('title', ''),
                        'selftext': entry.get('summary', ''), # RSS summary is the body
                        'ups': 0, # RSS doesn't show upvotes
                        'num_comments': 0, 
                        'created_utc': time.mktime(entry.published_parsed) if hasattr(entry, 'published_parsed') else time.time(),
                        'permalink': entry.get('link', '').replace('https://www.reddit.com', '')
                    }
                    posts.append(RedditPost(post_data))
                return posts
            else:
                print(f"❌ RSS Fallback failed: {rss_response.status_code}")
        except Exception as e:
            print(f"Error in RSS Fallback: {e}")

        # Fallback: Try CURL if all python requests failed
        if not posts:
            print("[DEBUG] All requests failed, trying CURL fallback...")
            posts = self.scrape_via_curl(subreddit, filter_type, count, time_range)
        
        if not posts:
            print("[ERROR] All mirrors and methods failed to return posts")
        
        return posts[:count]

    def scrape_via_curl(self, subreddit, filter_type, count, time_range) -> List[RedditPost]:
        """Fallback method using system CURL to bypass TLS fingerprinting"""
        import subprocess
        import json
        import time
        
        posts = []
        after = None
        
        while len(posts) < count:
            # Calculate how many more we need
            remaining = count - len(posts)
            limit = min(remaining, 100)
            
            url = f"https://old.reddit.com/r/{subreddit}/{filter_type}.json?limit={limit}"
            if filter_type == 'top' and time_range:
                url += f"&t={time_range}"
            
            if after:
                url += f"&after={after}"
                
            print(f"[DEBUG] Trying CURL: {url}")
            
            try:
                # Construct curl command with browser headers
                cmd = [
                    'curl', '-s', '-A', 
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    url
                ]
                
                # Add delay if paginating
                if after:
                    time.sleep(1.5)
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0 and result.stdout:
                    try:
                        data = json.loads(result.stdout)
                        children = data.get('data', {}).get('children', [])
                        
                        if not children:
                            print("[DEBUG] No more posts from CURL")
                            break
                            
                        batch_posts = []
                        for child in children:
                            post_data = child.get('data', {})
                            if post_data:
                                batch_posts.append(RedditPost(post_data))
                        
                        posts.extend(batch_posts)
                        print(f"[SUCCESS] CURL fetched {len(batch_posts)} posts (Total: {len(posts)})")
                        
                        # Get pagination token
                        after = data.get('data', {}).get('after')
                        if not after:
                            print("[DEBUG] No more pages (no 'after' token)")
                            break
                            
                    except json.JSONDecodeError:
                        print("[DEBUG] CURL returned invalid JSON")
                        break
                else:
                    print(f"[DEBUG] CURL failed: {result.stderr}")
                    break
                    
            except Exception as e:
                print(f"[DEBUG] CURL error: {e}")
                break
            
        return posts[:count]
    
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using VADER
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict with keys: 'neg', 'neu', 'pos', 'compound'
        """
        return self.analyzer.polarity_scores(text)
    
    def detect_coins(self, text: str) -> List[str]:
        """
        Detect cryptocurrency mentions in text
        
        Args:
            text: Text to search
            
        Returns:
            List of detected coin symbols (e.g., ['BTC', 'ETH'])
        """
        text_lower = text.lower()
        detected = []
        
        for symbol, keywords in self.COIN_PATTERNS.items():
            for keyword in keywords:
                # Match whole words only
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, text_lower):
                    detected.append(symbol)
                    break
        
        return list(set(detected))  # Remove duplicates
    
    def analyze_posts(self, posts: List[RedditPost]) -> List[RedditPost]:
        """
        Analyze sentiment and detect coins for all posts
        
        Args:
            posts: List of RedditPost objects
            
        Returns:
            Same list with sentiment_scores and detected_coins populated
        """
        for post in posts:
            # Combine title and selftext for analysis
            text = f"{post.title} {post.selftext}"
            
            # Analyze sentiment
            post.sentiment_scores = self.analyze_sentiment(text)
            
            # Detect mentioned coins
            post.detected_coins = self.detect_coins(text)
        
        return posts
    
    def aggregate_by_coin(self, posts: List[RedditPost]) -> Dict[str, Dict]:
        """
        Aggregate sentiment scores by cryptocurrency
        
        Args:
            posts: List of analyzed RedditPost objects
            
        Returns:
            Dict mapping coin symbol to aggregated stats:
            {
                'BTC': {
                    'avg_compound': float,
                    'post_count': int,
                    'scores': [list of compound scores],
                    'avg_pos': float,
                    'avg_neg': float,
                    'avg_neu': float
                },
                ...
            }
        """
        coin_data = {}
        
        for post in posts:
            if not post.sentiment_scores or not post.detected_coins:
                continue
            
            for coin in post.detected_coins:
                if coin not in coin_data:
                    coin_data[coin] = {
                        'scores': [],
                        'pos_scores': [],
                        'neg_scores': [],
                        'neu_scores': []
                    }
                
                coin_data[coin]['scores'].append(post.sentiment_scores['compound'])
                coin_data[coin]['pos_scores'].append(post.sentiment_scores['pos'])
                coin_data[coin]['neg_scores'].append(post.sentiment_scores['neg'])
                coin_data[coin]['neu_scores'].append(post.sentiment_scores['neu'])
        
        # Calculate averages
        result = {}
        for coin, data in coin_data.items():
            if data['scores']:
                result[coin] = {
                    'avg_compound': sum(data['scores']) / len(data['scores']),
                    'avg_pos': sum(data['pos_scores']) / len(data['pos_scores']),
                    'avg_neg': sum(data['neg_scores']) / len(data['neg_scores']),
                    'avg_neu': sum(data['neu_scores']) / len(data['neu_scores']),
                    'post_count': len(data['scores']),
                    'scores': data['scores']
                }
        
        return result
    
    def get_sentiment_distribution(self, posts: List[RedditPost]) -> Dict[str, int]:
        """
        Calculate sentiment distribution across all posts
        
        Returns:
            {'positive': int, 'neutral': int, 'negative': int}
        """
        distribution = {'positive': 0, 'neutral': 0, 'negative': 0}
        
        for post in posts:
            if not post.sentiment_scores:
                continue
            
            compound = post.sentiment_scores['compound']
            if compound >= 0.05:
                distribution['positive'] += 1
            elif compound <= -0.05:
                distribution['negative'] += 1
            else:
                distribution['neutral'] += 1
        
        return distribution
    
    def get_top_posts(
        self,
        posts: List[RedditPost],
        by: str = 'negative',
        limit: int = 10
    ) -> List[RedditPost]:
        """
        Get top posts by sentiment
        
        Args:
            posts: List of analyzed posts
            by: 'negative' or 'positive'
            limit: Number of posts to return
            
        Returns:
            Sorted list of top posts
        """
        analyzed_posts = [p for p in posts if p.sentiment_scores]
        
        if by == 'negative':
            sorted_posts = sorted(
                analyzed_posts,
                key=lambda p: p.sentiment_scores['compound']
            )
        else:  # positive
            sorted_posts = sorted(
                analyzed_posts,
                key=lambda p: p.sentiment_scores['compound'],
                reverse=True
            )
        
        return sorted_posts[:limit]
