import streamlit as st
import pandas as pd
import plotly.express as px
import data_fetcher as dfc
from datetime import date

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

# Sidebar controls
st.sidebar.header("Scenario Controls")

# Yara consumption slider
yara_val = st.sidebar.slider(
    "Yara Pilbara Fertilisers gas consumption (TJ/day)",
    min_value=0, max_value=100, value=80, step=5
)

# Manual refresh button
if st.sidebar.button("Refresh AEMO Data"):
    st.cache_data.clear()
    st.sidebar.success("Data refreshed!")

# Load data
sup, model = load_real_data()

if model.empty:
    st.error("No data available - using sample data")
    # Sample data fallback
    sample_data = {
        'Date': pd.date_range('2025-07-28', periods=30),
        'Supply': [1800 + i*5 for i in range(30)],
        'Demand': [1600 + i*3 for i in range(30)]
    }
    df = pd.DataFrame(sample_data)
    df['Balance'] = df['Supply'] - df['Demand']
    
    fig = px.line(df, x='Date', y=['Supply', 'Demand'], 
                  title="Sample Gas Supply vs Demand")
    st.plotly_chart(fig, use_container_width=True)
    
else:
    st.success(f"✅ Loaded {len(model)} days of real AEMO data")
    
    # Apply Yara adjustment
    model_adj = model.copy()
    model_adj["TJ_Demand"] = model_adj["TJ_Demand"] + (yara_val - 80)
    model_adj["Shortfall"] = model_adj["TJ_Available"] - model_adj["TJ_Demand"]
    
    # Create supply stack chart
    if not sup.empty:
        stack = sup.pivot(index="GasDay", columns="FacilityName", values="TJ_Available")
        today_dt = pd.to_datetime(date.today())
        stack = stack.loc[stack.index >= today_dt]
        
        if not stack.empty:
            fig1 = px.area(stack,
                          labels={"value": "TJ/day", "GasDay": "Date", "variable": "Facility"},
                          title="WA Gas Supply by Facility (Stacked)")
            
            # Add demand line
            fig1.add_scatter(x=model_adj["GasDay"], y=model_adj["TJ_Demand"],
                           mode="lines", name="Demand",
                           line=dict(color="black", width=3))
            
            # Add shortfall markers
            shortfalls = model_adj[model_adj["Shortfall"] < 0]
            if not shortfalls.empty:
                fig1.add_scatter(x=shortfalls["GasDay"], y=shortfalls["TJ_Demand"],
                               mode="markers", name="Shortfall",
                               marker=dict(color="red", size=7, symbol="x"))
            
            st.plotly_chart(fig1, use_container_width=True)
    
    # Supply-demand balance bar chart
    fig2 = px.bar(model_adj, x="GasDay", y="Shortfall",
                  color=model_adj["Shortfall"] >= 0,
                  color_discrete_map={True: "green", False: "red"},
                  labels={"Shortfall": "Supply-Demand Gap (TJ)"},
                  title="Daily Market Balance")
    fig2.update_layout(showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)
    
    # Data table
    st.subheader("Daily Balance Summary")
    display_cols = ["GasDay", "TJ_Available", "TJ_Demand", "Shortfall"]
    if all(col in model_adj.columns for col in display_cols):
        st.dataframe(
            model_adj[display_cols].rename(columns={
                "GasDay": "Date",
                "TJ_Available": "Available Supply (TJ)",
                "TJ_Demand": "Demand (TJ)",
                "Shortfall": "Balance (TJ)"
            }),
            use_container_width=True
        )
