#!/usr/bin/env python3
"""
Background Reddit data fetcher
Run this script periodically (e.g., via cron) to fetch fresh Reddit data
The Streamlit app will load data from the generated JSON file
"""

import json
from datetime import datetime
from reddit_sentiment import RedditSentimentAnalyzer

def fetch_and_save_reddit_data(
    subreddit='CryptoCurrency',
    filter_type='hot',
    count=100,
    time_range=None,
    output_file='reddit_data.json'
):
    """
    Fetch Reddit data and save to JSON file
    """
    print(f"[{datetime.now()}] Starting Reddit data fetch...")
    print(f"  Subreddit: r/{subreddit}")
    print(f"  Filter: {filter_type}")
    print(f"  Count: {count}")
    
    # Initialize analyzer
    analyzer = RedditSentimentAnalyzer()
    
    # Scrape posts
    posts = analyzer.scrape_reddit_posts(
        subreddit=subreddit,
        filter_type=filter_type,
        count=count,
        time_range=time_range
    )
    
    if not posts:
        print("[ERROR] Failed to fetch posts")
        return False
    
    print(f"[SUCCESS] Fetched {len(posts)} posts")
    
    # Analyze sentiments
    posts = analyzer.analyze_posts(posts)
    print(f"[SUCCESS] Analyzed sentiments")
    
    # Convert to JSON-serializable format
    data = {
        'fetch_time': datetime.now().isoformat(),
        'subreddit': subreddit,
        'filter_type': filter_type,
        'count': len(posts),
        'posts': []
    }
    
    for post in posts:
        data['posts'].append({
            'id': post.id,
            'title': post.title,
            'selftext': post.selftext,
            'upvotes': post.upvotes,
            'num_comments': post.num_comments,
            'created_utc': post.created_utc,
            'url': post.url,
            'sentiment_scores': post.sentiment_scores,
            'detected_coins': post.detected_coins
        })
    
    # Save to JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"[SUCCESS] Data saved to {output_file}")
    print(f"[INFO] You can now load this data in Streamlit")
    
    return True


if __name__ == '__main__':
    import sys
    
    # Parse command line arguments
    filter_type = sys.argv[1] if len(sys.argv) > 1 else 'hot'
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    time_range = sys.argv[3] if len(sys.argv) > 3 else None
    
    print("=" * 60)
    print("Reddit Data Fetcher")
    print("=" * 60)
    
    success = fetch_and_save_reddit_data(
        filter_type=filter_type,
        count=count,
        time_range=time_range
    )
    
    if success:
        print("\n✅ SUCCESS! Run Streamlit app to view the data.")
    else:
        print("\n❌ FAILED! Check error messages above.")
        sys.exit(1)
