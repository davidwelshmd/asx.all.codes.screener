import streamlit as st
import pandas as pd
import yfinance as yf
import io
import os
import time  # Added for rate limiting

# 1. PAGE LAYOUT CONFIGURATION
st.set_page_config(page_title="ASX Equity Screener", layout="wide")
st.title("📊 ASX Low P/E Valuation Screener")
st.write("Scan your ASX list for companies with a P/E Ratio under 20 and download the clean dataset.")

# 2. SIDEBAR PARAMETERS
st.sidebar.header("Screener Filters")
max_pe = st.sidebar.slider("Maximum P/E Ratio Cutoff", min_value=5, max_value=40, value=20)

# 3. DIRECT PATH DETECTION FOR CSV LOADING
current_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(current_dir, "asx_tickers.csv")

# 4. CACHED DATA FETCHING ENGINE (Fixes the rate-limiting and rerunning issue)
@st.cache_data(show_spinner=False, ttl=3600)  # Caches results for 1 hour
def get_all_asx_data(asx_tickers):
    """Fetches ALL ticker data once and caches it to memory."""
    results = []
    
    # Create a progress bar inside the cached function
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, symbol in enumerate(asx_tickers):
        status_text.text(f"Scraping {symbol} ({idx + 1}/{len(asx_tickers)})...")
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Extract raw metrics safely
            pe_ratio = info.get('trailingPE', None)
            market_cap = info.get('marketCap', None)
            enterprise_value = info.get('enterpriseValue', None)
            npat = info.get('netIncomeToCommon', None)
            ev_to_ebitda = info.get('enterpriseToEbitda', None)
            
            # Calculate Net Debt
            total_debt = info.get('totalDebt', 0) or 0
            total_cash = info.get('totalCash', 0) or 0
            net_debt = total_debt - total_cash
            
            # Extract Historical Financials
            financials = ticker.financials
            eps_1y_growth = None
            eps_3y_growth = None
            
            if 'Basic EPS' in financials.index:
                eps_series = financials.loc['Basic EPS']
                if len(eps_series) >= 4:
                    current_eps = eps_series.iloc[0]
                    prev_1y_eps = eps_series.iloc[1]
                    prev_3y_eps = eps_series.iloc[3]
                    
                    if prev_1y_eps and prev_1y_eps != 0:
                        eps_1y_growth = round(((current_eps - prev_1y_eps) / abs(prev_1y_eps)) * 100, 2)
                    if prev_3y_eps and prev_3y_eps != 0:
                        if current_eps > 0 and prev_3y_eps > 0:
                            eps_3y_growth = round((((current_eps / prev_3y_eps) ** (1/3)) - 1) * 100, 2)

            results.append({
                "Ticker": symbol.replace(".AX", ""),
                "Market Cap ($)": market_cap,
                "Net Debt ($)": net_debt,
                "Enterprise Value ($)": enterprise_value,
                "NPAT ($)": npat,
                "P/E Ratio": pe_ratio,  # Keep raw for filtering later
                "EV/EBITDA (EV:E)": round(ev_to_ebitda, 2) if ev_to_ebitda else None,
                "1Y EPS Growth (%)": eps_1y_growth,
                "3Y EPS Growth (%)": eps_3y_growth
            })
            
            # Polite scraping: pause 0.2 seconds between requests to avoid bans
            time.sleep(0.2) 
            
        except Exception:
            # Skip broken tickers silently
            pass
            
        progress_bar.progress((idx + 1) / len(asx_tickers))
        
    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(results)

# 5. EXECUTION INTERFACE
if st.button("🚀 Start ASX Deep Scan"):
    
    if not os.path.exists(csv_path):
        st.error(f"Critical Error: Cannot find 'asx_tickers.csv' at path: {csv_path}.")
    else:
        try:
            df_asx = pd.read_csv(csv_path, header=None, names=['Ticker', 'Company Name', 'Sector', 'Shares', 'Price', 'Col6', 'Col7', 'Col8'])
        except Exception as e:
            st.error(f"Error opening CSV: {e}")
            df_asx = pd.DataFrame()
            
        if df_asx.empty or 'Ticker' not in df_asx.columns:
            st.error("CSV loading failed or file is completely empty.")
        else:
            raw_tickers = df_asx['Ticker'].dropna().tolist()
            asx_tickers = [f"{str(ticker).strip().upper()}.AX" for ticker in raw_tickers if len(str(ticker).strip()) >= 3]
            
            # Fetch data (will load instantly from cache on second run!)
            with st.spinner("Downloading data from Yahoo Finance... (This takes a while on the first run)"):
                df_raw_results = get_all_asx_data(asx_tickers)
            
            if not df_raw_results.empty:
                # Apply the user's P/E filter completely in-memory
                            if not df_raw_results.empty:
                # Force P/E Ratio to be strictly numeric, converting unparsable values into NaN
                df_raw_results['P/E Ratio'] = pd.to_numeric(df_raw_results['P/E Ratio'], errors='coerce')
                
                # Apply the user's P/E filter safely
                df_filtered = df_raw_results[
                    (df_raw_results['P/E Ratio'].notna()) & 
                    (df_raw_results['P/E Ratio'] < max_pe)
                ].copy()

                # Round P/E ratio for clean visual presentation
                df_filtered['P/E Ratio'] = df_filtered['P/E Ratio'].round(2)
                
                st.subheader(f"Found {len(df_filtered)} Companies Matching Criteria")
                
                # Display Interactive UI Table Preview
                st.dataframe(df_filtered.style.format({
                    "Market Cap ($)": "{:,.0f}", 
                    "Net Debt ($)": "{:,.0f}",
                    "Enterprise Value ($)": "{:,.0f}",
                    "NPAT ($)": "{:,.0f}"
                }))
                
                # Setup In-Memory stream for clean spreadsheet extraction 
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_filtered.to_excel(writer, index=False, sheet_name='ASX Deep Screen')
                
                st.download_button(
                    label="📥 Download Filtered Results as Excel Spreadsheet",
                    data=buffer.getvalue(),
                    file_name="asx_low_pe_screener.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("No data retrieved from the scan.")
