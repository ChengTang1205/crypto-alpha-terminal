import pandas as pd
import numpy as np
import talib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
from typing import Dict, List, Tuple

# XGBoost is disabled on macOS due to libomp compatibility issues
XGBOOST_AVAILABLE = False
XGBClassifier = None
# If you want to re-enable XGBoost, uncomment below:
# try:
#     from xgboost import XGBClassifier as _XGBClassifier
#     XGBClassifier = _XGBClassifier
#     XGBOOST_AVAILABLE = True
# except Exception as e:
#     print(f"Warning: XGBoost not available: {e}")

# LightGBM is disabled on macOS due to libomp compatibility issues
LIGHTGBM_AVAILABLE = False
LGBMClassifier = None
# If you want to re-enable LightGBM, uncomment below:
# try:
#     from lightgbm import LGBMClassifier as _LGBMClassifier
#     LGBMClassifier = _LGBMClassifier
#     LIGHTGBM_AVAILABLE = True
# except Exception as e:
#     print(f"Warning: LightGBM not available: {e}")

class AIStrategy:
    def __init__(self, model_type: str = 'random_forest', n_estimators: int = 100, max_depth: int = 10):
        """
        Initialize AI Strategy.
        model_type: 'random_forest', 'xgboost', 'lightgbm', or 'ensemble'
        n_estimators: Number of trees/estimators
        max_depth: Maximum depth of trees
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.svm import SVC
        from sklearn.ensemble import VotingClassifier
        
        self.model_type = model_type
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        
        if model_type == 'xgboost' and XGBOOST_AVAILABLE and XGBClassifier is not None:
            self.model = XGBClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=0.1,
                random_state=42,
                use_label_encoder=False,
                eval_metric='logloss'
            )
        elif model_type == 'lightgbm' and LIGHTGBM_AVAILABLE and LGBMClassifier is not None:
            self.model = LGBMClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=0.1,
                random_state=42,
                verbose=-1
            )
        elif model_type == 'ensemble':
            # Ensemble: RF + Logistic Regression + SVC with soft voting
            rf = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=42)
            lr = LogisticRegression(max_iter=1000, random_state=42)
            svc = SVC(probability=True, random_state=42)
            self.model = VotingClassifier(
                estimators=[('rf', rf), ('lr', lr), ('svc', svc)],
                voting='soft'
            )
        else:
            self.model = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=42)
        self.feature_cols = []

    def fetch_fear_and_greed(self, limit: int = 500) -> pd.DataFrame:
        """
        Fetch historical Fear & Greed Index data.
        Returns DataFrame with columns: date, fng_value
        """
        import requests
        from datetime import datetime
        
        try:
            url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            records = []
            for item in data['data']:
                dt = datetime.fromtimestamp(int(item['timestamp']))
                records.append({
                    'date': dt.date(),
                    'FNG': int(item['value'])
                })
            
            df_fng = pd.DataFrame(records)
            return df_fng
        except Exception as e:
            print(f"Warning: Failed to fetch FNG data: {e}")
            return pd.DataFrame()

    def prepare_features(self, df: pd.DataFrame, include_fng: bool = True) -> pd.DataFrame:
        """
        Generate technical indicators as features for the ML model.
        """
        df = df.copy()
        
        # 1. Trend Indicators
        df['RSI'] = talib.RSI(df['close'], timeperiod=14)
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        df['ADX'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
        df['EMA_50'] = talib.EMA(df['close'], timeperiod=50)
        df['EMA_200'] = talib.EMA(df['close'], timeperiod=200)
        
        # Distance from EMAs (Normalized)
        df['Dist_EMA_50'] = (df['close'] - df['EMA_50']) / df['EMA_50']
        df['Dist_EMA_200'] = (df['close'] - df['EMA_200']) / df['EMA_200']

        # 2. Volatility Indicators
        df['ATR'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
        df['ATR_Pct'] = df['ATR'] / df['close']
        df['BB_Upper'], df['BB_Middle'], df['BB_Lower'] = talib.BBANDS(df['close'], timeperiod=20)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']

        # 3. Momentum Indicators
        df['ROC'] = talib.ROC(df['close'], timeperiod=10)
        df['MOM'] = talib.MOM(df['close'], timeperiod=10)
        
        # 4. Volume Indicators
        df['Volume_SMA'] = talib.SMA(df['volume'], timeperiod=20)
        df['Volume_Ratio'] = df['volume'] / df['Volume_SMA']

        # 5. Lagged Returns (Autoregression)
        df['Ret_1'] = df['close'].pct_change(1)
        df['Ret_4'] = df['close'].pct_change(4)

        # 6. Fear & Greed Index (Sentiment Proxy)
        if include_fng:
            df['date'] = df['timestamp'].dt.date
            df_fng = self.fetch_fear_and_greed(limit=500)
            if not df_fng.empty:
                df = df.merge(df_fng, on='date', how='left')
                df['FNG'] = df['FNG'].ffill().bfill()  # Forward/backward fill missing days
            else:
                df['FNG'] = 50  # Neutral default if fetch fails
            df.drop(columns=['date'], inplace=True)
        else:
            df['FNG'] = 50

        # Drop NaNs created by indicators
        df.dropna(inplace=True)

        # 7. NEW: Additional Derived Features for better prediction
        # Price Volatility (rolling std of returns)
        df['Price_Volatility'] = df['close'].pct_change().rolling(window=20).std()
        
        # High-Low Range normalized by close
        df['HL_Range'] = (df['high'] - df['low']) / df['close']
        
        # Lagged returns (more lags for pattern recognition)
        df['Ret_8'] = df['close'].pct_change(8)
        df['Ret_12'] = df['close'].pct_change(12)
        
        # Volume trend (volume change)
        df['Volume_Change'] = df['volume'].pct_change()
        
        # Drop NaNs from new features
        df.dropna(inplace=True)

        # Define Feature Columns (expanded)
        self.feature_cols = [
            'RSI', 'MACD', 'MACD_Hist', 'ADX', 
            'Dist_EMA_50', 'Dist_EMA_200',
            'ATR_Pct', 'BB_Width',
            'ROC', 'MOM',
            'Volume_Ratio', 'Volume_Change',
            'Ret_1', 'Ret_4', 'Ret_8', 'Ret_12',
            'Price_Volatility', 'HL_Range',
            'FNG'  # Fear & Greed Index
        ]
        
        return df

    def prepare_labels(self, df: pd.DataFrame, horizon: int = 4, threshold: float = 0.0) -> pd.DataFrame:
        """
        Generate target labels.
        Target: 1 if Future Return (t+horizon) > threshold, else 0.
        """
        df['Future_Ret'] = df['close'].shift(-horizon) / df['close'] - 1
        df['Target'] = (df['Future_Ret'] > threshold).astype(int)
        
        # Drop last 'horizon' rows where Future_Ret is NaN
        df.dropna(subset=['Future_Ret'], inplace=True)
        return df

    def _get_feature_importances(self, model):
        """Helper to safely extract feature importances."""
        if hasattr(model, 'feature_importances_'):
            return model.feature_importances_
        elif hasattr(model, 'named_estimators_') and 'rf' in model.named_estimators_:
            # For Ensemble, use Random Forest importances as proxy
            return model.named_estimators_['rf'].feature_importances_
        elif hasattr(model, 'estimators_'):
             # Fallback for VotingClassifier if named_estimators_ not available
             for estimator in model.estimators_:
                 if hasattr(estimator, 'feature_importances_'):
                     return estimator.feature_importances_
        return np.zeros(len(self.feature_cols))

    def train_model(self, df: pd.DataFrame, split_ratio: float = 0.8):
        """
        Train the Random Forest model.
        """
        # Split Data
        # Clean Data (Fix for Streamlit Cloud: "Input X contains infinity")
        # Replace infinity with nan
        df[self.feature_cols] = df[self.feature_cols].replace([np.inf, -np.inf], np.nan)
        # Drop rows with any NaNs in features
        df.dropna(subset=self.feature_cols, inplace=True)

        # Split Data (Re-calculate split after dropping NaNs)
        split_idx = int(len(df) * split_ratio)
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]

        X_train = train_df[self.feature_cols]
        y_train = train_df['Target']
        
        X_test = test_df[self.feature_cols]
        y_test = test_df['Target']

        # Train
        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)[:, 1]
        
        metrics = {
            "Accuracy": accuracy_score(y_test, y_pred),
            "Precision": precision_score(y_test, y_pred),
            "Recall": recall_score(y_test, y_pred),
            "Report": classification_report(y_test, y_pred, output_dict=True)
        }
        
        # Feature Importance
        importances = self._get_feature_importances(self.model)
        feature_imp = pd.DataFrame({'Feature': self.feature_cols, 'Importance': importances})
        feature_imp = feature_imp.sort_values(by='Importance', ascending=False)

        return metrics, feature_imp, test_df, y_prob

    def walk_forward_train(self, df: pd.DataFrame, n_splits: int = 5, train_ratio: float = 0.7):
        """
        Walk-Forward Validation: Rolling window training and testing.
        
        Example with n_splits=5:
        - Split 1: Train [0-70%], Test [70-76%]
        - Split 2: Train [6-76%], Test [76-82%]
        - ... and so on
        
        Returns: aggregated metrics, feature_imp, combined test_df, combined y_prob
        """
        total_len = len(df)
        test_size = int(total_len * (1 - train_ratio) / n_splits)  # Each test window
        
        all_preds = []
        all_probs = []
        all_actuals = []
        all_test_dfs = []
        all_importances = []
        
        for i in range(n_splits):
            # Calculate window indices
            test_start = int(total_len * train_ratio) + i * test_size
            test_end = min(test_start + test_size, total_len)
            train_end = test_start
            
            if test_end > total_len or train_end <= 0:
                break
                
            train_df = df.iloc[:train_end]
            test_df = df.iloc[test_start:test_end].copy()
            
            if len(train_df) < 100 or len(test_df) < 10:
                continue
            
            X_train = train_df[self.feature_cols]
            y_train = train_df['Target']
            X_test = test_df[self.feature_cols]
            y_test = test_df['Target']
            
            # Train fresh model for each window (using stored hyperparameters)
            if self.model_type == 'xgboost' and XGBOOST_AVAILABLE and XGBClassifier is not None:
                model = XGBClassifier(n_estimators=self.n_estimators, max_depth=self.max_depth, learning_rate=0.1, random_state=42, use_label_encoder=False, eval_metric='logloss')
            elif self.model_type == 'lightgbm' and LIGHTGBM_AVAILABLE and LGBMClassifier is not None:
                model = LGBMClassifier(n_estimators=self.n_estimators, max_depth=self.max_depth, learning_rate=0.1, random_state=42, verbose=-1)
            elif self.model_type == 'ensemble':
                from sklearn.linear_model import LogisticRegression
                from sklearn.svm import SVC
                from sklearn.ensemble import VotingClassifier
                rf = RandomForestClassifier(n_estimators=self.n_estimators, max_depth=self.max_depth, random_state=42)
                lr = LogisticRegression(max_iter=1000, random_state=42)
                svc = SVC(probability=True, random_state=42)
                model = VotingClassifier(estimators=[('rf', rf), ('lr', lr), ('svc', svc)], voting='soft')
            else:
                model = RandomForestClassifier(n_estimators=self.n_estimators, max_depth=self.max_depth, random_state=42)
            
            model.fit(X_train, y_train)
            
            y_pred = model.predict(X_test)
            y_prob = model.predict_proba(X_test)[:, 1]
            
            all_preds.extend(y_pred)
            all_probs.extend(y_prob)
            all_actuals.extend(y_test.values)
            all_test_dfs.append(test_df)
            all_importances.append(self._get_feature_importances(model))
        
        # Combine results
        combined_test_df = pd.concat(all_test_dfs, ignore_index=True)
        combined_probs = np.array(all_probs)
        
        # Aggregated metrics
        metrics = {
            "Accuracy": accuracy_score(all_actuals, all_preds),
            "Precision": precision_score(all_actuals, all_preds, zero_division=0),
            "Recall": recall_score(all_actuals, all_preds, zero_division=0),
            "Report": classification_report(all_actuals, all_preds, output_dict=True, zero_division=0),
            "n_splits": n_splits,
            "windows_used": len(all_test_dfs)
        }
        
        # Average feature importance across all windows
        avg_importance = np.mean(all_importances, axis=0)
        feature_imp = pd.DataFrame({'Feature': self.feature_cols, 'Importance': avg_importance})
        feature_imp = feature_imp.sort_values(by='Importance', ascending=False)
        
        return metrics, feature_imp, combined_test_df, combined_probs

    def run_backtest(self, df: pd.DataFrame, y_prob: np.ndarray, long_threshold: float = 0.55, short_threshold: float = 0.45, initial_capital: float = 1000.0) -> pd.DataFrame:
        """
        Simulate trading based on AI probability.
        Long if prob > long_threshold, Short if prob < short_threshold.
        Returns (df with Equity, backtest_metrics dict)
        """
        df = df.copy()
        df['AI_Prob'] = y_prob
        
        # Generate Signals: 1 = Long, -1 = Short, 0 = Hold
        df['Signal'] = 0
        df.loc[df['AI_Prob'] > long_threshold, 'Signal'] = 1
        df.loc[df['AI_Prob'] < short_threshold, 'Signal'] = -1
        
        # Loop Backtest
        capital = initial_capital
        equity = []
        position = 0  # 0: None, 1: Long, -1: Short
        entry_price = 0
        horizon = 4  # Assumed from label generation
        exit_idx = -1
        
        # Trade tracking for win rate
        trades = []  # List of (direction, return)
        
        for i in range(len(df)):
            # Check for exit
            if position != 0 and i == exit_idx:
                exit_price = df['close'].iloc[i]
                if position == 1:  # Long
                    ret = (exit_price - entry_price) / entry_price
                else:  # Short
                    ret = (entry_price - exit_price) / entry_price
                capital *= (1 + ret)
                trades.append((position, ret))
                position = 0
            
            # Check for entry
            if position == 0 and i < len(df) - horizon:
                signal = df['Signal'].iloc[i]
                if signal == 1:  # Long
                    position = 1
                    entry_price = df['close'].iloc[i]
                    exit_idx = i + horizon
                elif signal == -1:  # Short
                    position = -1
                    entry_price = df['close'].iloc[i]
                    exit_idx = i + horizon
            
            equity.append(capital)
            
        df['Equity'] = equity
        
        # Calculate Metrics
        equity_series = pd.Series(equity)
        returns = equity_series.pct_change().dropna()
        
        # 1. Total Return
        total_return = (equity[-1] - initial_capital) / initial_capital * 100
        
        # 2. Max Drawdown
        peak = equity_series.cummax()
        drawdown = (equity_series - peak) / peak
        max_drawdown = drawdown.min() * 100
        
        # 3. Sharpe Ratio (Annualized, assuming hourly data)
        if len(returns) > 0 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(365 * 24)  # Annualized
        else:
            sharpe_ratio = 0.0
        
        # 4. Win Rate
        if len(trades) > 0:
            wins = sum(1 for d, r in trades if r > 0)
            win_rate = wins / len(trades) * 100
            
            # Separate Long/Short win rates
            long_trades = [(d, r) for d, r in trades if d == 1]
            short_trades = [(d, r) for d, r in trades if d == -1]
            
            long_win_rate = sum(1 for d, r in long_trades if r > 0) / len(long_trades) * 100 if long_trades else 0
            short_win_rate = sum(1 for d, r in short_trades if r > 0) / len(short_trades) * 100 if short_trades else 0
        else:
            win_rate = 0
            long_win_rate = 0
            short_win_rate = 0
        
        backtest_metrics = {
            'total_return': round(total_return, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'total_trades': len(trades),
            'win_rate': round(win_rate, 2),
            'long_trades': len([t for t in trades if t[0] == 1]),
            'short_trades': len([t for t in trades if t[0] == -1]),
            'long_win_rate': round(long_win_rate, 2),
            'short_win_rate': round(short_win_rate, 2)
        }
        
        return df, backtest_metrics

