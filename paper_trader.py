import sqlite3

class PaperTrader:
    def __init__(self, db_name="paper_portfolio.db", initial_cash=10000.0):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db(initial_cash)

    def _init_db(self, initial_cash):
        # Create Tables
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS wallet (balance REAL)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS positions (ticker TEXT PRIMARY KEY, amount REAL, avg_cost REAL)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                            (id INTEGER PRIMARY KEY, ticker TEXT, type TEXT, target_price REAL, amount REAL, status TEXT)''')
        self.conn.commit()

        # Set initial cash if empty
        self.cursor.execute("SELECT count(*) FROM wallet")
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute("INSERT INTO wallet VALUES (?)", (initial_cash,))
            self.conn.commit()

    def get_balance(self):
        self.cursor.execute("SELECT balance FROM wallet")
        return self.cursor.fetchone()[0]

    def get_holdings(self):
        """Returns list of (ticker, amount, avg_cost)"""
        self.cursor.execute("SELECT ticker, amount, avg_cost FROM positions WHERE amount > 0")
        return self.cursor.fetchall()

    def get_position_exposure(self, ticker):
        """Returns dollar value of a specific position"""
        self.cursor.execute("SELECT amount, avg_cost FROM positions WHERE ticker=?", (ticker,))
        row = self.cursor.fetchone()
        if row:
            return row[0] * row[1]
        return 0.0

    def get_open_orders(self):
        self.cursor.execute("SELECT ticker, type, target_price, amount FROM orders WHERE status='OPEN'")
        return self.cursor.fetchall()

    def execute_trade(self, ticker, action, price, amount_usd):
        balance = self.get_balance()
        
        if action == "BUY":
            if balance < amount_usd: return "❌ Insufficient Funds"
            
            quantity = amount_usd / price
            new_balance = balance - amount_usd
            
            # Update Wallet
            self.cursor.execute("UPDATE wallet SET balance = ?", (new_balance,))
            
            # Update Position
            self.cursor.execute("SELECT amount, avg_cost FROM positions WHERE ticker=?", (ticker,))
            row = self.cursor.fetchone()
            if row:
                current_qty, current_avg = row
                total_cost = (current_qty * current_avg) + amount_usd
                total_qty = current_qty + quantity
                new_avg = total_cost / total_qty
                self.cursor.execute("UPDATE positions SET amount=?, avg_cost=? WHERE ticker=?", (total_qty, new_avg, ticker))
            else:
                self.cursor.execute("INSERT INTO positions VALUES (?, ?, ?)", (ticker, quantity, price))
            
            self.conn.commit()
            return f"✅ **BOUGHT** {quantity:.4f} {ticker} @ ${price:.2f}"

        return "❌ Unknown Action"

    def log_pending_order(self, ticker, order_type, price, amount_usd):
        qty = amount_usd / price if price > 0 else 0
        self.cursor.execute("INSERT INTO orders (ticker, type, target_price, amount, status) VALUES (?, ?, ?, ?, 'OPEN')", 
                           (ticker, order_type, price, qty))
        self.conn.commit()
        return f"⏳ **QUEUED:** {order_type} @ ${price:.2f}"

    def check_pending_orders(self, ticker, current_price):
        """Checks if any Limit/Stop orders should trigger"""
        logs = []
        self.cursor.execute("SELECT id, type, target_price, amount FROM orders WHERE ticker=? AND status='OPEN'", (ticker,))
        orders = self.cursor.fetchall()
        
        for order_id, order_type, target, qty in orders:
            # Limit Buy: Trigger if price drops BELOW target
            if order_type == "LIMIT_BUY" and current_price <= target:
                cost = qty * target
                self.execute_trade(ticker, "BUY", target, cost)
                self.cursor.execute("UPDATE orders SET status='FILLED' WHERE id=?", (order_id,))
                logs.append(f"🔔 **LIMIT FILLED:** {ticker} @ ${target:.2f}")

            # Stop Loss: Trigger if price drops BELOW target
            elif order_type == "STOP_LOSS" and current_price <= target:
                # Sell Logic (Simplified: Close entire position)
                # For this version, we just notify you, as selling logic requires more complex tracking
                self.cursor.execute("UPDATE orders SET status='TRIGGERED' WHERE id=?", (order_id,))
                logs.append(f"🛑 **STOP LOSS HIT:** {ticker} @ ${target:.2f} - CHECK APP!")

    def reset_portfolio(self, initial_cash=10000.0):
        """Wipes all data and resets wallet to initial cash."""
        self.cursor.execute("DELETE FROM positions")
        self.cursor.execute("DELETE FROM orders")
        self.cursor.execute("DELETE FROM wallet")
        self.cursor.execute("INSERT INTO wallet VALUES (?)", (initial_cash,))
        self.conn.commit()
        return f"✅ **RESET COMPLETE**\nAccount reset to ${initial_cash:,.2f}"

    def clear_positions(self):
        """Removes all positions and orders (used after selling all)."""
        self.cursor.execute("DELETE FROM positions")
        self.cursor.execute("DELETE FROM orders")
        self.conn.commit()
    
    def deposit_cash(self, amount):
        """Adds cash to wallet (used from sell_all)."""
        current = self.get_balance()
        new_bal = current + amount
        self.cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))         
        self.conn.commit()
        return logs