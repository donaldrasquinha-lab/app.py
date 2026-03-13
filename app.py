import upstox_client
from upstox_client.feeder import MarketDataStreamerV3

# Configuration
configuration = upstox_client.Configuration()
configuration.access_token = "YOUR_ACCESS_TOKEN"
api_client = upstox_client.ApiClient(configuration)

# Define symbols and use 'ltpc' mode for only the spot price
instrument_keys = ["NSE_INDEX|Nifty 50", "BSE_INDEX|SENSEX"]
mode = "ltpc"

def on_message(message):
    # Process the live tick
    print(f"Live Feed Data: {message}")

# Initialize and connect
streamer = MarketDataStreamerV3(api_client, instrument_keys, mode)
streamer.on("message", on_message)
streamer.connect()
