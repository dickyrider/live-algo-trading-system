"""
Backpack Exchange Production Trading Template (Public Version)
================================================================
Author        : Your Name (GitHub: dickyrider)
Updated       : 2025-11-20
Description   : Complete production-ready template for Backpack Exchange perpetual trading
                • Full ed25519 signature implementation
                • Account / position / order management
                • Telegram alerts (disabled in public version)
                • Live strategy logic REMOVED for security
                
2025 YTD Live Performance (private bot): +XX% | Sharpe X.X | Max DD -XX%
Full version + equity curve available during technical interviews.
"""

import pandas as pd
import requests
import time
import base64
from nacl.signing import SigningKey
from datetime import datetime, timezone, timedelta

# ================== CONFIG (Fill your own in private version) ==================
API_KEY = "YOUR_API_KEY_HERE"
API_SECRET = "YOUR_API_SECRET_HERE" 
BASE_URL = "https://api.backpack.exchange"

# Telegram disabled in public version
def send_notification(message: str):
    """Replace with Telegram/Discord/Slack in your private bot"""
    print(f"[NOTIFICATION] {message}")

# ================== ED25519 SIGNATURE (The most complete public version in 2025) ==================
def get_signature_ed25519(instruction: str, timestamp: str, window: int = 5000, params: dict = None) -> str:
    def to_sign_value(val):
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, float):
            s = f"{val:.3f}"
            s = s.rstrip('0').rstrip('.') if '.' in s else s
            return s
        return str(val)

    sign_str = f"instruction={instruction}"
    if params:
        param_str = '&'.join(f"{k}={to_sign_value(params[k])}" for k in sorted(params))
        sign_str += f"&{param_str}"
    sign_str += f"&timestamp={timestamp}&window={window}"

    private_key = SigningKey(base64.b64decode(API_SECRET))
    signature = private_key.sign(sign_str.encode())
    return base64.b64encode(signature.signature).decode()

# ================== ACCOUNT INFO (Balance + Position + Max Qty) ==================
def get_account_info(symbol: str = "ETH_USDC_PERP", side: str = "Bid") -> dict:
    timestamp = str(int(time.time() * 1000))
    window = 5000

    # 1. Balance
    bal_sig = get_signature_ed25519("balanceQuery", timestamp, window)
    bal_headers = {"X-API-KEY": API_KEY, "X-SIGNATURE": bal_sig, "X-TIMESTAMP": timestamp, "X-WINDOW": str(window), "Content-Type": "application/json"}
    bal_resp = requests.get(f"{BASE_URL}/api/v1/capital", headers=bal_headers)
    cash = 0.0
    if bal_resp.status_code == 200:
        asset = bal_resp.json().get("USDC", {})
        cash = float(asset.get("available", 0))

    # 2. Position
    pos_sig = get_signature_ed25519("positionQuery", timestamp, window)
    pos_headers = {**bal_headers, "X-SIGNATURE": pos_sig}
    pos_resp = requests.get(f"{BASE_URL}/api/v1/position", headers=pos_headers)
    position = avg_entry = 0.0
    if pos_resp.status_code == 200:
        for p in pos_resp.json():
            if p["symbol"] == symbol and float(p["netQuantity"]) != 0:
                position = float(p["netQuantity"])
                avg_entry = float(p["entryPrice"])

    # 3. Max Order Quantity
    params = {"side": side.capitalize(), "symbol": symbol}
    limit_sig = get_signature_ed25519("maxOrderQuantity", timestamp, window, params)
    limit_headers = {**bal_headers, "X-SIGNATURE": limit_sig}
    max_qty = None
    limit_resp = requests.get(f"{BASE_URL}/api/v1/account/limits/order", params=params, headers=limit_headers)
    if limit_resp.status_code == 200:
        max_qty = float(limit_resp.json().get("maxOrderQuantity", 0))

    return {
        "cash": cash,
        "position": position,
        "avg_entry_price": avg_entry,
        "max_order_qty": max_qty
    }

# ================== DUMMY DATA LOADER (Replace with your pipeline) ==================
def load_data() -> pd.DataFrame:
    """In real bot: load your 1h + 4h + Coinglass merged CSV"""
    # Example dummy data with RSI for demo
    df = pd.DataFrame({
        "close": [60000, 60500, 61000, 60800, 61200],
        "rsi":   [25,    35,    45,    65,    75]
    })
    return df

# ================== LIVE STRATEGY REMOVED (Dummy example) ==================
def generate_signal(df: pd.DataFrame, account_info: dict) -> dict | None:
    """LIVE STRATEGY INTENTIONALLY REMOVED"""
    rsi = df['rsi'].iloc[-1]

    if rsi < 30 and account_info['position'] <= 0:
        return {"action": "open", "side": "bid", "qty": 0.005, "reason": "RSI oversold"}
    if rsi > 70 and account_info['position'] >= 0:
        return {"action": "open", "side": "ask", "qty": 0.005, "reason": "RSI overbought"}
    if account_info['position'] != 0:
        return {"action": "close", "side": "ask" if account_info['position'] > 0 else "bid",
                "qty": abs(account_info['position']), "reason": "Take profit / risk control"}
    return None

# ================== ORDER EXECUTION ==================
def place_order(signal: dict, symbol: str = "ETH_USDC_PERP"):
    payload = {
        "symbol": symbol,
        "side": signal['side'].capitalize(),
        "orderType": "Market",
        "quantity": round(float(signal['qty']), 4),
        "reduceOnly": signal['action'] == "close"
    }
    timestamp = str(int(time.time() * 1000))
    sig = get_signature_ed25519("orderExecute", timestamp, 5000, payload)
    headers = {
        "X-API-KEY": API_KEY,
        "X-SIGNATURE": sig,
        "X-TIMESTAMP": timestamp,
        "X-WINDOW": "5000",
        "Content-Type": "application/json"
    }
    resp = requests.post(f"{BASE_URL}/api/v1/order", json=payload, headers=headers)
    result = resp.json() if resp.status_code == 200 else None
    status = "SUCCESS" if result else f"FAILED {resp.text}"
    send_notification(f"ORDER {signal['action'].upper()} {signal['side'].upper()} {signal['qty']} @ MARKET → {status}")
    return result

# ================== MAIN LOOP (Production ready) ==================
def main():
    print("Backpack Trading Template - Public Version Starting...")
    account = get_account_info("ETH_USDC_PERP")
    df = load_data()
    signal = generate_signal(df, account)

    if signal:
        place_order(signal, "ETH_USDC_PERP")
    else:
        send_notification("No signal - Monitoring...")

if __name__ == "__main__":
    main()
