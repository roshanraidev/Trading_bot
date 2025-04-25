import streamlit as st
import pandas as pd
import time
import pandas_ta as ta
import matplotlib.pyplot as plt
from binance.client import Client
from binance.enums import *
from datetime import datetime
import threading

# API Key and Secret - make sure they have restricted permissions
API_KEY = 'xLGKkXgRHEdJVpKlIi08iMUMHuhBNIj99e3f3ibQRAcQMTRizbE1GVtiX0QoUbgk'
API_SECRET = 'OaOsVaSTrpOxslhnPLB8DDAfS0aufRBqG6LGS22F5MkA9WaeacmqQL00MtVC5Kke'

client = Client(API_KEY, API_SECRET)


# ⚠️ FOR TESTNET:
# client.API_URL = 'https://testnet.binance.vision/api'

# ---------- STREAMLIT UI ---------- #
st.set_page_config("Real-Time Crypto Trading", layout="wide")
st.title("📈 Live Binance Crypto Trading Dashboard")

# Sidebar inputs
symbol = st.sidebar.text_input("Trading Pair (e.g., BTCUSDT)", "BTCUSDT")
interval = st.sidebar.selectbox("Interval", ["1m", "5m", "15m", "1h", "4h", "1d"])
initial_capital = st.sidebar.number_input("Initial USD Capital", 100, 100000, 1000)
refresh_now = st.sidebar.button("🔄 Refresh Now")
run_trading = st.sidebar.checkbox("✅ Run Strategy")

# ---------- SESSION STATE ---------- #
if "positions" not in st.session_state:
    st.session_state.positions = []
if "pnl" not in st.session_state:
    st.session_state.pnl = 0.0

# ---------- FETCH DATA ---------- #
def fetch_data(symbol, interval):
    try:
        raw = client.get_klines(symbol=symbol, interval=interval, limit=150)
        df = pd.DataFrame(raw, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

# ---------- INDICATORS ---------- #
def add_indicators(df):
    df['rsi'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df['macd'] = macd['MACD_12_26_9']
    df['macd_signal'] = macd['MACDs_12_26_9']
    return df

# ---------- PLACE ORDER ---------- #
def place_order(side, quantity, price):
    try:
        order = client.order_market(
            symbol=symbol,
            side=side,
            quantity=round(quantity, 6)  # Adjust precision based on coin
        )
        status = "✅ Success"
    except Exception as e:
        st.error(f"Order Error: {e}")
        status = "❌ Failed"

    # Log trade
    pnl = None
    if side == SIDE_SELL and st.session_state.positions:
        last_buy = next((x for x in reversed(st.session_state.positions) if x["action"] == SIDE_BUY), None)
        if last_buy:
            pnl = (price - last_buy['price']) * quantity
            st.session_state.pnl += pnl

    st.session_state.positions.append({
        "time": datetime.now(),
        "action": side,
        "quantity": quantity,
        "price": price,
        "pnl": pnl,
        "status": status
    })

# ---------- STRATEGY ---------- #
def trading_strategy(df):
    latest = df.iloc[-1]
    price = latest['close']
    rsi = latest['rsi']
    macd = latest['macd']
    signal = latest['macd_signal']

    if pd.notna(rsi) and pd.notna(macd) and pd.notna(signal):
        qty = available_balance / price  # Use real-time available balance

        if rsi < 30 and macd > signal:
            place_order(SIDE_BUY, qty, price)
            st.success(f"📥 BUY: {qty:.6f} @ {price:.2f}")
        elif rsi > 70 and macd < signal:
            place_order(SIDE_SELL, qty, price)
            st.warning(f"📤 SELL: {qty:.6f} @ {price:.2f}")

# ---------- GET REAL BALANCE ---------- #
def get_available_balance(asset="USDT"):
    try:
        account_info = client.get_asset_balance(asset=asset)
        balance = float(account_info['free'])
        return balance
    except Exception as e:
        st.error(f"Balance fetch error: {e}")
        return 0.0

# ---------- PLOT CHART ---------- #
def plot_chart(df):
    fig, axs = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    axs[0].plot(df.index, df['close'], label='Price', color='black')
    axs[0].set_ylabel("Price")
    axs[0].legend()

    axs[1].plot(df.index, df['rsi'], label='RSI', color='blue')
    axs[1].axhline(70, color='red', linestyle='--')
    axs[1].axhline(30, color='green', linestyle='--')
    axs[1].set_ylabel("RSI")
    axs[1].legend()

    axs[2].plot(df.index, df['macd'], label='MACD', color='purple')
    axs[2].plot(df.index, df['macd_signal'], label='Signal', color='orange')
    axs[2].set_ylabel("MACD")
    axs[2].legend()

    plt.tight_layout()
    st.pyplot(fig)

# ---------- MAIN LOOP ---------- #
df = fetch_data(symbol, interval)
if df is not None:
    df = add_indicators(df)

    # Get real-time available balance
    available_balance = get_available_balance("USDT")  # or any other base asset

    # Metrics
    price = df['close'].iloc[-1]
    rsi = df['rsi'].iloc[-1]
    macd = df['macd'].iloc[-1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Available Capital", f"${available_balance:,.2f}")
    col2.metric("Current Price", f"${price:,.2f}")
    col3.metric("RSI", f"{rsi:.2f}")
    col4.metric("P/L", f"${st.session_state.pnl:.2f}")

    # Strategy
    if run_trading:
        trading_strategy(df)

    # Chart
    plot_chart(df)

    # Trade Log
    if st.session_state.positions:
        st.subheader("📜 Trade History")
        st.dataframe(pd.DataFrame(st.session_state.positions))

    # Auto-refresh every 60 sec
    if run_trading:
        time.sleep(60)
        st.rerun()
