#!/usr/bin/env python3
"""Test Selenium Reddit scraper"""

from reddit_sentiment import RedditSentimentAnalyzer
import sys

print("=" * 50)
print("Testing Selenium Reddit Scraper")
print("=" * 50)

try:
    analyzer = RedditSentimentAnalyzer()

    print("\nFetching 10 hot posts from r/CryptoCurrency using Selenium...")
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
        print("\n✅ Selenium Test PASSED")
    else:
        print("\n❌ No posts fetched - check debug output above")

except Exception as e:
    print(f"\n❌ Test FAILED with error: {e}")
    import traceback
    traceback.print_exc()
