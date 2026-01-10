import asyncio
import json
import threading
import time
from collections import deque
import websockets
import ssl

class LiquidationMonitor:
    def __init__(self):
        self.active_symbol = None
        self.running = False
        self.thread = None
        self.loop = None
        self.liquidations = deque(maxlen=2000) # Store last 2000 events
        self.start_time = None
        self.lock = threading.Lock()

    def start(self, symbol: str):
        symbol = symbol.lower().replace('/', '')
        if '/' not in symbol and not symbol.endswith('usdt'):
             symbol = f"{symbol}usdt"
        
        # If already running for same symbol, do nothing
        if self.running and self.active_symbol == symbol:
            return
            
        # If running for different symbol, stop first
        if self.running:
            self.stop()
            
        self.active_symbol = symbol
        self.running = True
        self.start_time = time.time()
        self.liquidations.clear()
        
        # Start background thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        # We can't easily stop the loop from outside, but the loop checks self.running
        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.1)
            
    def _run_loop(self):
        # Create a new loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._listen())
        loop.close()
        
    async def _listen(self):
        uri = f"wss://fstream.binance.com/ws/{self.active_symbol}@forceOrder"
        
        # SSL Context to avoid cert errors
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        while self.running:
            try:
                async with websockets.connect(uri, ssl=ssl_context) as websocket:
                    while self.running:
                        try:
                            # Use wait_for to allow checking self.running periodically
                            msg = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            data = json.loads(msg)
                            self._process_message(data)
                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            # print(f"WS Error: {e}")
                            break
            except Exception as e:
                # print(f"Connection Error: {e}")
                await asyncio.sleep(5) # Retry delay

    def _process_message(self, data):
        # Format: {"e":"forceOrder", "o": { ... }}
        if data.get('e') == 'forceOrder':
            order = data['o']
            event = {
                "time": data['E'], # Event time
                "side": order['S'], # SELL (Long Liq) or BUY (Short Liq)
                "qty": float(order['q']),
                "price": float(order['p']),
                "amount": float(order['q']) * float(order['p'])
            }
            with self.lock:
                self.liquidations.append(event)

    def get_stats(self):
        with self.lock:
            if not self.liquidations:
                return {
                    "count": 0, 
                    "vol": 0, 
                    "long_vol": 0, 
                    "short_vol": 0, 
                    "duration": time.time() - (self.start_time or time.time()),
                    "start_time": self.start_time
                }
            
            now = time.time()
            duration = now - self.start_time
            
            total_vol = 0
            long_vol = 0
            short_vol = 0
            long_count = 0
            short_count = 0
            
            for liq in self.liquidations:
                total_vol += liq['amount']
                if liq['side'] == 'SELL':
                    long_vol += liq['amount']
                    long_count += 1
                else:
                    short_vol += liq['amount']
                    short_count += 1
                    
            return {
                "count": len(self.liquidations),
                "long_count": long_count,
                "short_count": short_count,
                "vol": total_vol,
                "long_vol": long_vol,
                "short_vol": short_vol,
                "duration": duration,
                "start_time": self.start_time
            }
