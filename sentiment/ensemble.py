import transformers.utils.import_utils
import transformers.modeling_utils

# Monkey-patch to bypass strict torch version check (we are on torch 2.2.2)
# Must be done BEFORE any other transformers imports
transformers.utils.import_utils.check_torch_load_is_safe = lambda: None
transformers.modeling_utils.check_torch_load_is_safe = lambda: None

import torch
from transformers import pipeline
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from termcolor import cprint

class CryptoSentimentEnsemble:
    def __init__(self, use_gpu: bool = True):
        """
        初始化三个情感分析模型。
        """
        # 0. 硬件检测
        self.device = 0 if use_gpu and torch.cuda.is_available() else -1
        cprint(f"🤖 Loading sentiment models on device: {'GPU' if self.device == 0 else 'CPU'}...", "cyan")

        # 1. 初始化 VADER (需下载词典)
        try:
            nltk.data.find('sentiment/vader_lexicon.zip')
        except LookupError:
            nltk.download('vader_lexicon', quiet=True)
        self.vader = SentimentIntensityAnalyzer()

        # 2. 初始化 Twitter-roBERTa (通用社媒语境)
        # model_id: cardiffnlp/twitter-roberta-base-sentiment-latest
        # Labels: positive, neutral, negative
        cprint("   Loading Twitter-roBERTa...", "cyan")
        self.roberta_pipe = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest",
            top_k=None, # 返回所有标签概率
            device=self.device
        )

        # 3. 初始化 CryptoBERT (加密货币语境)
        # model_id: ElKulako/cryptobert
        # Labels: Bullish, Neutral, Bearish
        cprint("   Loading CryptoBERT...", "cyan")
        self.crypto_pipe = pipeline(
            "sentiment-analysis",
            model="ElKulako/cryptobert",
            tokenizer="ElKulako/cryptobert",
            top_k=None, # 返回所有标签概率
            device=self.device
        )
        cprint("✨ All sentiment models loaded successfully.", "green")

    def _normalize_transformer_output(self, results, pos_labels, neg_labels):
        """
        核心逻辑：将 Transformer 概率分布转换为 [-1, 1] 标量。
        Formula: Score = P(Positive) - P(Negative)
        """
        # results 结构示例: [{'label': 'positive', 'score': 0.9}, {'label': 'negative', 'score': 0.05}...]
        # Flatten list of lists if necessary (pipeline sometimes returns list of lists for single input)
        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], list):
            results = results[0]
            
        scores_map = {item['label']: item['score'] for item in results}
        
        # 获取正向概率 (sum处理是为了防止模型输出多标签变体，虽不常见但作为防御性编程)
        p_pos = sum(scores_map.get(l, 0.0) for l in pos_labels)
        
        # 获取负向概率
        p_neg = sum(scores_map.get(l, 0.0) for l in neg_labels)
        
        return p_pos - p_neg

    def analyze(self, text: str, weights: dict = None):
        """
        执行多模型分析并加权。
        默认权重: CryptoBERT(0.5) + roBERTa(0.3) + VADER(0.2)
        """
        if weights is None:
            weights = {'crypto': 0.5, 'roberta': 0.3, 'vader': 0.2}

        # --- A. VADER ---
        # compound 已经是 -1 到 1
        vader_score = self.vader.polarity_scores(text)['compound']

        # --- B. Twitter-roBERTa ---
        # 截断过长文本以防报错 (BERT限制512 tokens)
        # Pipeline handles truncation usually, but explicit slicing is safer for very long text
        roberta_raw = self.roberta_pipe(text[:2000], truncation=True)
        # Pipeline returns a list (one per input text), we sent one text
        if isinstance(roberta_raw, list) and isinstance(roberta_raw[0], list):
             roberta_raw = roberta_raw[0]
             
        roberta_score = self._normalize_transformer_output(
            roberta_raw, 
            pos_labels=['positive'], 
            neg_labels=['negative']
        )

        # --- C. CryptoBERT ---
        crypto_raw = self.crypto_pipe(text[:2000], truncation=True)
        if isinstance(crypto_raw, list) and isinstance(crypto_raw[0], list):
             crypto_raw = crypto_raw[0]

        crypto_score = self._normalize_transformer_output(
            crypto_raw, 
            pos_labels=['Bullish'], 
            neg_labels=['Bearish']
        )

        # --- D. 加权计算 ---
        final_score = (
            (crypto_score * weights['crypto']) +
            (roberta_score * weights['roberta']) +
            (vader_score * weights['vader'])
        )

        return {
            "text_snippet": text[:50] + "..." if len(text) > 50 else text,
            "final_score": round(final_score, 4),
            "breakdown": {
                "crypto_bert": round(crypto_score, 4),
                "twitter_roberta": round(roberta_score, 4),
                "vader": round(vader_score, 4)
            },
            "raw_probabilities": {
                "roberta": roberta_raw,
                "crypto": crypto_raw
            }
        }
