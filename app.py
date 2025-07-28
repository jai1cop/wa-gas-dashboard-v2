import streamlit as st
import pandas as pd
import plotly.express as px
import data_fetcher as dfc

st.sidebar.write("**Debug: Raw CSV Data**")
try:
    # Test each data source
    nameplate = dfc.fetch_csv("nameplate", force=True)
    st.sidebar.write(f"Nameplate shape: {nameplate.shape}")
    st.sidebar.write(f"Nameplate columns: {list(nameplate.columns)}")
    
    flows = dfc.fetch_csv("flows", force=True)
    st.sidebar.write(f"Flows shape: {flows.shape}")
    st.sidebar.write(f"Flows columns: {list(flows.columns)}")
    
    mto = dfc.fetch_csv("mto_future", force=True)
    st.sidebar.write(f"MTO shape: {mto.shape}")
    st.sidebar.write(f"MTO columns: {list(mto.columns)}")
    
except Exception as e:
    st.sidebar.error(f"Debug error: {e}")

st.set_page_config("WA Gas Dashboard", layout="wide")
st.title("WA Gas Supply & Demand Dashboard")

# Load real AEMO data
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_real_data():
    try:
        return dfc.get_model()
    except Exception as e:
        st.error(f"Error loading AEMO data: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Manual refresh button
if st.sidebar.button("Refresh AEMO Data"):
    st.cache_data.clear()
    st.sidebar.success("Data refreshed!")

sup, model = load_real_data()

if model.empty:
    st.error("No data available - using sample data")
    # Fall back to your sample data code
else:
    st.success(f"✅ Loaded {len(model)} days of real AEMO data")
    # Use real data for charts
