import asyncio
import json
import websockets
import time

import ssl

async def test_liquidation_stream():
    uri = "wss://fstream.binance.com/ws/btcusdt@forceOrder"
    print(f"Connecting to {uri}...")
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        async with websockets.connect(uri, ssl=ssl_context) as websocket:
            print("Connected! Listening for 10 seconds...")
            start_time = time.time()
            
            while time.time() - start_time < 10:
                try:
                    # Set a short timeout for receive to allow loop to check time
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    print(f"Liquidation Event: {data}")
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"Error receiving: {e}")
                    break
            
            print("Finished listening.")
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_liquidation_stream())
