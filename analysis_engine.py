import os
import json
import time
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import ccxt
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1. Load Keys & Configure Gemini
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ Error: GEMINI_API_KEY not found in .env file!")
    exit()

try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    print(f"❌ Error initializing client: {e}")
    exit()

class MoonshotAnalyzer:
    def __init__(self):
        print("⚙️ Initializing Analysis Engine...")
        # We use Binance for Crypto data (Largest volume)
        self.exchange = ccxt.binance()
        
    def get_gemini_sentiment(self, ticker, asset_type):
        """
        Uses Gemini to search X (Twitter) & Reddit for 'Vibe Checks'.
        Returns: Score (0-100) and a short summary.
        """
        print(f"🤖 Gemini is checking social sentiment for {ticker}...")
        
        # We target social media specifically in the search query
        search_query = f"${ticker} {asset_type} sentiment discussion site:x.com OR site:reddit.com"
        
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )

        prompt = f"""
        Act as a Social Sentiment Analyst.
        
        Step 1: Search for real-time discussions about {ticker} ({asset_type}) on X (Twitter) and Reddit.
        Step 2: Analyze the "Vibe":
           - Are people HYPE/BULLISH? (High Score 80-100)
           - Are people ANGRY/BEARISH? (Low Score 0-20)
           - Is it dead silence? (Mid Score 40-60)
        
        Step 3: Output a JSON block with a score (0-100) and a very short reason.
        
        CRITICAL: Return ONLY valid JSON.
        
        Example:
        ```json
        {{ "score": 85, "reason": "Trending on X with new partnership rumors" }}
        ```
        """
        
        try:
            # We use the search tool to let Gemini read the live internet
            response = client.models.generate_content(
                model="models/gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[grounding_tool],
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="BLOCK_NONE"
                        ),
                    ]
                )
            )

            # Clean JSON
            if not response.text: return 50, "No Sentiment Data"
            clean_text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_text)
            return data['score'], data['reason']

        except Exception as e:
            print(f"⚠️ Sentiment Check Failed: {e}")
            return 50, "Neutral (AI Error)"

    def analyze_stock(self, ticker):
        """
        3-Layer Analysis for Stocks
        """
        print(f"🔍 Analyzing Stock: {ticker}...")
        score = 0
        report = {"ticker": ticker, "type": "Stock"}

        try:
            # 1. TECHNICAL ANALYSIS (RSI)
            # multi_level_index=False fixes a common yfinance bug
            df = yf.download(ticker, period="6mo", interval="1d", progress=False, multi_level_index=False)
            if df.empty: return None
            
            df.ta.rsi(length=14, append=True)
            current_rsi = df['RSI_14'].iloc[-1]
            current_price = df['Close'].iloc[-1]
            report['price'] = current_price
            
            # Logic: We want breakout momentum (50-70) or Oversold bounce (<35)
            if 50 < current_rsi < 70:
                score += 30
                report['technical'] = f"Healthy Momentum (RSI: {current_rsi:.2f})"
            elif current_rsi < 35:
                score += 40 
                report['technical'] = f"Oversold Bounce (RSI: {current_rsi:.2f})"
            else:
                report['technical'] = f"Neutral/Overheated (RSI: {current_rsi:.2f})"

            # 2. FUNDAMENTAL (Market Cap Check)
            stock = yf.Ticker(ticker)
            mkt_cap = stock.info.get('marketCap', 0)
            
            # Moonshot Zone: $300M - $20B
            if 300_000_000 < mkt_cap < 20_000_000_000: 
                score += 20
                report['fundamental'] = "Moonshot Cap Size"
            else:
                report['fundamental'] = "Cap Size Warning"

            # 3. SENTIMENT (Gemini AI)
            sent_score, sent_reason = self.get_gemini_sentiment(ticker, "Stock")
            
            # Weighted: Sentiment is 50% of a Moonshot score
            score += (sent_score * 0.5) 
            report['sentiment'] = f"{sent_reason} ({sent_score}/100)"
            report['moonshot_score'] = int(score)
            
            return report

        except Exception as e:
            print(f"❌ Stock Analysis Failed: {e}")
            return None

    def analyze_crypto(self, ticker):
        """
        3-Layer Analysis for Crypto
        """
        print(f"🔍 Analyzing Crypto: {ticker}...")
        score = 0
        report = {"ticker": ticker, "type": "Crypto"}
        symbol = f"{ticker.upper()}/USDT"

        try:
            # 1. TECHNICAL
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1d', limit=50)
            if not ohlcv: 
                print(f"⚠️ Could not fetch data for {symbol} on Binance.")
                return None
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.ta.rsi(length=14, append=True)
            current_rsi = df['RSI_14'].iloc[-1]
            report['price'] = df['close'].iloc[-1]
            
            if 45 < current_rsi < 65:
                score += 30
                report['technical'] = f"Strong Trend (RSI: {current_rsi:.2f})"
            elif current_rsi <= 40:
                score += 40
                report['technical'] = f"Buy Zone (RSI: {current_rsi:.2f})"
            else:
                report['technical'] = f"Risky (RSI: {current_rsi:.2f})"

            # 2. FUNDAMENTAL (Volume Check)
            daily_vol = (df['volume'] * df['close']).mean()
            if daily_vol > 5_000_000:
                score += 20
                report['fundamental'] = "High Liquidity"
            else:
                report['fundamental'] = "Low Liquidity Warning"

            # 3. SENTIMENT (Gemini AI)
            # Add "Token" to help Gemini find the crypto, not a generic word
            sent_score, sent_reason = self.get_gemini_sentiment(ticker, "Crypto Token")
            
            # Crypto is 60% Sentiment driven
            score += (sent_score * 0.6)
            
            # Cap score at 99
            final_score = min(int(score), 99)
            report['sentiment'] = f"{sent_reason} ({sent_score}/100)"
            report['moonshot_score'] = final_score
            
            return report

        except Exception as e:
            print(f"❌ Crypto Error ({symbol}): {e}")
            return None

# Test the Engine
if __name__ == "__main__":
    analyzer = MoonshotAnalyzer()
    
    # Test 1: Stock (Space Stock)
    print("\n--- TEST 1: STOCK (RKLB) ---")
    result = analyzer.analyze_stock("RKLB") # Rocket Lab
    if result: print(json.dumps(result, indent=2))
    
    print("-" * 30)
    
    # Test 2: Crypto (AI Token)
    print("\n--- TEST 2: CRYPTO (FET) ---")
    result = analyzer.analyze_crypto("FET") # Fetch.ai
    if result: print(json.dumps(result, indent=2))