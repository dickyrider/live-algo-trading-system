import requests
import pandas as pd
import numpy as np
import datetime
import os
import time
import pandas_ta as ta
import subprocess

CSV_FILE = "backpack_btc_usdc_1_hour.csv"
SYMBOL = "BTC_USDC"
INTERVAL = "1h"
SLEEP_SECONDS = 10  

def get_last_end(csv_file):
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            if not df.empty:
                df['end'] = pd.to_datetime(df['end']).view('int64') // 10**9
                print('Reading CSV file successfully.')
                return int(df['end'].max())
        except Exception as e:
            print(f"Failed to read CSV: {e}")
    return 0

def fetch_klines(symbol, interval, start_time):
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": int(start_time)
    }
    url = "https://api.backpack.exchange/api/v1/klines"
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Failed to request API: {e}")
        return pd.DataFrame()

def vbp(df, period, close='close', volume='volume'):
    df['highest_vbp'] = np.nan
    for i in range(len(df)):
        if i < period - 1:
            continue
        segment = df.iloc[i - period + 1 : i + 1]
        prices = segment[close].values
        volumes = segment[volume].values
        rounded_prices = np.round(prices, 1)
        unique_prices = np.unique(rounded_prices)
        vbp_volume = np.zeros(unique_prices.shape)
        for j, price in enumerate(unique_prices):
            vbp_volume[j] = np.sum(volumes[rounded_prices == price])
        highest_vbp_price = unique_prices[np.argmax(vbp_volume)]
        df.at[i, 'highest_vbp'] = highest_vbp_price
    return df

def compute_indicators_partial(df, period=20):
    for col in ['open','high','low','close','volume']:
        df[col] = df[col].astype(float)
    df['tpma'] = (df['high'] + df['low'] + df['close']) / 3
    df['tpma5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['tpma10'] = df['close'].ewm(span=10, adjust=False).mean()
    try:
        adx_df = ta.adx(df['high'], df['low'], df['close'])
        df['ADX'] = adx_df['ADX_14']
        df['DI+'] = adx_df['DMP_14']
        df['DI-'] = adx_df['DMN_14']
        df['atr']    = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['rsi']    = ta.rsi(df['close'], length=7)
    except Exception as e:
        print("pandas-ta DMI/ADX Error:", e)
        df['DI+'] = df['DI-'] = df['ADX'] = df['atr'] = df['rsi'] = np.nan
    df = vbp(df, period=period, close='close', volume='volume')
    return df

def update_csv_with_new_klines(csv_file, period=24):
    last_end = get_last_end(csv_file)
    print(f"Latest price end: {last_end} ({datetime.datetime.utcfromtimestamp(last_end) if last_end else 'none'})")

    while True:
        new_df = fetch_klines(SYMBOL, INTERVAL, last_end)
        if new_df.empty:
            print(f"{datetime.datetime.utcnow()} No new price data, restarting after {SLEEP_SECONDS} seconds...")
            time.sleep(SLEEP_SECONDS)
            continue

        order = ["start", "end", "open", "high", "low", "close", "volume", "quoteVolume", "trades"]
        new_df = new_df[order]
        end_as_ts = pd.to_datetime(new_df['end']).astype('int64') // 10**9
        new_rows = new_df[end_as_ts > last_end]
        if new_rows.empty:
            print(f"{datetime.datetime.utcnow()} No new price data, restarting after {SLEEP_SECONDS} seconds...")
            time.sleep(SLEEP_SECONDS)
            continue

        print(f"{datetime.datetime.utcnow()} Caught {len(new_rows)} new price data...")

        if os.path.exists(csv_file):
            print(f"CSV file {csv_file} exists, appending new data...")
            old_df = pd.read_csv(csv_file)
            # Take the last required lookback rows
            lookback = period*2  # Longest for vbp
            if len(old_df) > lookback:
                context_df = old_df.tail(lookback)
            else:
                context_df = old_df
            # Merge (ensure sufficient calculation interval for indicators)
            calc_df = pd.concat([context_df, new_rows], ignore_index=True)
            calc_df = compute_indicators_partial(calc_df, period=lookback)
            # Extract the indicator part of the new rows
            latest_inds = calc_df.tail(len(new_rows))
            # Merge back to old data
            final_df = pd.concat([old_df, latest_inds], ignore_index=True)
            final_df = final_df.drop_duplicates(subset='end', keep='last')
        else:
            calc_df = compute_indicators_partial(new_rows, period=period)
            final_df = calc_df
    

        final_df.to_csv(csv_file, index=False)
        print(f"{datetime.datetime.utcnow()} Added {len(new_rows)} new price data with indicators.")
        print(final_df.tail(5))

        print("Starting to run trade bot: backpack_trade_bot.py")
        try:
            # Recommend using absolute paths to prevent crontab environment path issues
            result = subprocess.run(
                ['/root/anaconda3/bin/python', '/root/backpack_trade_bot.py'], 
                capture_output=True,
                text=True
            )
            print("Trade bot stdout:")
            print(result.stdout)
            if result.stderr:
                print("Trade bot stderr:")
                print(result.stderr)
        except Exception as e:
            print(f"Error running trade bot: {e}")
        break

if __name__ == "__main__":
    update_csv_with_new_klines(CSV_FILE)