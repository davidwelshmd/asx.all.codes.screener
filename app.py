import streamlit as st
import pandas as pd
import yfinance as yf
import io
import os

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

# 4. FINANCIAL EXTRACTION ENGINE
def fetch_ticker_data(symbol, max_pe_filter):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Extract and instantly filter on P/E to save processing time
        pe_ratio = info.get('trailingPE', None)
        if pe_ratio is None or pe_ratio >= max_pe_filter:
            return None
            
        # Extract raw value metrics
        market_cap = info.get('marketCap', None)
        enterprise_value = info.get('enterpriseValue', None)
        npat = info.get('netIncomeToCommon', None)
        ev_to_ebitda = info.get('enterpriseToEbitda', None)
        
        # Calculate Net Debt (Total Debt - Cash)
        total_debt = info.get('totalDebt', 0) or 0
        total_cash = info.get('totalCash', 0) or 0
        net_debt = total_debt - total_cash
        
        # Extract Historical Financials for EPS growth calculations
        financials = ticker.financials
        eps_1y_growth = None
        eps_3y_growth = None
        
        if 'Basic EPS' in financials.index:
            eps_series = financials.loc['Basic EPS']
            if len(eps_series) >= 4:
                current_eps = eps_series.iloc[0]
                prev_1y_eps = eps_series.iloc[1]
                prev_3y_eps = eps_series.iloc[3]
                
                # Check for valid denominators to avoid division by zero
                if prev_1y_eps and prev_1y_eps != 0:
                    eps_1y_growth = round(((current_eps - prev_1y_eps) / abs(prev_1y_eps)) * 100, 2)
                if prev_3y_eps and prev_3y_eps != 0:
                    # Compounded Annual Growth Rate (CAGR) calculation
                    if current_eps > 0 and prev_3y_eps > 0:
                        eps_3y_growth = round((((current_eps / prev_3y_eps) ** (1/3)) - 1) * 100, 2)

        return {
            "Ticker": symbol.replace(".AX", ""),
            "Market Cap ($)": market_cap,
            "Net Debt ($)": net_debt,
            "Enterprise Value ($)": enterprise_value,
            "NPAT ($)": npat,
            "P/E Ratio": round(pe_ratio, 2),
            "EV/EBITDA (EV:E)": round(ev_to_ebitda, 2) if ev_to_ebitda else None,
            "1Y EPS Growth (%)": eps_1y_growth,
            "3Y EPS Growth (%)": eps_3y_growth
        }
    except Exception:
        return None

# 5. EXECUTION INTERFACE
if st.button("🚀 Start ASX Deep Scan"):
    
    if not os.path.exists(csv_path):
        st.error(f"Critical Error: Cannot find 'asx_tickers.csv' at path: {csv_path}. Please verify your GitHub file upload.")
    else:
        # Load the custom CSV file, skipping the descriptive text headers at the top
        try:
            df_asx = pd.read_csv(csv_path, skiprows=3)
        except Exception:
            df_asx = pd.read_csv(csv_path)
            
        # Strip invisible spaces out of the header column names
        df_asx.columns = [str(col).strip() for col in df_asx.columns]
        
        # Match potential spreadsheet column naming layouts
        if 'Code' in df_asx.columns:
            ticker_col = 'Code'
        elif 'Ticker' in df_asx.columns:
            ticker_col = 'Ticker'
        elif 'ASX code' in df_asx.columns:
            ticker_col = 'ASX code'
        else:
            ticker_col = None
            
        if ticker_col is None:
            st.error(f"CSV format error. Could not find a column named 'Code', 'Ticker', or 'ASX code'. Found columns: {list(df_asx.columns)}")
        else:
            raw_tickers = df_asx[ticker_col].dropna().tolist()
            # Append Yahoo Finance required region indicator (.AX)
            asx_tickers = [f"{str(ticker).strip().upper()}.AX" for ticker in raw_tickers if len(str(ticker).strip()) >= 3]
            
            results = []
            
            # Interactive Streamlit progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, symbol in enumerate(asx_tickers):
                status_text.text(f"Scanning {symbol} ({idx + 1}/{len(asx_tickers)})...")
                data = fetch_ticker_data(symbol, max_pe)
                if data:
                    results.append(data)
                progress_bar.progress((idx + 1) / len(asx_tickers))
                
            status_text.text("✅ Scan completed successfully!")
            
            if results:
                df_results = pd.DataFrame(results)
                
                # Interactive Web UI Table Preview
                st.subheader(f"Found {len(df_results)} Companies Matching Criteria")
                st.dataframe(df_results.style.format({
                    "Market Cap ($)": "{:,.0f}", 
                    "Net Debt ($)": "{:,.0f}",
                    "Enterprise Value ($)": "{:,.0f}",
                    "NPAT ($)": "{:,.0f}"
                }))
                
                # Setup In-Memory stream for clean spreadsheet extraction 
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_results.to_excel(writer, index=False, sheet_name='ASX Deep Screen')
                
                # Instant Local Browser Download Link
                st.download_button(
                    label="📥 Download Filtered Results as Excel Spreadsheet",
                    data=buffer.getvalue(),
                    file_name="asx_low_pe_screener.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Scan complete. Zero companies found matching your chosen configuration rules.")
