import os
import json
import logging
import asyncio
import yfinance as yf
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, JobQueue

# Import our custom modules
import ai_scout
import analysis_engine
import charting
import paper_trader
from google import genai

# 1. SETUP & CONFIGURATION
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHAT_ID = "YOUR_CHAT_ID_HERE" # OPTIONAL: Set this if you know it, otherwise /start sets it.

# Initialize Systems
trader = paper_trader.PaperTrader(initial_cash=10000.0)
analyzer = analysis_engine.MoonshotAnalyzer()
artist = charting.ChartGenerator()

# Initialize Strategist (Gemini)
client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- STRATEGIST LOGIC (The "Portfolio Manager" AI) ---
def get_ai_strategy(ticker, narrative, analysis_report, current_cash, current_exposure):
    prompt = f"""
    Act as a Hedge Fund Portfolio Manager.
    
    CONTEXT:
    Ticker: {ticker}
    Narrative: "{narrative}"
    Analysis: {analysis_report}
    
    PORTFOLIO:
    Cash Available: ${current_cash:,.2f}
    Current Exposure to {ticker}: ${current_exposure:,.2f}
    
    MISSION:
    Decide allocation based on conviction.
    1. If high score (>80) + Low Exposure -> Aggressive (5-8% of cash).
    2. If mid score (60-80) -> Conservative (2-4% of cash).
    3. Determine split: Spot Buy (Now) vs Limit Buy (Later).
    
    OUTPUT JSON ONLY:
    {{
      "action": "AGGRESSIVE" or "CONSERVATIVE",
      "spot_pct": 5.0, 
      "limit_pct": 3.0,
      "limit_price": 12.50,
      "stop_loss": 10.00,
      "reason": "Strong momentum, buying 5% spot and adding 3% on dip."
    }}
    """
    try:
        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite", 
            contents=prompt
        )
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"Strategy Error: {e}")
        return None

# --- TELEGRAM COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    CHAT_ID = update.effective_chat.id
    await update.message.reply_text(f"🚀 Moonshot Bot Online!\nChat ID set to: {CHAT_ID}\nUse /scan to force a hunt.")

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cash = trader.get_balance()
    holdings = trader.get_holdings()
    msg = f"💼 **PORTFOLIO UPDATE**\n💵 Cash: ${cash:,.2f}\n"
    for ticker, amt, cost in holdings:
        val = amt * cost # Simplified (Real ver would fetch live price)
        msg += f"🔹 {ticker}: ${val:,.2f} (Avg: {cost:.2f})\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def manual_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Force Scan Initiated... This may take a minute.")
    await run_market_scan(context)

# --- COMMAND: /reset ---
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes the portfolio and resets cash to $10,000."""
    msg = trader.reset_portfolio()
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- COMMAND: /sell_all ---
async def cmd_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liquidates ALL holdings at current market prices."""
    await update.message.reply_text("🚨 **PANIC SELL INITIATED...**", parse_mode='Markdown')
    
    holdings = trader.get_holdings()
    if not holdings:
        await update.message.reply_text("💼 Portfolio is already empty.")
        return

    total_liquidation_value = 0.0
    log = ""

    # 1. SEPARATE STOCKS AND CRYPTO
    stocks = [h for h in holdings if "/" not in h[0]]
    cryptos = [h for h in holdings if "/" in h[0]]

    # 2. SELL STOCKS (Bulk Fetch)
    if stocks:
        tickers = [s[0] for s in stocks]
        try:
            # Fetch all prices at once for speed
            data = yf.download(tickers, period="1d", progress=False)['Close'].iloc[-1]
            
            for ticker, qty, avg in stocks:
                # Handle single vs multiple ticker result format
                current_price = data[ticker] if len(tickers) > 1 else data.item()
                val = qty * current_price
                total_liquidation_value += val
                log += f"📉 Sold {ticker}: ${val:,.2f} (@ ${current_price:.2f})\n"
        except Exception as e:
            log += f"⚠️ Error selling stocks: {e}\n"

    # 3. SELL CRYPTO (Loop Fetch)
    # Crypto APIs often dislike bulk formatting, safer to loop for accuracy
    exchange = analyzer.exchange # Re-use the analyzer's connection
    for ticker, qty, avg in cryptos:
        try:
            price = exchange.fetch_ticker(ticker)['last']
            val = qty * price
            total_liquidation_value += val
            log += f"📉 Sold {ticker}: ${val:,.2f} (@ ${price:.2f})\n"
        except Exception as e:
            log += f"⚠️ Error selling {ticker}: {e}\n"

    # 4. UPDATE DATABASE
    trader.deposit_cash(total_liquidation_value)
    trader.clear_positions()
    
    final_balance = trader.get_balance()
    
    msg = f"""
💥 **LIQUIDATION COMPLETE**
──────────────────────
{log}
💰 **Cash Gained:** ${total_liquidation_value:,.2f}
🏦 **New Balance:** ${final_balance:,.2f}
    """
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- COMMAND: /help (Dynamic) ---
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all available commands dynamically."""
    msg = "🤖 **MOONSHOT BOT COMMANDS**\n──────────────────────\n"
    
    # Magic: Look inside the bot to find its own commands
    # We access the bot's application handlers to see what is registered
    handlers = context.application.handlers[0] # Group 0 contains standard commands
    
    for handler in handlers:
        if isinstance(handler, CommandHandler):
            # Get the command name (e.g., 'start')
            command_name = list(handler.commands)[0]
            # Get the docstring (the text inside """ """)
            description = handler.callback.__doc__ or "No description."
            
            msg += f"/{command_name} - {description}\n"
            
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- THE MAIN LOOP (The "Job") ---
async def run_market_scan(context: ContextTypes.DEFAULT_TYPE):
    print("--- 🔄 Starting Market Scan ---")
    
    # 1. SCOUT
    candidates = ai_scout.scan_market()
    if isinstance(candidates, str): 
        print(candidates) # Print error if string
        return

    for item in candidates:
        ticker = item.get('ticker')
        narrative = item.get('narrative')
        asset_type = item.get('type', 'Stock') # Default to Stock if missing
        
        print(f"👉 Checking {ticker} ({asset_type})...")
        
        # 2. ANALYZE & CHART
        chart_file = None # Initialize variable
        if asset_type == 'Crypto':
            report = analyzer.analyze_crypto(ticker)
            if report:
                chart_file = artist.generate_crypto_chart(ticker)
        else:
            report = analyzer.analyze_stock(ticker)
            if report:
                chart_file = artist.generate_stock_chart(ticker)

        if not report: continue

        score = report.get('moonshot_score', 0)
        print(f"📊 Score for {ticker}: {score}/100")

        # 3. FILTER (Only trade if Score > 70)
        if score >= 70:
            # 4. STRATEGY
            cash = trader.get_balance()
            exposure = trader.get_position_exposure(ticker)
            
            strategy = get_ai_strategy(ticker, narrative, str(report), cash, exposure)
            if not strategy: continue
            
            # 5. EXECUTE (Paper Trade)
            trade_log = ""
            current_price = report.get('price', 0)
            
            # Execute Trades (Spot, Limit, Stop)
            if strategy.get('spot_pct', 0) > 0:
                spot_amt = cash * (strategy['spot_pct'] / 100)
                if spot_amt > 10:
                    trade_log += f"{trader.execute_trade(ticker, 'BUY', current_price, spot_amt)}\n"
            
            if strategy.get('limit_pct', 0) > 0:
                limit_amt = cash * (strategy['limit_pct'] / 100)
                if limit_amt > 10:
                    trade_log += f"{trader.log_pending_order(ticker, 'LIMIT_BUY', strategy['limit_price'], limit_amt)}\n"
                
            trader.log_pending_order(ticker, "STOP_LOSS", strategy['stop_loss'], 0)

            # 6. NOTIFY
            # We remove the bolding formatting logic here to prevent crashes
            caption = f"""
🚀 MOONSHOT FOUND: {ticker}
Score: {score}/100
🔥 Narrative: {narrative}

🧠 AI STRATEGY
Action: {strategy['action']}
Reason: {strategy['reason']}

📝 EXECUTED
{trade_log}

🛑 Stop Loss: ${strategy['stop_loss']}
            """
            
            # FIX: Removed parse_mode='Markdown' to prevent crashes from AI symbols
            if CHAT_ID:
                if chart_file and os.path.exists(chart_file):
                    await context.bot.send_photo(chat_id=CHAT_ID, photo=open(chart_file, 'rb'), caption=caption)
                else:
                    await context.bot.send_message(chat_id=CHAT_ID, text=caption)

    print("--- ✅ Scan Complete ---")

# --- LAUNCHER ---
if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN not set in .env")
        exit()
        
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # [Update the add_handler section in main.py]
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", manual_scan))
    app.add_handler(CommandHandler("portfolio", portfolio))
    
    # NEW COMMANDS
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("sell_all", cmd_sell_all))
    
    # OVERWRITE OLD HELP (Place this LAST so it sees all previous commands)
    app.add_handler(CommandHandler("help", cmd_help))
    
    # Schedule Job (Every 4 hours = 14400 seconds)
    job_queue = app.job_queue
    job_queue.run_repeating(run_market_scan, interval=14400, first=10)
    
    print("🤖 Bot is Live! Polling...")
    app.run_polling()