import yfinance as yf

# Use '^NSEI' for Nifty 50
nifty = yf.Ticker("^NSEI")

# Get live price data
live_data = nifty.history(period="1d", interval="1m")
current_price = live_data['Close'].iloc[-1]

print(f"Current Nifty 50 Price: {current_price}")
