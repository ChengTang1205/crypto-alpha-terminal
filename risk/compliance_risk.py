"""
Compliance Risk Analysis Module
Evaluates project fundamentals and compliance risks through:
1. GitHub code activity monitoring
2. DefiLlama audit status
3. Regulatory news monitoring via RSS feeds
"""

import requests
import feedparser
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os
from termcolor import cprint

# ============================================================================
# Configuration
# ============================================================================

# RSS Feeds for crypto news (expanded with professional financial sources)
NEWS_FEEDS = {
    # Crypto-focused
    "CoinTelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CryptoNews": "https://cryptonews.com/news/feed/",
    "Bitcoin.com": "https://news.bitcoin.com/feed/",
    "NewsBTC": "https://www.newsbtc.com/feed/",
    # Professional Financial
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
}

# Google News search (for longer time range - up to 30 days)
GOOGLE_NEWS_TEMPLATE = "https://news.google.com/rss/search?q={query}+crypto&hl=en-US&gl=US&ceid=US:en"

# Keywords for NEGATIVE events (more precise)
NEGATIVE_KEYWORDS = [
    # Regulatory/Legal issues
    "lawsuit", "sued", "indictment", "charged", "arrest", 
    "investigation", "probe", "subpoena", "enforcement",
    "fine", "penalty", "sanction", "violation",
    # Security incidents
    "hack", "hacked", "exploit", "exploited", "breach",
    "stolen", "theft", "drain", "drained", "attack",
    "vulnerability", "bug", "flaw",
    # Scams/Fraud
    "rugpull", "rug pull", "scam", "fraud", "ponzi",
    "exit scam", "phishing",
    # Market negatives
    "crash", "plunge", "collapse", "bankruptcy", "insolvent",
    "delisted", "suspend", "halt",
]

# Keywords for POSITIVE events
POSITIVE_KEYWORDS = [
    # Partnerships & Adoption
    "partnership", "partners", "collaboration", "integration",
    "adoption", "launch", "launches", "launched",
    "upgrade", "update", "v2", "v3", "v4",
    # Growth & Investment
    "raise", "raised", "funding", "investment", "invest",
    "milestone", "record", "ath", "all-time high",
    "growth", "surge", "rally", "bullish",
    # Regulatory positive
    "approved", "approval", "license", "licensed",
    "compliant", "compliance", "legalize", "legal",
    # Technology
    "mainnet", "testnet", "airdrop", "staking",
    "scaling", "layer 2", "l2",
]

# Project name aliases (for better matching)
PROJECT_ALIASES = {
    "uniswap": ["uniswap", "uni", "$uni", "uniswap labs"],
    "aave": ["aave", "$aave", "aave protocol"],
    "compound": ["compound", "comp", "$comp", "compound finance"],
    "bitcoin": ["bitcoin", "btc", "$btc"],
    "ethereum": ["ethereum", "eth", "$eth", "ether"],
    "solana": ["solana", "sol", "$sol"],
    "cardano": ["cardano", "ada", "$ada"],
    "polygon": ["polygon", "matic", "$matic"],
    "chainlink": ["chainlink", "link", "$link"],
    "avalanche": ["avalanche", "avax", "$avax"],
    "arbitrum": ["arbitrum", "arb", "$arb"],
    "optimism": ["optimism", "op", "$op"],
    "lido": ["lido", "ldo", "$ldo", "lido finance"],
    "maker": ["makerdao", "maker", "mkr", "$mkr", "dai"],
    "curve": ["curve", "crv", "$crv", "curve finance"],
    "sushi": ["sushiswap", "sushi", "$sushi"],
    "pancakeswap": ["pancakeswap", "cake", "$cake"],
    "1inch": ["1inch", "$1inch"],
    "yearn": ["yearn", "yfi", "$yfi", "yearn finance"],
    "synthetix": ["synthetix", "snx", "$snx"],
    "balancer": ["balancer", "bal", "$bal"],
    "ripple": ["ripple", "xrp", "$xrp"],
    "binance": ["binance", "bnb", "$bnb", "binance coin"],
    "coinbase": ["coinbase", "coin", "$coin"],
    "kraken": ["kraken"],
    "ftx": ["ftx", "sbf"],
    "tether": ["tether", "usdt", "$usdt"],
    "usdc": ["usdc", "$usdc", "circle"],
    "defi": ["defi", "decentralized finance"],
}

# ============================================================================
# Project Track Classification (for risk baseline)
# ============================================================================

# Project tracks with base risk scores (lower = less risky)
PROJECT_TRACKS = {
    # Layer 1 Blockchain - Most established, lowest base risk
    "layer1_major": {
        "base_score": 25,
        "label": "主链 Layer 1 (主流)",
        "projects": ["bitcoin", "ethereum"],
        "description": "久经考验的主流区块链"
    },
    "layer1_alt": {
        "base_score": 35,
        "label": "主链 Layer 1 (新兴)",
        "projects": ["solana", "cardano", "avalanche", "polygon"],
        "description": "新兴但已建立市场的区块链"
    },
    # Layer 2 Solutions
    "layer2": {
        "base_score": 40,
        "label": "Layer 2 扩容方案",
        "projects": ["arbitrum", "optimism", "polygon"],
        "description": "以太坊扩容解决方案"
    },
    # DeFi Protocols - Blue chip
    "defi_bluechip": {
        "base_score": 35,
        "label": "DeFi 蓝筹",
        "projects": ["uniswap", "aave", "compound", "makerdao", "lido", "curve"],
        "description": "头部 DeFi 协议，经过时间验证"
    },
    # DeFi Protocols - Established
    "defi_established": {
        "base_score": 45,
        "label": "DeFi 成熟项目",
        "projects": ["sushiswap", "yearn", "synthetix", "balancer", "1inch", "pancakeswap"],
        "description": "成熟的 DeFi 协议"
    },
    # Infrastructure & Oracle
    "infrastructure": {
        "base_score": 35,
        "label": "基础设施/预言机",
        "projects": ["chainlink"],
        "description": "关键基础设施项目"
    },
    # Stablecoins
    "stablecoin": {
        "base_score": 30,
        "label": "稳定币",
        "projects": ["tether", "usdc", "dai"],
        "description": "主流稳定币"
    },
    # Centralized Exchanges
    "cex": {
        "base_score": 40,
        "label": "中心化交易所",
        "projects": ["binance", "coinbase", "kraken"],
        "description": "主流中心化交易所"
    },
    # Unknown/New Projects - Highest base risk
    "unknown": {
        "base_score": 55,
        "label": "新兴/未分类项目",
        "projects": [],
        "description": "新项目或未分类项目"
    }
}

# Risk factors configuration
RISK_FACTORS = {
    # Technical Risk (增加风险分)
    "no_audit": {"impact": +15, "label": "未审计", "category": "技术风险"},
    "inactive_code": {"impact": +10, "label": "代码不活跃", "category": "技术风险"},
    "low_activity": {"impact": +5, "label": "代码活动较低", "category": "技术风险"},
    "negative_news": {"impact": +8, "label": "有负面新闻", "category": "舆情风险"},
    "many_negative_news": {"impact": +15, "label": "大量负面新闻", "category": "舆情风险"},
    
    # Defensive Factors (减少风险分)
    "audited": {"impact": -10, "label": "已审计", "category": "安全因素"},
    "multi_audited": {"impact": -15, "label": "多重审计", "category": "安全因素"},
    "very_active_code": {"impact": -10, "label": "代码非常活跃", "category": "开发因素"},
    "active_code": {"impact": -5, "label": "代码活跃", "category": "开发因素"},
    "high_tvl": {"impact": -10, "label": "高 TVL (>$1B)", "category": "市场因素"},
    "medium_tvl": {"impact": -5, "label": "中等 TVL (>$100M)", "category": "市场因素"},
    "positive_news": {"impact": -5, "label": "正面新闻", "category": "舆情因素"},
    "established_project": {"impact": -10, "label": "成熟项目 (>3年)", "category": "历史因素"},
}

# Popular GitHub repos for crypto projects (for quick lookup)
KNOWN_REPOS = {
    "uniswap": ("Uniswap", "interface"),
    "aave": ("aave", "aave-v3-core"),
    "compound": ("compound-finance", "compound-protocol"),
    "makerdao": ("makerdao", "dss"),
    "curve": ("curvefi", "curve-contract"),
    "sushiswap": ("sushiswap", "sushiswap"),
    "pancakeswap": ("pancakeswap", "pancake-smart-contracts"),
    "1inch": ("1inch", "limit-order-protocol"),
    "yearn": ("yearn", "yearn-vaults"),
    "synthetix": ("Synthetixio", "synthetix"),
    "balancer": ("balancer", "balancer-v2-monorepo"),
    "lido": ("lidofinance", "lido-dao"),
    "ethereum": ("ethereum", "go-ethereum"),
    "bitcoin": ("bitcoin", "bitcoin"),
    "solana": ("solana-labs", "solana"),
}

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class GitHubActivity:
    """GitHub repository activity data"""
    owner: str
    repo: str
    commits_30d: int
    commits_90d: int
    contributors: int
    last_commit_date: str
    stars: int
    forks: int
    open_issues: int
    success: bool
    error: Optional[str] = None

@dataclass
class AuditStatus:
    """DeFi protocol audit information"""
    name: str
    audited: bool
    auditors: List[str]
    tvl: float
    category: str
    chain: str
    success: bool
    error: Optional[str] = None

@dataclass
class NewsItem:
    """News article item with sentiment classification"""
    title: str
    link: str
    source: str
    published: str
    sentiment: str  # "positive", "negative", or "neutral"
    matched_keywords: List[str]
    is_project_specific: bool = True  # Whether it directly mentions the project

# ============================================================================
# GitHub Activity Monitoring
# ============================================================================

def get_github_activity(owner: str, repo: str, token: Optional[str] = None) -> GitHubActivity:
    """
    Fetch GitHub repository activity metrics.
    
    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        token: Optional GitHub personal access token for higher rate limits
        
    Returns:
        GitHubActivity dataclass with repository metrics
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    try:
        # 1. Get repository info
        repo_url = f"https://api.github.com/repos/{owner}/{repo}"
        repo_response = requests.get(repo_url, headers=headers, timeout=10)
        
        if repo_response.status_code == 404:
            return GitHubActivity(
                owner=owner, repo=repo, commits_30d=0, commits_90d=0,
                contributors=0, last_commit_date="", stars=0, forks=0,
                open_issues=0, success=False, error="Repository not found"
            )
        
        repo_response.raise_for_status()
        repo_data = repo_response.json()
        
        # 2. Get commit counts for different time periods
        commits_30d = _count_commits(owner, repo, 30, headers)
        commits_90d = _count_commits(owner, repo, 90, headers)
        
        # 3. Get contributors count
        contributors_url = f"https://api.github.com/repos/{owner}/{repo}/contributors?per_page=1"
        contributors_response = requests.get(contributors_url, headers=headers, timeout=10)
        
        # Parse Link header to get total count
        contributors_count = 0
        if 'Link' in contributors_response.headers:
            link_header = contributors_response.headers['Link']
            # Extract last page number from Link header
            for part in link_header.split(','):
                if 'rel="last"' in part:
                    import re
                    match = re.search(r'page=(\d+)', part)
                    if match:
                        contributors_count = int(match.group(1))
        else:
            contributors_count = len(contributors_response.json()) if contributors_response.ok else 0
        
        # 4. Parse last commit date
        pushed_at = repo_data.get("pushed_at", "")
        if pushed_at:
            last_commit = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            last_commit_str = last_commit.strftime("%Y-%m-%d %H:%M")
        else:
            last_commit_str = "Unknown"
        
        return GitHubActivity(
            owner=owner,
            repo=repo,
            commits_30d=commits_30d,
            commits_90d=commits_90d,
            contributors=contributors_count,
            last_commit_date=last_commit_str,
            stars=repo_data.get("stargazers_count", 0),
            forks=repo_data.get("forks_count", 0),
            open_issues=repo_data.get("open_issues_count", 0),
            success=True
        )
        
    except requests.exceptions.RequestException as e:
        cprint(f"❌ GitHub API error: {e}", "red")
        return GitHubActivity(
            owner=owner, repo=repo, commits_30d=0, commits_90d=0,
            contributors=0, last_commit_date="", stars=0, forks=0,
            open_issues=0, success=False, error=str(e)
        )


def _count_commits(owner: str, repo: str, days: int, headers: dict) -> int:
    """Count commits in the last N days"""
    since_date = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    params = {"since": since_date, "per_page": 100}
    
    total = 0
    page = 1
    max_pages = 10  # Limit to avoid rate limiting
    
    while page <= max_pages:
        params["page"] = page
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if not response.ok:
                break
            commits = response.json()
            if not commits:
                break
            total += len(commits)
            if len(commits) < 100:
                break
            page += 1
        except:
            break
    
    return total


def lookup_github_repo(project_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Look up known GitHub repositories for popular crypto projects.
    
    Args:
        project_name: Name of the project (e.g., "uniswap", "aave")
        
    Returns:
        Tuple of (owner, repo) or (None, None) if not found
    """
    key = project_name.lower().strip()
    if key in KNOWN_REPOS:
        return KNOWN_REPOS[key]
    return None, None


# ============================================================================
# DefiLlama Audit Status
# ============================================================================

def get_defi_audit_status(protocol_name: str) -> AuditStatus:
    """
    Fetch protocol audit status from DefiLlama.
    
    Args:
        protocol_name: Name of the DeFi protocol (e.g., "uniswap", "aave")
        
    Returns:
        AuditStatus dataclass with audit information
    """
    try:
        # Fetch all protocols from DefiLlama
        url = "https://api.llama.fi/protocols"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        protocols = response.json()
        
        # Search for matching protocol
        search_name = protocol_name.lower().strip()
        matched_protocol = None
        
        for protocol in protocols:
            name = protocol.get("name", "").lower()
            slug = protocol.get("slug", "").lower()
            symbol = protocol.get("symbol", "").lower()
            
            if search_name in name or search_name == slug or search_name == symbol:
                matched_protocol = protocol
                break
        
        if not matched_protocol:
            return AuditStatus(
                name=protocol_name,
                audited=False,
                auditors=[],
                tvl=0,
                category="Unknown",
                chain="Unknown",
                success=False,
                error="Protocol not found in DefiLlama"
            )
        
        # Extract audit information
        audit_info = matched_protocol.get("audits", "0")
        auditors = matched_protocol.get("audit_links", []) or matched_protocol.get("audits_auditedBy", [])
        
        # Parse auditors from audit_note if available
        audit_note = matched_protocol.get("audit_note", "")
        if audit_note and not auditors:
            auditors = [audit_note]
        
        # Determine if audited
        is_audited = str(audit_info) != "0" and str(audit_info) != ""
        if isinstance(auditors, list) and len(auditors) > 0:
            is_audited = True
        
        return AuditStatus(
            name=matched_protocol.get("name", protocol_name),
            audited=is_audited,
            auditors=auditors if isinstance(auditors, list) else [auditors] if auditors else [],
            tvl=matched_protocol.get("tvl", 0) or 0,
            category=matched_protocol.get("category", "Unknown"),
            chain=matched_protocol.get("chain", "Unknown"),
            success=True
        )
        
    except requests.exceptions.RequestException as e:
        cprint(f"❌ DefiLlama API error: {e}", "red")
        return AuditStatus(
            name=protocol_name,
            audited=False,
            auditors=[],
            tvl=0,
            category="Unknown",
            chain="Unknown",
            success=False,
            error=str(e)
        )


# ============================================================================
# Regulatory News Monitoring
# ============================================================================

def _get_project_search_terms(project_name: str) -> List[str]:
    """Get all search terms for a project including aliases"""
    key = project_name.lower().strip()
    
    # Check if project has aliases
    if key in PROJECT_ALIASES:
        return PROJECT_ALIASES[key]
    
    # Check partial matches
    for alias_key, aliases in PROJECT_ALIASES.items():
        if key in alias_key or alias_key in key:
            return aliases
    
    # Return just the project name if no aliases found
    return [key]


def _is_project_mentioned(text: str, search_terms: List[str]) -> bool:
    """
    Check if any search term is mentioned in text using word boundary matching.
    This prevents false positives like 'uni' matching 'university'.
    """
    import re
    text_lower = text.lower()
    
    for term in search_terms:
        # For short terms (<=3 chars), use strict word boundary matching
        if len(term) <= 3:
            # Match term with word boundaries (space, punctuation, start/end)
            pattern = r'(?:^|[\s\(\[\{,.:;!?\'\"]|(?<=\$))' + re.escape(term) + r'(?:$|[\s\)\]\},.:;!?\'\"])'
            if re.search(pattern, text_lower):
                return True
        else:
            # For longer terms, simple substring matching is fine
            if term in text_lower:
                return True
    return False


def _classify_sentiment(text: str) -> tuple:
    """
    Classify text sentiment based on keywords.
    Returns: (sentiment, matched_keywords)
    """
    text_lower = text.lower()
    
    neg_matches = []
    pos_matches = []
    
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in text_lower:
            neg_matches.append(keyword)
    
    for keyword in POSITIVE_KEYWORDS:
        if keyword in text_lower:
            pos_matches.append(keyword)
    
    # Determine sentiment based on keyword counts
    if len(neg_matches) > len(pos_matches) and len(neg_matches) > 0:
        return "negative", neg_matches
    elif len(pos_matches) > len(neg_matches) and len(pos_matches) > 0:
        return "positive", pos_matches
    elif len(neg_matches) > 0 or len(pos_matches) > 0:
        # Mixed signals - return as neutral with all keywords
        return "neutral", neg_matches + pos_matches
    else:
        return "neutral", []


def get_regulatory_news(project_name: str, max_items: int = 30) -> List[NewsItem]:
    """
    Fetch and classify news from RSS feeds.
    
    Args:
        project_name: Name of the project to search for
        max_items: Maximum number of news items to return
        
    Returns:
        List of NewsItem dataclasses with sentiment classification
    """
    all_news = []
    general_news = []  # Fallback for general crypto news
    
    # Get all search terms for the project
    search_terms = _get_project_search_terms(project_name)
    cprint(f"  🔎 Search terms: {', '.join(search_terms)}", "cyan")
    
    # Browser-like headers to avoid blocking
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    for source_name, feed_url in NEWS_FEEDS.items():
        try:
            cprint(f"  📰 Fetching {source_name}...", "cyan")
            
            # Use requests with headers to fetch RSS content
            response = requests.get(feed_url, headers=headers, timeout=10)
            if response.status_code != 200:
                cprint(f"    ⚠️ {source_name} returned status {response.status_code}", "yellow")
                continue
            
            # Parse the RSS content
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                cprint(f"    ⚠️ {source_name} has no entries", "yellow")
                continue
            
            cprint(f"    ✓ Found {len(feed.entries)} articles", "green")
            
            for entry in feed.entries[:50]:  # Limit per source
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                title_lower = title.lower()
                summary_lower = summary.lower() if summary else ""
                combined_text = title_lower + " " + summary_lower
                
                # Classify sentiment
                sentiment, matched_keywords = _classify_sentiment(combined_text)
                
                # Parse published date
                published = entry.get("published", entry.get("updated", "Unknown"))
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
                    except:
                        pass
                
                # Check if any search term is mentioned
                is_project_related = _is_project_mentioned(combined_text, search_terms)
                
                news_item = NewsItem(
                    title=title,
                    link=entry.get("link", ""),
                    source=source_name,
                    published=published,
                    sentiment=sentiment,
                    matched_keywords=matched_keywords,
                    is_project_specific=is_project_related
                )
                
                if is_project_related:
                    all_news.append(news_item)
                else:
                    # Collect general crypto news as fallback
                    general_news.append(news_item)
                
        except requests.exceptions.Timeout:
            cprint(f"  ⚠️ Timeout fetching {source_name}", "yellow")
            continue
        except Exception as e:
            cprint(f"  ⚠️ Error fetching {source_name}: {e}", "yellow")
            continue
    
    # If few/no project-specific news from RSS, try Google News (longer time range)
    if len(all_news) < 5:
        cprint(f"  🔍 Searching Google News for more {project_name} articles...", "cyan")
        try:
            # Use the main project name for Google News search
            google_url = GOOGLE_NEWS_TEMPLATE.format(query=project_name.replace(" ", "+"))
            response = requests.get(google_url, headers=headers, timeout=10)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                cprint(f"    ✓ Found {len(feed.entries)} Google News articles", "green")
                
                for entry in feed.entries[:30]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    combined_text = (title + " " + summary).lower()
                    
                    # Google News results should already be relevant, but double-check
                    if not _is_project_mentioned(combined_text, search_terms):
                        continue
                    
                    sentiment, matched_keywords = _classify_sentiment(combined_text)
                    
                    published = entry.get("published", "Unknown")
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        try:
                            published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
                        except:
                            pass
                    
                    # Extract actual source from Google News title (usually ends with " - Source")
                    source = "Google News"
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        if len(parts) == 2:
                            title = parts[0]
                            source = parts[1]
                    
                    news_item = NewsItem(
                        title=title,
                        link=entry.get("link", ""),
                        source=source,
                        published=published,
                        sentiment=sentiment,
                        matched_keywords=matched_keywords,
                        is_project_specific=True
                    )
                    all_news.append(news_item)
                    
        except Exception as e:
            cprint(f"  ⚠️ Google News error: {e}", "yellow")
    
    # If still no project-specific news, include general crypto news
    if len(all_news) == 0 and len(general_news) > 0:
        cprint(f"  ℹ️ No {project_name}-specific news, showing general crypto news", "yellow")
        # Sort general news: negative first, then positive, then neutral
        general_news.sort(key=lambda x: (
            0 if x.sentiment == "negative" else (1 if x.sentiment == "positive" else 2),
            x.published
        ), reverse=True)
        all_news = general_news[:max_items]
    
    # Sort: project-specific first, then by sentiment priority (negative > positive > neutral)
    all_news.sort(key=lambda x: (
        not x.is_project_specific,
        0 if x.sentiment == "negative" else (1 if x.sentiment == "positive" else 2),
    ))
    
    cprint(f"  📊 Total news found: {len(all_news)}", "cyan")
    
    # Count by sentiment
    neg_count = sum(1 for n in all_news if n.sentiment == "negative")
    pos_count = sum(1 for n in all_news if n.sentiment == "positive")
    neu_count = sum(1 for n in all_news if n.sentiment == "neutral")
    cprint(f"  📈 Sentiment: {pos_count} positive, {neg_count} negative, {neu_count} neutral", "cyan")
    
    return all_news[:max_items]


# ============================================================================
# Risk Score Calculation
# ============================================================================

def _get_project_track(project_name: str) -> tuple:
    """
    Determine the project track and base score.
    Returns: (track_key, track_info)
    """
    key = project_name.lower().strip()
    
    # Also check aliases
    for alias_key, aliases in PROJECT_ALIASES.items():
        if key in aliases or key == alias_key:
            key = alias_key
            break
    
    # Find matching track
    for track_key, track_info in PROJECT_TRACKS.items():
        if key in track_info["projects"]:
            return track_key, track_info
    
    # Default to unknown track
    return "unknown", PROJECT_TRACKS["unknown"]


def calculate_risk_score(
    project_name: str,
    github_activity: Optional[GitHubActivity],
    audit_status: Optional[AuditStatus],
    news_items: List[NewsItem]
) -> Dict:
    """
    Calculate comprehensive risk score using track-based baseline model.
    
    Formula: Final Risk = Base Score + Risk Factors - Defensive Factors
    
    Returns:
        Dict with score (0-100, lower is better), grade (A-F), breakdown, and track info
    """
    # 1. Determine project track and base score
    track_key, track_info = _get_project_track(project_name)
    base_score = track_info["base_score"]
    track_label = track_info["label"]
    
    # Initialize breakdown with track info
    breakdown = {
        "track": {
            "name": track_label,
            "base_score": base_score,
            "description": track_info["description"]
        }
    }
    
    risk_increases = []  # Factors that increase risk
    risk_decreases = []  # Factors that decrease risk
    
    # 2. Evaluate GitHub Activity
    if github_activity and github_activity.success:
        commits = github_activity.commits_30d
        if commits >= 50:
            risk_decreases.append(("very_active_code", RISK_FACTORS["very_active_code"]))
        elif commits >= 20:
            risk_decreases.append(("active_code", RISK_FACTORS["active_code"]))
        elif commits >= 5:
            pass  # Neutral - no impact
        elif commits > 0:
            risk_increases.append(("low_activity", RISK_FACTORS["low_activity"]))
        else:
            risk_increases.append(("inactive_code", RISK_FACTORS["inactive_code"]))
    
    # 3. Evaluate Audit Status
    if audit_status and audit_status.success:
        if audit_status.audited:
            if len(audit_status.auditors) >= 2:
                risk_decreases.append(("multi_audited", RISK_FACTORS["multi_audited"]))
            else:
                risk_decreases.append(("audited", RISK_FACTORS["audited"]))
            
            # Add TVL factor
            tvl = audit_status.tvl or 0
            if tvl >= 1_000_000_000:  # $1B+
                risk_decreases.append(("high_tvl", RISK_FACTORS["high_tvl"]))
            elif tvl >= 100_000_000:  # $100M+
                risk_decreases.append(("medium_tvl", RISK_FACTORS["medium_tvl"]))
        else:
            # For Layer 1 major chains, no audit is expected (not smart contracts)
            if track_key != "layer1_major":
                risk_increases.append(("no_audit", RISK_FACTORS["no_audit"]))
    else:
        # For unknown audit status, only penalize non-L1 projects
        if track_key not in ["layer1_major", "layer1_alt"]:
            risk_increases.append(("no_audit", RISK_FACTORS["no_audit"]))
    
    # 4. Evaluate News Sentiment
    negative_count = sum(1 for n in news_items if n.sentiment == "negative")
    positive_count = sum(1 for n in news_items if n.sentiment == "positive")
    
    if negative_count >= 5:
        risk_increases.append(("many_negative_news", RISK_FACTORS["many_negative_news"]))
    elif negative_count >= 1:
        risk_increases.append(("negative_news", RISK_FACTORS["negative_news"]))
    
    if positive_count > negative_count and positive_count >= 3:
        risk_decreases.append(("positive_news", RISK_FACTORS["positive_news"]))
    
    # 5. Check for established project status (based on track)
    if track_key in ["layer1_major", "defi_bluechip", "stablecoin"]:
        risk_decreases.append(("established_project", RISK_FACTORS["established_project"]))
    
    # 6. Calculate final score
    total_increase = sum(f["impact"] for _, f in risk_increases)
    total_decrease = sum(f["impact"] for _, f in risk_decreases)
    
    final_score = base_score + total_increase + total_decrease
    final_score = max(0, min(100, final_score))  # Clamp to 0-100
    
    # Build breakdown details
    breakdown["risk_increases"] = [
        {"factor": key, "label": f["label"], "category": f["category"], "impact": f"+{f['impact']}"}
        for key, f in risk_increases
    ]
    breakdown["risk_decreases"] = [
        {"factor": key, "label": f["label"], "category": f["category"], "impact": str(f["impact"])}
        for key, f in risk_decreases
    ]
    breakdown["calculation"] = {
        "base_score": base_score,
        "total_increase": total_increase,
        "total_decrease": total_decrease,
        "final_score": final_score
    }
    
    # Determine grade
    if final_score <= 15:
        grade = "A+"
        label = "极低风险"
    elif final_score <= 25:
        grade = "A"
        label = "低风险"
    elif final_score <= 35:
        grade = "B"
        label = "较低风险"
    elif final_score <= 45:
        grade = "C"
        label = "中等风险"
    elif final_score <= 60:
        grade = "D"
        label = "较高风险"
    else:
        grade = "F"
        label = "高风险"
    
    return {
        "score": final_score,
        "grade": grade,
        "label": label,
        "track": track_label,
        "breakdown": breakdown
    }


# ============================================================================
# Main Analysis Function
# ============================================================================

def analyze_project_compliance(
    project_name: str,
    github_owner: Optional[str] = None,
    github_repo: Optional[str] = None,
    github_token: Optional[str] = None
) -> Dict:
    """
    Perform comprehensive compliance risk analysis for a project.
    
    Args:
        project_name: Name of the project/protocol
        github_owner: Optional GitHub owner (auto-lookup if not provided)
        github_repo: Optional GitHub repo (auto-lookup if not provided)
        github_token: Optional GitHub token for higher rate limits
        
    Returns:
        Dict with all analysis results
    """
    cprint(f"\n🔍 Analyzing compliance for: {project_name}", "cyan")
    
    results = {
        "project_name": project_name,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # 1. GitHub Activity
    if not github_owner or not github_repo:
        github_owner, github_repo = lookup_github_repo(project_name)
    
    if github_owner and github_repo:
        cprint(f"  📊 Fetching GitHub activity for {github_owner}/{github_repo}...", "cyan")
        github_activity = get_github_activity(github_owner, github_repo, github_token)
        results["github"] = github_activity
    else:
        cprint(f"  ⚠️ No GitHub repo found for {project_name}", "yellow")
        results["github"] = None
    
    # 2. DefiLlama Audit Status
    cprint(f"  🔐 Fetching audit status from DefiLlama...", "cyan")
    audit_status = get_defi_audit_status(project_name)
    results["audit"] = audit_status
    
    # 3. Regulatory News
    cprint(f"  📰 Scanning news for regulatory events...", "cyan")
    news_items = get_regulatory_news(project_name)
    results["news"] = news_items
    
    # 4. Calculate Risk Score
    risk_score = calculate_risk_score(
        project_name,
        results.get("github"),
        results.get("audit"),
        news_items
    )
    results["risk_score"] = risk_score
    
    cprint(f"\n✅ Analysis complete. Risk Grade: {risk_score['grade']} ({risk_score['label']})", "green")
    
    return results


# ============================================================================
# CLI Testing
# ============================================================================

if __name__ == "__main__":
    import json
    
    # Test with Uniswap
    test_project = "uniswap"
    results = analyze_project_compliance(test_project)
    
    # Print summary
    print("\n" + "="*60)
    print(f"Project: {results['project_name']}")
    print(f"Risk Score: {results['risk_score']['score']}/100")
    print(f"Risk Grade: {results['risk_score']['grade']} - {results['risk_score']['label']}")
    print("="*60)
    
    if results.get("github") and results["github"].success:
        g = results["github"]
        print(f"\nGitHub Activity ({g.owner}/{g.repo}):")
        print(f"  - Commits (30d): {g.commits_30d}")
        print(f"  - Commits (90d): {g.commits_90d}")
        print(f"  - Contributors: {g.contributors}")
        print(f"  - Stars: {g.stars}")
    
    if results.get("audit") and results["audit"].success:
        a = results["audit"]
        print(f"\nAudit Status:")
        print(f"  - Audited: {'Yes' if a.audited else 'No'}")
        print(f"  - Auditors: {', '.join(a.auditors) if a.auditors else 'N/A'}")
        print(f"  - TVL: ${a.tvl:,.0f}")
    
    print(f"\nNews Items: {len(results['news'])} found")
    negative_news = [n for n in results['news'] if n.sentiment == "negative"]
    if negative_news:
        print("  ⚠️ Negative News:")
        for n in negative_news[:3]:
            print(f"    - {n.title[:60]}...")
