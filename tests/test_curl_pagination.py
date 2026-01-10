#!/usr/bin/env python3
"""Test CURL Pagination Reddit scraper"""

from reddit_sentiment import RedditSentimentAnalyzer
import sys

print("=" * 50)
print("Testing CURL Pagination Reddit Scraper")
print("=" * 50)

try:
    analyzer = RedditSentimentAnalyzer()

    # Request 150 posts to trigger pagination (since limit is 100)
    count = 150
    print(f"\nFetching {count} hot posts from r/CryptoCurrency using CURL directly...")
    
    posts = analyzer.scrape_via_curl(
        subreddit='CryptoCurrency',
        filter_type='hot',
        count=count,
        time_range=None
    )

    print(f"\nResult: {len(posts)} posts fetched")

    if len(posts) > 100:
        print(f"\n✅ Pagination Test PASSED (Fetched {len(posts)} > 100)")
    elif len(posts) == 100:
        print("\n⚠️ Pagination Test WARNING (Fetched exactly 100, might be single page limit)")
    else:
        print(f"\n❌ Pagination Test FAILED (Fetched {len(posts)})")

except Exception as e:
    print(f"\n❌ Test FAILED with error: {e}")
    import traceback
    traceback.print_exc()
