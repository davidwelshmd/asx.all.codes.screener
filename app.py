import streamlit as st
import pandas as pd
import yfinance as yf
import io
import os
import time

# LAYOUT CONFIG
st.set_page_config(
    page_title="ASX",
    layout="wide"
)
st.title("📊 ASX Screener")
st.write("Click 'Run Screener'")

# SIDEBAR FILTERS
st.sidebar.header("Filters")

t_range = st.sidebar.selectbox(
    "Alphabet Group",
    options=[
        "A-G", "H-L", "M-Q", 
        "R-V", "W-Z", "ALL"
    ],
    index=0
)

max_pe = st.sidebar.slider(
    "Max P/E", 
    5, 40, 20
)
max_pb = st.sidebar.slider(
    "Max P/B", 
    0.1, 10.0, 2.0, 0.1
)

mc_opts = [
    "Under $100 Million",
    "$100 - $500 Million",
    "$500 - $1,500 Million",
    "Over $1,500 Million"
]
sel_mc = st.sidebar.multiselect(
    "Market Cap",
    options=mc_opts,
    default=mc_opts
)

ex_losses = st.sidebar.toggle(
    "Exclude Losses", 
    value=False
)

st.sidebar.markdown("---")
btn_run = st.sidebar.button(
    "🚀 Run Screener", 
    use_container_width=True
)

# TICKER FILTER
def filter_ticker(t, s_range):
    t_str = str(t).strip().upper()
    pts = t_str.split(".")
    base = pts[0]
    
    if len(base) != 3:
        return False
        
    if s_range == "ALL":
        return True
        
    f_let = base[0]
    if not f_let.isalpha():
        return False
        
    st_l, en_l = s_range.split("-")
    return st_l <= f_let <= en_l

# MC MATCH
def match_mc(mc, brackets):
    if not brackets:
        return True
    if pd.isna(mc) or mc is None:
        return False
    mcm = mc / 1_000_000
    if (
        "Under $100 Million" 
        in brackets and mcm < 100
    ):
        return True
    if (
        "$100 - $500 Million" 
        in brackets 
        and 100 <= mcm <= 500
    ):
        return True
    if (
        "$500 - $1,500 Million" 
        in brackets 
        and 500 < mcm <= 1500
    ):
        return True
    if (
        "Over $1,500 Million" 
        in brackets and mcm > 1500
    ):
        return True
    return False

# CSV DIRECTORY PATH
c_dir = os.path.dirname(
    os.path.abspath(__file__)
)
csv_p = os.path.join(
    c_dir, "asx_tickers.csv"
)

# DATA FETCH ENGINE
@st.cache_data(
    show_spinner=False, 
    ttl=3600
)
def fetch_batch(tkrs, lbl):
    res = []
    p_bar = st.progress(0)
    s_txt = st.empty()
    
    for idx, sym in enumerate(tkrs):
        if sym.endswith(".AX"):
            fsym = sym
        else:
            fsym = f"{sym}.AX"
        s_txt.text(f"Scan {fsym}...")
        
        try:
            t_obj = yf.Ticker(fsym)
            inf = t_obj.info
            
            p = inf.get('currentPrice')
            pe = inf.get('trailingPE')
            pb = inf.get('priceToBook')
            mc = inf.get('marketCap')
            np = inf.get('netIncomeToCommon')
            nm = inf.get('longName', sym)
            ev = inf.get('enterpriseValue')
            
            dy = inf.get('dividendYield')
            if dy is not None:
                dy = float(dy)
                if dy > 1.0:
                    dy = dy / 100.0
            
            td = inf.get('totalDebt', 0)
            tc = inf.get('totalCash', 0)
            
            if (
                not td or pd.isna(td)
            ):
                td = 0.0
            if (
                not tc or pd.isna(tc)
            ):
                tc = 0.0
                
            if td == 0.0 and tc == 0.0:
                nd = None
            else:
                nd = float(td) - float(tc)
            
            res.append({
                "Ticker": sym,
                "Company Name": nm,
                "Price": p,
                "P/E Ratio": pe,
                "P/B Ratio": pb,
                "Dividend Yield": dy,
                "NPAT (TTM)": np,
                "Market Cap": mc,
                "Net Debt": nd,
                "Enterprise Value": ev
            })
            time.sleep(0.2)
        except Exception:
            pass
        p_bar.progress(
            (idx + 1) / len(tkrs)
        )
    s_txt.empty()
    p_bar.empty()
    return pd.DataFrame(res)

# EVALUATION MATRIX
if os.path.exists(csv_p):
    if btn_run:
        df_t = pd.read_csv(
            csv_p, header=None
        )
        t_lst = df_t.iloc[:, 0].tolist()
        t_clean = [
            str(x).strip().upper() 
            for x in t_lst
        ]
        f_tkrs = [
            x for x in t_clean 
            if filter_ticker(x, t_range)
        ]
        
        if f_tkrs:
            with st.spinner("Wait..."):
                st.session_state.raw = (
                    fetch_batch(
                        f_tkrs, t_range
                    )
                )
        else:
            st.warning("No matches")

    if (
        "raw" in st.session_state 
        and st.session_state.raw 
        is not None
    ):
        df_r = st.session_state.raw.copy()
        
        if not df_r.empty:
            v_cols = [
                "P/E Ratio", "P/B Ratio",
                "Market Cap", "NPAT (TTM)",
                "Net Debt", "Price",
                "Enterprise Value"
            ]
            for c in v_cols:
                df_r[c] = pd.to_numeric(
                    df_r[c], 
                    errors='coerce'
                )
            
            # RUNTIME METRIC FILTER
            f_df = df_r[
                (
                    df_r["P/E Ratio"].isna() 
                    | (
                        df_r["P/E Ratio"] 
                        <= max_pe
                    )
                ) &
                (
                    df_r["P/B Ratio"].isna() 
                    | (
                        df_r["P/B Ratio"] 
                        <= max_pb
                    )
                )
            ]
            
            f_df = f_df[
                f_df["Market Cap"].apply(
                    lambda x: match_mc(
                        x, sel_mc
                    )
                )
            ]
            
            if ex_losses:
                f_df = f_df[
                    f_df["NPAT (TTM)"]
                    .notna() & 
                    (
                        f_df["NPAT (TTM)"] 
                        >= 0
                    )
                ]

            # DATA FRAME DISPLAY RENDER
            st.dataframe(
                f_df, 
                use_container_width=True,
                column_config={
                    "Price": 
                    st.column_config
                    .NumberColumn(
                        "Price", 
                        format="$%.3f"
                    ),
                    "P/E Ratio": 
                    st.column_config
                    .NumberColumn(
                        "P/E Ratio", 
                        format="%.2f"
                    ),
                    "P/B Ratio": 
                    st.column_config
                    .NumberColumn(
                        "P/B Ratio", 
                        format="%.2f"
                    ),
                    "Dividend Yield": 
                    st.column_config
                    .NumberColumn(
                        "Div Yield", 
                        format="%.2f%%"
                    ),
                    "NPAT (TTM)": 
                    st.column_config
                    .NumberColumn(
                        "NPAT TTM", 
                        format="$%.2f a"
                    ),
                    "Market Cap": 
                    st.column_config
                    .NumberColumn(
                        "Market Cap", 
                        format="$%.2f a"
                    ),
                    "Net Debt": 
                    st.column_config
                    .NumberColumn(
                        "Net Debt", 
                        format="$%.2f a"
                    ),
                    "Enterprise Value": 
                    st.column_config
                    .NumberColumn(
                        "EV", 
                        format="$%.2f a"
                    )
                }
            )
            
            # DOWNLOAD CONTROLLER
            buf = io.BytesIO()
            f_df.to_csv(
                buf, index=False
            )
            b_val = buf.getvalue()
            
            st.download_button(
                label="📥 Download CSV",
                data=b_val,
                file_name="asx.csv",
                mime="text/csv"
            )
        else:
            st.warning("No data rows found")
    else:
        st.info("💡 Adjust filters & Run")
else:
    st.error(f"Missing file: {csv_p}")
