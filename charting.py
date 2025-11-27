import yfinance as yf
import mplfinance as mpf
import pandas as pd
import ccxt
import os
import shutil

class ChartGenerator:
    def __init__(self):
        # 1. Create the 'charts' folder if it doesn't exist
        self.chart_dir = "charts"
        if not os.path.exists(self.chart_dir):
            os.makedirs(self.chart_dir)
            print(f"📁 Created directory: {self.chart_dir}")

        self.exchange = ccxt.binance()
        
        # Dark Mode Style
        self.style = mpf.make_mpf_style(
            base_mpf_style='nightclouds', 
            facecolor='#0e1117',
            edgecolor='#0e1117',
            gridcolor='#23262c',
            marketcolors=mpf.make_marketcolors(
                up='#00ff00', down='#ff0000',
                edge='inherit', wick='inherit', volume='in'
            )
        )

    def generate_stock_chart(self, ticker):
        """Generates a chart for stocks"""
        try:
            print(f"🎨 Painting chart for Stock: {ticker}...")
            df = yf.download(ticker, period="3mo", interval="1d", progress=False, multi_level_index=False)
            if df.empty: return None

            # Save to charts/TICKER_chart.png
            filename = os.path.join(self.chart_dir, f"{ticker}_chart.png")
            self._plot_and_save(df, ticker, filename)
            return filename
        except Exception as e:
            print(f"❌ Chart Error ({ticker}): {e}")
            return None

    def generate_crypto_chart(self, ticker):
        """Generates a chart for crypto"""
        try:
            print(f"🎨 Painting chart for Crypto: {ticker}...")
            symbol = f"{ticker.upper()}/USDT"
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1d', limit=90)
            if not ohlcv: return None
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Save to charts/TICKER_crypto.png
            filename = os.path.join(self.chart_dir, f"{ticker}_crypto.png")
            self._plot_and_save(df, symbol, filename)
            return filename
        except Exception as e:
            print(f"❌ Crypto Chart Error: {e}")
            return None

    def _plot_and_save(self, df, title, filename):
        mpf.plot(
            df,
            type='candle',
            style=self.style,
            title=f"\n{title} (Daily)",
            ylabel='Price ($)',
            volume=True,
            mav=(20, 50),
            savefig=dict(fname=filename, dpi=100, bbox_inches='tight'),
            tight_layout=True
        )
        print(f"✅ Saved chart to: {filename}")

    def cleanup_chart(self, filepath):
        """Utility to delete a specific chart after sending"""
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"🧹 Cleaned up: {filepath}")
            except Exception as e:
                print(f"⚠️ Could not delete {filepath}: {e}")

# Test
if __name__ == "__main__":
    artist = ChartGenerator()
    path = artist.generate_stock_chart("NVDA")
    # Verify it exists, then delete it
    if path and os.path.exists(path):
        print("Test Successful. Cleaning up...")
        artist.cleanup_chart(path)