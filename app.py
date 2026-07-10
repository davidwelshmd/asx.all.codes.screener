import streamlit as st
import pandas as pd
import yfinance as yf
import io

# App Titles
st.set_page_config(page_title="ASX Equity Screener", layout="wide")
st.title("📊 ASX Low P/E Valuation Screener")
st.write("Scan the ASX for companies with a P/E Ratio under 20 and download the clean dataset.")

# Sidebar Configuration Controls
st.sidebar.header("Scan Parameters")
max_pe = st.sidebar.slider("Maximum P/E Ratio Cutoff", min_value=5, max_value=40, value=20)

# Helper function to extract financial metrics safely
def fetch_ticker_data(symbol, max_pe_filter):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        pe_ratio = info.get('trailingPE', None)
        # Immediate filtering to maximize processing speed
        if pe_ratio is None or pe_ratio >= max_pe_filter:
            return None
            
        market_cap = info.get('marketCap', None)
        enterprise_value = info.get('enterpriseValue', None)
        npat = info.get('netIncomeToCommon', None)
        ev_to_ebitda = info.get('enterpriseToEbitda', None)
        
        # Calculate Net Debt
        net_debt = (info.get('totalDebt', 0) or 0) - (info.get('totalCash', 0) or 0)
        
        # Calculate basic growth proxies from income statements
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
                    eps_3y_growth = round((((current_eps / prev_3y_eps) ** (1/3)) - 1) * 100, 2)

        return {
            "Ticker": symbol,
            "Market Cap ($)": market_cap,
            "Net Debt ($)": net_debt,
            "Enterprise Value ($)": enterprise_value,
            "NPAT ($)": npat,
            "P/E Ratio": round(pe_ratio, 2),
            "EV/EBITDA": round(ev_to_ebitda, 2) if ev_to_ebitda else None,
            "1Y EPS Growth (%)": eps_1y_growth,
            "3Y EPS Growth (%)": eps_3y_growth
        }
    except Exception:
        return None # Ignore logging to keep screen UI clean

# Trigger Button
if st.button("🚀 Start ASX Deep Scan"):
    
    # Placeholder list for demonstration. 
    # In practice, read your uploaded file: tickers = pd.read_csv("asx_tickers.csv")['Ticker'].tolist()
    sample_asx_tickers = ["CBA.AX", "BHP.AX", "TLS.AX", "WOW.AX", "WBC.AX", "APT.AX", "COH.AX", "FMG.AX"]
    
    results = []
    
    # Progress visualization bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, symbol in enumerate(sample_asx_tickers):
        status_text.text(f"Scanning {symbol} ({idx + 1}/{len(sample_asx_tickers)})...")
        data = fetch_ticker_data(symbol, max_pe)
        if data:
            results.append(data)
        progress_bar.progress((idx + 1) / len(sample_asx_tickers))
        
    status_text.text("Scan completed successfully!")
    
    if results:
        df_results = pd.DataFrame(results)
        
        # Display preview inside web browser
        st.subheader(f"Found {len(df_results)} Companies Matching Criteria")
        st.dataframe(df_results)
        
        # In-Memory generation of Excel sheet for direct browser downloading
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_results.to_excel(writer, index=False, sheet_name='ASX Filters')
        
        # Action button to trigger instant local download
        st.download_button(
            label="📥 Download Results as Excel Spreadsheet",
            data=buffer.getvalue(),
            file_name="asx_low_pe_screener.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No companies found matching that P/E constraint.")
