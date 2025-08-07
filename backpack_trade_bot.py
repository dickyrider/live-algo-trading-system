import pandas as pd
import requests
import time
import base64
from nacl.signing import SigningKey
import base64
import nacl.signing 
from datetime import datetime, timezone, timedelta


API_KEY = #api key
API_SECRET = # api secret
BASE_URL =  'https://api.backpack.exchange'

TG_TOKEN = #tg_token
TG_CHAT_ID = #tg_id  # your chat id, number

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {
        "chat_id": TG_CHAT_ID,
        "text": text
    }
    try:
        resp = requests.post(url, data=data)
        if not resp.ok:
            print("Telegram sending failed:", resp.text)
    except Exception as e:
        print("Telegram notification error:", e)

def get_signature_ed25519(instruction, timestamp, window=5000, params=None):
    # Compose signature string according to official rules
    def to_sign_value(val):
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, float):
            # Three decimal places, remove trailing zeros
            s = f"{val:.3f}"
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            return s
        return str(val)
    sign_str = f"instruction={instruction}"
    if params:
        param_str = '&'.join(f"{k}={to_sign_value(params[k])}" for k in sorted(params))
        sign_str += f"&{param_str}"
    sign_str += f"&timestamp={timestamp}&window={window}"
    print("Signature string:", sign_str)  # For debugging, can be used to compare in case of issues
    private_key = nacl.signing.SigningKey(base64.b64decode(API_SECRET))
    signature = private_key.sign(sign_str.encode())
    sig_b64 = base64.b64encode(signature.signature).decode()
    return sig_b64

def get_account_info(symbol="BTC-USDC", side="Bid"):
    # 1. Query available balance and open balance
    bal_path = "/api/v1/capital"
    bal_url = BASE_URL + bal_path
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    window = 5000
    bal_sig = get_signature_ed25519("balanceQuery", timestamp, window)
    headers = {
        "X-API-KEY": API_KEY,
        "X-SIGNATURE": bal_sig,
        "X-TIMESTAMP": timestamp,
        "X-WINDOW": str(window),
        "Content-Type": "application/json"
    }
    resp_bal = requests.get(bal_url, headers=headers)
    if resp_bal.status_code != 200:
        print("Balance API error:", resp_bal.status_code, resp_bal.text)
        return None
    bal_data = resp_bal.json()
    asset_code = symbol.split('-')[1] if '-' in symbol else "USDC"
    usdc_info = bal_data.get(asset_code)
    cash = float(usdc_info["available"]) if usdc_info else 0
    open_balance = (
        float(usdc_info.get("available", 0)) +
        float(usdc_info.get("locked", 0)) +
        float(usdc_info.get("staked", 0))
    ) if usdc_info else 0

    # 2. Query contract positions
    pos_path = "/api/v1/position"
    pos_url = BASE_URL + pos_path
    timestamp2 = str(int(time.time() * 1000))
    pos_sig = get_signature_ed25519("positionQuery", timestamp2, window)
    pos_headers = {
        "X-API-KEY": API_KEY,
        "X-SIGNATURE": pos_sig,
        "X-TIMESTAMP": timestamp2,
        "X-WINDOW": str(window),
        "Content-Type": "application/json"
    }
    resp_pos = requests.get(pos_url, headers=pos_headers)
    if resp_pos.status_code != 200:
        print("Positions API error:", resp_pos.status_code, resp_pos.text)
        return None
    pos_data = resp_pos.json()
    pos_info = None
    for pos in pos_data:
        if pos["symbol"] == symbol and float(pos["netQuantity"]) != 0:
            position = float(pos["netQuantity"])
            avg_entry_price = float(pos["entryPrice"])
            side_pos = "Bid" if position > 0 else "Ask"
            pos_info = {
                "position": position,
                "avg_entry_price": avg_entry_price,
                "side": side_pos
            }
            break

    # 3. Query maximum order quantity (set to None if query fails, does not affect other info return)
    max_qty = None
    try:
        # Check types for symbol/side
        if not isinstance(symbol, str) or not isinstance(side, str):
            print(f"Error: symbol/side must be strings, current symbol={symbol}, side={side}")
        elif side not in ("Bid", "Ask"):
            print(f"Error: side only allows 'Bid' or 'Ask', current side={side}")
        else:
            limit_path = f"/api/v1/account/limits/order?side={side}&symbol={symbol}"
            limit_url = BASE_URL + limit_path
            params = {"side": side, "symbol": symbol}
            print(f"Requesting: {limit_url}")
            print(f"Params for signature: {params}")
            timestamp = str(int(time.time() * 1000))
            limit_sig = get_signature_ed25519("maxOrderQuantity", timestamp, window, params)
            limit_headers = {
                "X-API-KEY": API_KEY,
                "X-SIGNATURE": limit_sig,
                "X-TIMESTAMP": timestamp,
                "X-WINDOW": str(window),
                "Content-Type": "application/json"
            }
            resp = requests.get(limit_url, headers=limit_headers)
            if resp.status_code == 200:
                data = resp.json()
                max_qty = float(data.get("maxOrderQuantity", 0))
            else:
                print("Max order API error:", resp.status_code, resp.text)
                # Skip here, do not return None
    except Exception as e:
        print("Failed to query max order quantity, set to None:", e)
        max_qty = None

    return {
        "cash": cash,
        "open_balance": open_balance,
        "position": pos_info["position"] if pos_info else 0,
        "avg_entry_price": pos_info["avg_entry_price"] if pos_info else None,
        "side": pos_info["side"] if pos_info else None,
        "max_order_qty": max_qty
    }

# === 1. read latest price ===
def get_last_n_rows(file_path, n=10):
    df = pd.read_csv(file_path)
    return df.tail(n)


# === 2. action signal  ===
def open_signal(df, account_info, symbol="BTC-USDC", contract_size = 1, leverage=1, risk_frac=0.5):
    price = df['close'].iloc[-1]
    your_trading_signal = ''
    cash = float(account_info['cash'])
    holding_qty = float(account_info['position']) if account_info['position'] else 0
    holding_value = (abs(holding_qty) * price )
    max_open_value = cash * risk_frac

    open_value = max_open_value*adx_frac

    if open_value + holding_value/leverage > max_open_value:
        open_value = max(0, max_open_value - holding_value)
    
    trade_qty = open_value * contract_size / leverage

    trade_qty = round(float(trade_qty), 3)



    if  your_trading_signal:
        return {"action": "open",'side':'bid', "qty": trade_qty}
    if your_trading_signal:
        return {"action": "open",'side':'ask', "qty": trade_qty}

    




        
        
def close_signal(df, account_info, symbol="BTC-USDC" ,contract_size = 1, leverage=1, risk_frac=0.5):

    entry_price = account_info['avg_entry_price']
    if entry_price:
        entry_price = float(entry_price)

    
    trade_qty = abs(account_info['position'])
    position = account_info['position']
    your_trading_signal = ''


    if position > 0:
        if your_trading_signal:
            return {
                "action": "close",
                "side": "ask",
                "qty": trade_qty,
                "reason": "Maximum divergence"
            }
    if position < 0:
        if your_trading_signal:
            return {
                "action": "close",
                "side": "bid",
                "qty": trade_qty,
                "reason": "RSI < 30"
            }

   

    
def place_order(signal, order_type = "Market", symbol="BTC_USDC_PERP"):
    """
    signal: dict, e.g. {"action": "open", "side": "bid", "qty": 0.001}
    symbol: str, e.g. "BTC_USDC_PERP"
    """
    # 1. Convert side to API format
    side = signal['side'].capitalize()  # API requires "Bid" or "Ask"
    qty = float(signal['qty'])
    # 2. Determine main order type (default market order)
    # 3. Build order payload
    
    order_payload = {
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "quantity": qty,
        "reduceOnly":  (signal.get("action") == "close")  # reduceOnly for closing positions
    }
    print("order_payload:", order_payload)
    # 4. Signature
    instruction = "orderExecute"
    timestamp = str(int(time.time() * 1000))
    window = 5000
    params = order_payload.copy()
    params["reduceOnly"] = (params["reduceOnly"])
    order_sig = get_signature_ed25519(instruction, timestamp, window, params)
    headers = {
        "X-API-KEY": API_KEY,
        "X-SIGNATURE": order_sig,
        "X-TIMESTAMP": timestamp,
        "X-WINDOW": str(window),
        "Content-Type": "application/json"
    }
    # 5. Send order request
    order_url = BASE_URL + "/api/v1/order"
    response = requests.post(order_url, json=order_payload, headers=headers)
    if response.status_code != 200:
        print("Order placement failed:", response.status_code, response.text)
        return None
    print("Order placement successful:", response.json())
    return response.json()

def get_open_orders(symbol="BTC_USDC_PERP"):
    """
    Query all unfilled orders
    """
    instruction = "orderOpenQuery"
    timestamp = str(int(time.time() * 1000))
    window = 5000
    params = {"symbol": symbol}
    sig = get_signature_ed25519(instruction, timestamp, window, params)
    headers = {
        "X-API-KEY": API_KEY,
        "X-SIGNATURE": sig,
        "X-TIMESTAMP": timestamp,
        "X-WINDOW": str(window),
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/api/v1/order/open?symbol={symbol}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 404:
    # This means no unfilled orders, not an error
        print("No Unfilled Orders")
        return []
    if resp.status_code != 200:
        print("Failed to query unfilled orders:", resp.status_code, resp.text)
        return []
    return resp.json()  # Assume return is a list

def cancel_order(order_id):
    """
    Cancel a single order
    """
    instruction = "orderCancel"
    timestamp = str(int(time.time() * 1000))
    window = 5000
    params = {"orderId": order_id}
    sig = get_signature_ed25519(instruction, timestamp, window, params)
    headers = {
        "X-API-KEY": API_KEY,
        "X-SIGNATURE": sig,
        "X-TIMESTAMP": timestamp,
        "X-WINDOW": str(window),
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/api/v1/order/{order_id}"
    resp = requests.delete(url, headers=headers)
    if resp.status_code != 200:
        print(f"Order cancellation failed order_id={order_id}:", resp.status_code, resp.text)
        return False
    print(f"Order cancellation successful order_id={order_id}")
    return True

def cancel_old_stop_orders(symbol, side):
    """
    Cancel all stop orders (STOP_MARKET) corresponding to the closing side
    For example, for long positions, cancel all side=Ask STOP_MARKET orders
    """
    orders = get_open_orders(symbol)
    for order in orders:
        # Assume order format has type and side fields
        if order.get("type") == "StopMarket" and order.get("side") == side:
            cancel_order(order["orderId"])

def send_trade_message(
    df, signal, order_result, account_info=None, atr=None, sl_multiplier=2, tp_multiplier=3):
    from datetime import datetime, timezone, timedelta

    utc_now = datetime.now(timezone.utc)
    utc_str = utc_now.strftime('%Y-%m-%d %H:%M:%S')
    hk_now = utc_now.astimezone(timezone(timedelta(hours=8)))
    hk_str = hk_now.strftime('%Y-%m-%d %H:%M:%S')
    price = df['close'].iloc[-1]

    # Default values
    pos_str = "0"
    avg_entry_price = "-"
    sl_price = "-"
    tp_price = "-"
    position = 0

    # Check if there is a position
    if (
        account_info
        and account_info.get("position") is not None
        and float(account_info.get("position", 0)) != 0
        and account_info.get("avg_entry_price") is not None
    ):
        try:
            position = float(account_info["position"])
            avg_entry_price = float(account_info["avg_entry_price"])
        except (TypeError, ValueError):
            position = 0
            avg_entry_price = "-"
        pos_side = "Long" if position > 0 else "Short"
        pos_str = f"{pos_side} {position:.4f} @ {avg_entry_price:.2f}"

        # Calculate TP/SL only if there is a position
        if atr is not None:
            try:
                atr = float(atr)
                if position > 0:
                    tp_price = avg_entry_price + atr * tp_multiplier
                    sl_price = avg_entry_price - atr * sl_multiplier
                else:
                    tp_price = avg_entry_price - atr * tp_multiplier
                    sl_price = avg_entry_price + atr * sl_multiplier
                tp_price = f"{tp_price:.2f}"
                sl_price = f"{sl_price:.2f}"
            except (TypeError, ValueError):
                tp_price = "-"
                sl_price = "-"
        else:
            tp_price = "-"
            sl_price = "-"
    else:
        pos_str = "0"
        avg_entry_price = "-"
        sl_price = "-"
        tp_price = "-"
        position = 0

    # === Message content ===
    signal_reason = signal.get("reason", "") if signal else ""
    # === Message content ===
    if signal is None:
        msg = (
            f"HK datetime: {hk_str}\n"
            f"UTC datetime: {utc_str}\n"
            f"Symbol: BTC_USDC_PERP\n"
            f"Price: {price}\n"
            f"Signal: No action\n"
            f"Trade qty: 0\n"
            f"Order status: None\n"
            f"\n"
            f"Position: {pos_str}\n"
            f"Entry price: {avg_entry_price}\n"
            f"Stop loss: {sl_price}\n"
            f"Take profit: {tp_price}"
        )
    else:
        action = signal.get("action", "open")
        side = signal.get("side", "-")
        qty = signal.get("qty", 0)
        msg = (
            f"HK datetime: {hk_str}\n"
            f"UTC datetime: {utc_str}\n"
            f"Symbol: BTC_USDC_PERP\n"
            f"Price: {price}\n"
            f"Signal: {action} {side}\n"
            f"Reason: {signal_reason}\n"
            f"Trade qty: {qty}\n"
            f"Order status: {'True' if order_result else 'False'}\n"
            f"\n"
            f"Position: {pos_str}\n"
            f"Entry price: {avg_entry_price}\n"
            f"Stop loss: {sl_price}\n"
            f"Take profit: {tp_price}"
        )
    send_telegram_message(msg) 

def main():
    # 1. Get account information
    account_info = get_account_info("BTC_USDC_PERP")
    if not account_info:
        print("Failed to get account information, skipping execution")
        return

    # 2. Get market data
    df = get_last_n_rows('backpack_btc_usdc_1_hour.csv')
    if df is None or len(df) == 0:
        print("Market data error")
        return
    
    latest_atr = float(df['atr'].iloc[-1])
    position = float(account_info['position'])

    # 3. Determine signals
    open_sig = open_signal(df, account_info, symbol="BTC-USDC", contract_size=0.001, leverage=10, risk_frac=0.5)
    close_sig = close_signal(df, account_info, symbol="BTC-USDC", contract_size=0.001, leverage=10, risk_frac=0.5)

    executed_signal = None
    order_result = None

    # === 1. Closing positions take priority ===
    if close_sig and position != 0:
        print("Detected closing signal:", close_sig)
        order_result = place_order(close_sig, order_type="Market", symbol="BTC_USDC_PERP")
        executed_signal = close_sig
        if order_result:
            # Re-query the latest account status
            fresh_account_info = get_account_info("BTC_USDC_PERP")
            send_trade_message(df, executed_signal, order_result, account_info=fresh_account_info, atr=latest_atr)
            print("This round of execution ended")
            return

    # === 2. If there is a same-direction open/add position signal ===
    if open_sig:
        is_long_signal = open_sig['side'].lower() == 'bid'
        if position == 0 or (position > 0 and is_long_signal) or (position < 0 and not is_long_signal):
            print("Detected open/add position signal:", open_sig)
            order_result = place_order(open_sig, order_type="Market", symbol="BTC_USDC_PERP")
            executed_signal = open_sig
            if order_result:
                time.sleep(1)
                fresh_account_info = get_account_info("BTC_USDC_PERP")
                send_trade_message(df, executed_signal, order_result, account_info=fresh_account_info, atr=latest_atr)
                print("This round of execution ended")
                return

    # Send message even if no action
    send_trade_message(df, executed_signal, order_result, account_info=account_info, atr=latest_atr)
    print("End of this round of execution")


if __name__ == "__main__":
    main()
