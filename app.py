import streamlit as st
import pandas as pd
import yfinance as yf
import io
import os
import time

# 1. PAGE LAYOUT CONFIGURATION
st.set_page_config(page_title="ASX Equity Screener", layout="wide")
st.title("📊 ASX Low P/E Valuation Screener")
st.write("Configure your filters below and press 'Run Screener' to scan your ASX list without timeouts.")

# Initialize a custom session state tracker to safely govern the manual run button
if "run_screener" not in st.session_state:
    st.session_state.run_screener = False

# 2. SIDEBAR PARAMETERS (Moved out of st.form to resolve the multiselect freeze bug)
st.sidebar.header("Screener Filters")

ticker_range = st.sidebar.selectbox(
    "Select Ticker Alphabet Group",
    options=["A-G", "H-L", "M-Q", "R-V", "W-Z", "ALL (Slow)"],
    index=0
)

max_pe = st.sidebar.slider("Maximum P/E Ratio Cutoff", min_value=5, max_value=40, value=20)
max_pb = st.sidebar.slider("Maximum P/B Ratio Cutoff", min_value=0.1, max_value=10.0, value=2.0, step=0.1)

# Market Cap Category Filter (Now fully clickable)
market_cap_options = [
    "Under $100 Million",
    "$100 - $500 Million",
    "$500 - $1,500 Million",
    "Over $1,500 Million"
]
selected_mc_brackets = st.sidebar.multiselect(
    "Market Capitalisation Brackets",
    options=market_cap_options,
    default=market_cap_options
)

# Toggle: Filter Profitability
exclude_losses = st.sidebar.toggle("Exclude Loss-Making Companies (NPAT < 0)", value=False)

st.sidebar.markdown("---")
# The Action Trigger Button
if st.sidebar.button("🚀 Run Screener", use_container_width=True):
    st.session_state.run_screener = True


# Helper function to map tickers to selected ranges and ensure they are standard 3-digit tickers
def filter_ticker(ticker, range_selection):
    ticker_str = str(ticker).strip().upper()
    
    # Remove standard '.AX' suffix if present to accurately check length
    clean_ticker = ticker_str.split(".")[0]
    
    # Enforce strict 3-digit rule (removes hybrids like WBCPL, MQGPF, or options)
    if len(clean_ticker) != 3:
        return False
        
    if range_selection == "ALL (Slow)":
        return True
        
    first_letter = clean_ticker[0]
    if not first_letter.isalpha():
        return False
        
    start_letter, end_letter = range_selection.split("-")
    return start_letter <= first_letter <= end_letter

# Helper function to classify market caps into your custom brackets
def matches_market_cap_bracket(market_cap, selected_brackets):
    if not selected_brackets:
        return True
    if pd.isna(market_cap) or market_cap is None:
        return False
        
    mc_million = market_cap / 1_000_000
    
    if "Under $100 Million" in selected_brackets and mc_million < 100:
        return True
    if "$100 - $500 Million" in selected_brackets and 100 <= mc_million <= 500:
        return True
    if "$500 - $1,500 Million" in selected_brackets and 500 < mc_million <= 1500:
        return True
    if "Over $1,500 Million" in selected_brackets and mc_million > 1500:
        return True
        
    return False

# 3. DIRECT PATH DETECTION FOR CSV LOADING
current_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(current_dir, "asx_tickers.csv")

# 4. CACHED DATA FETCHING ENGINE 
@st.cache_data(show_spinner=False, ttl=3600)
def get_asx_data_for_batch(asx_tickers, range_label):
    """Fetches ticker data for the filtered batch and caches it."""
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, symbol in enumerate(asx_tickers):
        status_text.text(f"Scanning {symbol} ({idx + 1}/{len(asx_tickers)}) in Group {range_label}...")
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            pe_ratio = info.get('trailingPE', None)
            pb_ratio = info.get('priceToBook', None)
            market_cap = info.get('marketCap', None)
            npat = info.get('netIncomeToCommon', None)
            current_price = info.get('currentPrice', None)
            long_name = info.get('longName', symbol)
            div_yield = info.get('dividendYield', None)
            
            results.append({
                "Ticker": symbol,
                "Company Name": long_name,
                "Price": current_price,
                "P/E Ratio": pe_ratio,
                "P/B Ratio": pb_ratio,
                "Dividend Yield": div_yield,
                "NPAT (TTM)": npat,
                "Market Cap": market_cap
            })
            
            time.sleep(0.2)
            
        except Exception as e:
            pass
            
        progress_bar.progress((idx + 1) / len(asx_tickers))
        
    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(results)

# 5. LOADING AND EXECUTION LOGIC
if os.path.exists(csv_path):
    # Check if the execution flag is active in the session state
    if st.session_state.run_screener:
        df_tickers = pd.read_csv(csv_path, header=None)
        raw_ticker_list = df_tickers.iloc[:, 0].tolist()
        
        # Apply combined alphabet and length filtering
        filtered_tickers = [t for t in raw_ticker_list if filter_ticker(t, ticker_range)]
        
        if filtered_tickers:
            with st.spinner("Fetching data from Yahoo Finance..."):
                df_results = get_asx_data_for_batch(filtered_tickers, ticker_range)
                
            if not df_results.empty:
                # Reset run tracking flag so modifications to filters later don't trigger auto-runs
                st.session_state.run_screener = False
                
                # Apply dynamic P/E and P/B filters
                filtered_df = df_results[
                    (df_results["P/E Ratio"].isna() | (df_results["P/E Ratio"] <= max_pe)) &
                    (df_results["P/B Ratio"].isna() | (df_results["P/B Ratio"] <= max_pb))
                ]
                
                # Apply the custom Market Capitalisation bracket filters
                filtered_df = filtered_df[
                    filtered_df["Market Cap"].apply(lambda x: matches_market_cap_bracket(x, selected_mc_brackets))
                ]
                
                # Apply profitability toggle filter if checked
                if exclude_losses:
                    filtered_df = filtered_df[
                        filtered_df["NPAT (TTM)"].notna() & (filtered_df["NPAT (TTM)"] >= 0)
                    ]
                
                # 6. STREAMLIT DATA FRAME COLUMNS CONFIGURATION
                st.dataframe(
                    filtered_df, 
                    use_container_width=True,
                    column_config={
                        "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
                        "P/E Ratio": st.column_config.NumberColumn("P/E Ratio", format="%.2f"),
                        "P/B Ratio": st.column_config.NumberColumn("P/B Ratio", format="%.2f"),
                        "Dividend Yield": st.column_config.NumberColumn("Dividend Yield", format="%.2f%%"),
                        "NPAT (TTM)": st.column_config.NumberColumn("NPAT (TTM)", format="$%.2f a"),
                        "Market Cap": st.column_config.NumberColumn("Market Cap", format="$%.2f a")
                    }
                )
                
                # Prepare CSV data for export
                csv_df = filtered_df.copy()
                if not csv_df.empty and "Dividend Yield" in csv_df.columns:
                    csv_df["Dividend Yield"] = csv_df["Dividend Yield"] * 100
                    
                # 7. EXPORT TO CSV FEATURE
                csv_buffer = io.BytesIO()
                csv_df.to_csv(csv_buffer, index=False)
                csv_bytes = csv_buffer.getvalue()
                
                st.download_button(
                    label="📥 Download Filtered List as CSV",
                    data=csv_bytes,
                    file_name=f"asx_screener_{ticker_range.lower().replace(' ', '_')}.csv",
                    mime="text/csv"
                )
                
            else:
                st.session_state.run_screener = False
                st.warning("No data retrieved for this batch.")
        else:
            st.session_state.run_screener = False
            st.warning("No tickers found matching this alphabet group and length condition.")
    else:
        st.info("💡 Adjust your filters in the sidebar and click **'Run Screener'** to start scanning.")
else:
    st.error(f"Missing configuration asset. Please place your 'asx_tickers.csv' file inside: {current_dir}")
