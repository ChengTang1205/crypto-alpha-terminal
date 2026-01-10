"""
Twitter Sentiment Analysis Module
Refactored from Moon Dev's Sentiment Agent
"""

import os
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from termcolor import cprint

# Note: We no longer patch httpx globally since it breaks other libraries (OpenAI, etc.)
# Manual cookie import makes this patch unnecessary

from twikit import Client, TooManyRequests

# ML Imports (Lazy loaded to speed up startup if not used)
torch = None
AutoTokenizer = None
AutoModelForSequenceClassification = None

class TwitterSentimentAnalyzer:
    def __init__(self):
        self.ensemble = None
        self.client = None
        
    def _load_model(self):
        """Lazy load Ensemble models"""
        if self.ensemble is None:
            from sentiment.ensemble import CryptoSentimentEnsemble
            self.ensemble = CryptoSentimentEnsemble()

    def _init_client(self):
        """Initialize Twitter client"""
        if self.client is None:
            from sentiment.twitter_auth import get_client
            self.client = get_client()
            if not self.client:
                raise Exception("Not logged in. Please run twitter_auth.py first.")

    async def fetch_tweets(self, query: str, count: int = 20) -> List[Dict]:
        """Fetch tweets for a query with pagination"""
        self._init_client()
        
        # 1. Query Optimization
        # Add exclusion filters to reduce noise
        exclusion_terms = [
            "-giveaway", "-airdrop", "-whitelist", "-presale", "-bot", 
            "-filter:links", "min_faves:3", "lang:en"
        ]
        optimized_query = f"{query} {' '.join(exclusion_terms)}"
        
        collected_tweets = []
        seen_hashes = set()
        
        # Blacklist for post-processing (Aggressive filtering)
        blacklist = [
            "join my telegram", "dm for promo", "pump", "100x", "gem", 
            "whatsapp", "click link", "promotion", "send dm", "in bio"
        ]
        
        try:
            cprint(f"🔍 Searching Twitter for: {optimized_query}", "cyan")
            
            # Initial request
            tweets = await self.client.search_tweet(optimized_query, product='Latest', count=min(20, count))
            
            # Keep fetching until we have enough tweets
            while tweets and len(collected_tweets) < count:
                # Process current batch
                batch_count = 0
                for tweet in tweets:
                    if len(collected_tweets) >= count:
                        break
                    
                    # --- Post-Processing Filters (Scheme 2) ---
                    
                    # 1. Deduplication
                    text_hash = hash(tweet.text)
                    if text_hash in seen_hashes:
                        continue
                    seen_hashes.add(text_hash)
                    
                    # 2. Hashtag/Cashtag Density
                    # Skip if too many tags (spam indicator)
                    if tweet.text.count('#') > 5 or tweet.text.count('$') > 5:
                        continue
                        
                    # 3. Blacklist Check
                    text_lower = tweet.text.lower()
                    if any(bad_word in text_lower for bad_word in blacklist):
                        continue

                    # Basic filtering - skip retweets
                    if not tweet.text.startswith('RT @'):
                        collected_tweets.append({
                            'id': tweet.id,
                            'text': tweet.text,
                            'created_at': tweet.created_at,
                            'user': tweet.user.name,
                            'screen_name': tweet.user.screen_name,
                            'likes': tweet.favorite_count,
                            'retweets': tweet.retweet_count
                        })
                        batch_count += 1
                
                cprint(f"  Fetched {batch_count} tweets (total: {len(collected_tweets)}/{count})", "cyan")
                
                # Check if we have enough
                if len(collected_tweets) >= count:
                    break
                
                # Try to get next page
                try:
                    tweets = await tweets.next()
                    if not tweets:
                        cprint(f"ℹ️ No more tweets available (got {len(collected_tweets)} total)", "yellow")
                        break
                except AttributeError:
                    # No next() method available
                    cprint(f"ℹ️ Pagination not available (got {len(collected_tweets)} total)", "yellow")
                    break
                except Exception as e:
                    # Other errors (rate limit, etc.)
                    cprint(f"⚠️ Pagination stopped: {str(e)[:50]}", "yellow")
                    break
            
            cprint(f"✅ Total tweets collected: {len(collected_tweets)}", "green")
            return collected_tweets
            
        except Exception as e:
            cprint(f"❌ Error fetching tweets: {e}", "red")
            return collected_tweets if collected_tweets else []

    def analyze_sentiment(self, tweets: List[Dict]) -> Dict:
        """Analyze sentiment of tweets using Ensemble Model"""
        self._load_model()
        
        if not tweets:
            return {'score': 0, 'label': 'Neutral', 'distribution': {}}
            
        scores = []
        crypto_scores = []
        roberta_scores = []
        vader_scores = []
        
        pos_count = 0
        neg_count = 0
        neu_count = 0
        
        cprint(f"🧠 Analyzing {len(tweets)} tweets with CryptoSentimentEnsemble...", "cyan")
        
        for tweet in tweets:
            # Analyze each tweet
            res = self.ensemble.analyze(tweet['text'])
            score = res['final_score']
            scores.append(score)
            
            # Collect individual model scores
            if 'breakdown' in res:
                crypto_scores.append(res['breakdown'].get('crypto_bert', 0))
                roberta_scores.append(res['breakdown'].get('twitter_roberta', 0))
                vader_scores.append(res['breakdown'].get('vader', 0))
            
            # Categorize based on score
            if score > 0.05:
                pos_count += 1
            elif score < -0.05:
                neg_count += 1
            else:
                neu_count += 1
        
        avg_score = np.mean(scores)
        
        # Determine label (adjusted thresholds)
        if avg_score > 0.4: label = "Very Positive"
        elif avg_score > 0.1: label = "Positive"
        elif avg_score < -0.4: label = "Very Negative"
        elif avg_score < -0.1: label = "Negative"
        else: label = "Neutral"
        
        return {
            'score': float(avg_score),
            'label': label,
            'count': len(tweets),
            'distribution': {
                'Positive': pos_count,
                'Neutral': neu_count,
                'Negative': neg_count
            },
            'breakdown': {
                'crypto_bert': float(np.mean(crypto_scores)) if crypto_scores else 0.0,
                'twitter_roberta': float(np.mean(roberta_scores)) if roberta_scores else 0.0,
                'vader': float(np.mean(vader_scores)) if vader_scores else 0.0
            },
            'raw_scores': scores
        }

    def generate_narrative_summary(self, tweets: List[Dict], api_key: str, provider: str = "OpenAI", base_url: str = None, model_name: str = "gpt-4o") -> str:
        """
        Generate a narrative summary of the tweets using an LLM.
        """
        if not tweets:
            return "No tweets available to summarize."

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.prompts import ChatPromptTemplate
            
            # Initialize LLM
            if provider == "DeepSeek-V3":
                llm = ChatOpenAI(
                    model=model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=0.7
                )
            else: # OpenAI
                llm = ChatOpenAI(
                    model=model_name,
                    openai_api_key=api_key,
                    temperature=0.7
                )

            # Prepare tweet text blob
            # User requested to use ALL tweets (not just top 50) to align with other models
            # Note: 200 tweets * ~280 chars = ~56k chars, which fits easily in GPT-4o/DeepSeek context (128k)
            tweets_text = "\n".join([f"- {t['text']}" for t in tweets])

            prompt = ChatPromptTemplate.from_template("""
            You are a Senior Crypto Trader & Analyst (Degen/Alpha Hunter). 
            Analyze the following tweets about a specific crypto asset to find "Alpha" and filter out noise.
            
            Tweets:
            {tweets_text}
            
            Your task:
            1. **Narrative**: Identify the REAL story. Is it a tax sell-off? ETF flow? specific FUD? (Skip generic "market fluctuation" talk).
            2. **Price Action**: If prices are mentioned, identify if they are viewed as Support, Resistance, or Liquidation levels.
            3. **FUD Check**: Explicitly label any rumors or panic as [FUD] or [Verified].
            
            Output format (Use Markdown):
            **🔥 Alpha Narrative**: [Direct, sharp summary of the main driver. No fluff.]
            **🐂/🐻 Sentiment & Levels**: [Sentiment + Key Price Levels. IMPORTANT: Escape all dollar signs with a backslash, e.g., \$88k, to prevent formatting errors.]
            **🎯 AI Score**: [Float between -1.0 (Extreme Bearish) and 1.0 (Extreme Bullish). Just the number.]
            **⚠️ Risk / FUD Watch**: [Specific risks or FUD topics to ignore]
            **👀 Trader's Outlook**: [One actionable thought: e.g., "Watch for bounce at \$X" or "Sell pressure likely until Y"]
            
            Tone: Professional but sharp, like a hedge fund internal memo.
            """)

            chain = prompt | llm
            response = chain.invoke({"tweets_text": tweets_text})
            return response.content
            
        except Exception as e:
            return f"❌ Failed to generate summary: {str(e)}"
