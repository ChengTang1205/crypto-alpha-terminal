#!/usr/bin/env python3
"""Test Reddit scraper"""

from reddit_sentiment import RedditSentimentAnalyzer

print("=" * 50)
print("Testing Reddit Scraper")
print("=" * 50)

analyzer = RedditSentimentAnalyzer()

print("\nFetching 10 hot posts from r/CryptoCurrency...")
posts = analyzer.scrape_reddit_posts(
    subreddit='CryptoCurrency',
    filter_type='hot',
    count=10
)

print(f"\nResult: {len(posts)} posts fetched")

if posts:
    print("\nFirst post:")
    print(f"  Title: {posts[0].title}")
    print(f"  Upvotes: {posts[0].upvotes}")
    print(f"  URL: {posts[0].url}")
else:
    print("\nNo posts fetched - check debug output above")
