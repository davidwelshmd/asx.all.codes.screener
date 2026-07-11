import streamlit as st
import pandas as pd
import yfinance as yf
import io
import os
import time

# 1. PAGE LAYOUT CONFIGURATION
st.set_page_config(page_title="ASX Equity Screener", layout="wide")
st.title("📊 ASX Low P/E Valuation Screener")
st.write("Select an alphabet group to scan your ASX list efficiently and avoid timeouts.")

# 2. SIDEBAR PARAMETERS
st.sidebar.header("Screener Filters")

# Alphabet Group Selector to speed up execution
ticker_range = st.sidebar.selectbox(
    "Select Ticker Alphabet Group",
    options=["A-G", "H-L", "M-Q", "R-V", "W-Z", "ALL (Slow)"],
    index=0
)

max_pe = st.sidebar.slider("Maximum P/E Ratio Cutoff", min_value=5, max_value=40, value=20)

# Helper function to map tickers to selected ranges
def filter_by_alphabet(ticker, range_selection):
    if range_selection == "ALL (Slow)":
        return True
    first_letter = str(ticker).strip().upper()[0]
    if not first_letter.isalpha():
        return False
        
    start_letter, end_letter = range_selection.split("-")
    return start_letter <= first_letter <= end_letter

# 3. DIRECT PATH DETECTION FOR CSV LOADING
current_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(current_dir, "asx_tickers.csv")

# 4. CACHED DATA FETCHING ENGINE 
@st.cache_data(show_spinner=False, ttl=3600)  # Caches results for 1 hour per specific group combination
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
            market_cap = info.get('marketCap', None)
            enterprise_value = info.get('enterpriseValue', None)
            npat = info.get('netIncomeToCommon', None)
            ev_to_ebitda = info.get('enterpriseToEbitda', None)
            
            total_debt = info.get('totalDebt', 0) or 0
            total_cash = info.get('totalCash', 0) or 0
            net_debt = total_debt - total_cash
            
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
                "P/E Ratio": pe_ratio,  
                "EV/EBITDA (EV:E)": round(ev_to_ebitda, 2) if ev_to_ebitda else None,
                "1Y EPS Growth (%)": eps_1y_growth,
                "3Y EPS Growth (%)": eps_3y_growth
            })
            
            time.sleep(0.2)  # Avoid aggressive anti-bot triggers
            
        except Exception:
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
            
            # Apply the alphabet filter to raw tickers BEFORE hitting Yahoo Finance
            filtered_raw_tickers = [t for t in raw_tickers if filter_by_alphabet(t, ticker_range)]
            asx_tickers = [f"{str(ticker).strip().upper()}.AX" for ticker in filtered_raw_tickers if len(str(ticker).strip()) >= 3]
            
            if not asx_tickers:
                st.warning(f"No tickers found matching alphabet group: {ticker_range}")
            else:
                with st.spinner(f"Downloading Group {ticker_range} from Yahoo Finance..."):
                    # Passing ticker_range to the cache function treats each group as its own separate cache key
                    df_raw_results = get_asx_data_for_batch(asx_tickers, ticker_range)
                
                if not df_raw_results.empty:
                    # Fix the numeric type comparison crash safely
                    df_raw_results['P/E Ratio'] = pd.to_numeric(df_raw_results['P/E Ratio'], errors='coerce')
                    
                    df_filtered = df_raw_results[
                        (df_raw_results['P/E Ratio'].notna()) & 
                        (df_raw_results['P/E Ratio'] < max_pe)
                    ].copy()
                    
                    df_filtered['P/E Ratio'] = df_filtered['P/E Ratio'].round(2)
                    
                    st.subheader(f"Found {len(df_filtered)} Companies Matching Criteria (Group {ticker_range})")
                    
                    st.dataframe(df_filtered.style.format({
                        "Market Cap ($)": "{:,.0f}", 
                        "Net Debt ($)": "{:,.0f}",
                        "Enterprise Value ($)": "{:,.0f}",
                        "NPAT ($)": "{:,.0f}"
                    }))
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_filtered.to_excel(writer, index=False, sheet_name=f'ASX Group {ticker_range}')
                    
                    st.download_button(
                        label=f"📥 Download Group {ticker_range} Spreadsheet",
                        data=buffer.getvalue(),
                        file_name=f"asx_low_pe_screener_{ticker_range}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("No data retrieved from this specific scan group.")

