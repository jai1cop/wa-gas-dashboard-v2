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

# COMPREHENSIVE DEBUG SECTION
st.sidebar.write("**📊 Debug Information:**")
st.sidebar.write(f"Supply DataFrame shape: {sup.shape}")
st.sidebar.write(f"Model DataFrame shape: {model.shape}")

# Show DataFrame columns and samples
if not sup.empty:
    st.sidebar.write("**Supply columns:**", list(sup.columns))
    st.sidebar.write("Supply sample:")
    st.sidebar.dataframe(sup.head(3))
else:
    st.sidebar.error("❌ Supply DataFrame is EMPTY")

if not model.empty:
    st.sidebar.write("**Model columns:**", list(model.columns))
    st.sidebar.write("Model sample:")
    st.sidebar.dataframe(model.head(3))
else:
    st.sidebar.error("❌ Model DataFrame is EMPTY")

# RAW CSV DEBUG
st.sidebar.write("**📁 Raw CSV Debug:**")
try:
    nameplate = dfc.fetch_csv("nameplate", force=False)
    flows = dfc.fetch_csv("flows", force=False)
    mto = dfc.fetch_csv("mto_future", force=False)
    
    st.sidebar.write(f"Raw nameplate shape: {nameplate.shape}")
    st.sidebar.write(f"Raw flows shape: {flows.shape}")
    st.sidebar.write(f"Raw MTO shape: {mto.shape}")
    
    # FACILITY TYPE DEBUG - This is the key issue
    st.sidebar.write("**🏭 Facility Type Analysis:**")
    if 'facilitytype' in nameplate.columns:
        facility_types = nameplate['facilitytype'].value_counts()
        st.sidebar.write("Nameplate facility types:")
        st.sidebar.dataframe(facility_types)
    else:
        st.sidebar.error("No 'facilitytype' column in nameplate")
    
    if 'facilitytype' in mto.columns:
        mto_types = mto['facilitytype'].value_counts()
        st.sidebar.write("MTO facility types:")
        st.sidebar.dataframe(mto_types)
    else:
        st.sidebar.error("No 'facilitytype' column in MTO")
        
    # COLUMN STRUCTURE DEBUG
    st.sidebar.write("**📋 Column Structure:**")
    st.sidebar.write("Nameplate columns:", list(nameplate.columns))
    st.sidebar.write("MTO columns:", list(mto.columns))
    st.sidebar.write("Flows columns:", list(flows.columns))
    
except Exception as e:
    st.sidebar.error(f"Raw data debug error: {e}")

# CLEANING FUNCTION DEBUG
st.sidebar.write("**🔧 Data Cleaning Debug:**")
try:
    # Test individual cleaning functions
    nameplate_raw = dfc.fetch_csv("nameplate", force=False)
    nameplate_clean = dfc.clean_nameplate(nameplate_raw)
    st.sidebar.write(f"Nameplate: {nameplate_raw.shape} → {nameplate_clean.shape}")
    
    mto_raw = dfc.fetch_csv("mto_future", force=False)
    mto_clean = dfc.clean_mto(mto_raw)
    st.sidebar.write(f"MTO: {mto_raw.shape} → {mto_clean.shape}")
    
    flows_raw = dfc.fetch_csv("flows", force=False)
    demand_clean = dfc.build_demand_profile()
    st.sidebar.write(f"Demand: {flows_raw.shape} → {demand_clean.shape}")
    
except Exception as e:
    st.sidebar.error(f"Cleaning debug error: {e}")

# MAIN DASHBOARD LOGIC
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
    
    # Check if required columns exist before proceeding
    required_cols = ['TJ_Demand', 'TJ_Available']
    missing_cols = [col for col in required_cols if col not in model.columns]
    
    if missing_cols:
        st.error(f"❌ Missing required columns: {missing_cols}")
        st.write("**Available columns in model:**", list(model.columns))
        st.write("**This suggests an issue in the data_fetcher.py merge operation**")
        
        # Show debugging info
        st.write("**Debugging Information:**")
        st.write("1. Check if supply data is empty (supply shape above)")
        st.write("2. Check facility types in sidebar - are they 'production'?")
        st.write("3. Check if column names match expectations")
        
        if not model.empty:
            st.write("**Current model data:**")
            st.dataframe(model.head())
        st.stop()
    
    # Apply Yara adjustment
    model_adj = model.copy()
    model_adj["TJ_Demand"] = model_adj["TJ_Demand"] + (yara_val - 80)
    model_adj["Shortfall"] = model_adj["TJ_Available"] - model_adj["TJ_Demand"]
    
    # Create supply stack chart
    if not sup.empty and 'TJ_Available' in sup.columns and 'FacilityName' in sup.columns and 'GasDay' in sup.columns:
        try:
            stack = sup.pivot(index="GasDay", columns="FacilityName", values="TJ_Available")
            today_dt = pd.to_datetime(date.today())
            stack = stack.loc[stack.index >= today_dt]
            
            if not stack.empty:
                fig1 = px.area(stack,
                              labels={"value": "TJ/day", "GasDay": "Date", "variable": "Facility"},
                              title="WA Gas Supply by Facility (Stacked)")
                
                # Add demand line
                if 'GasDay' in model_adj.columns:
                    fig1.add_scatter(x=model_adj["GasDay"], y=model_adj["TJ_Demand"],
                                   mode="lines", name="Demand",
                                   line=dict(color="black", width=3))
                
                # Add shortfall markers
                shortfalls = model_adj[model_adj["Shortfall"] < 0]
                if not shortfalls.empty and 'GasDay' in shortfalls.columns:
                    fig1.add_scatter(x=shortfalls["GasDay"], y=shortfalls["TJ_Demand"],
                                   mode="markers", name="Shortfall",
                                   marker=dict(color="red", size=7, symbol="x"))
                
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.warning("⚠️ No future supply data available for chart")
                st.write("This could mean:")
                st.write("- All supply data is in the past")
                st.write("- Date filtering removed all records")
        except Exception as e:
            st.error(f"Error creating supply chart: {e}")
            st.write("Stack pivot shape:", stack.shape if 'stack' in locals() else "Not created")
    else:
        st.error("❌ Supply data missing required columns for stacked chart")
        st.write("**Required columns:** ['TJ_Available', 'FacilityName', 'GasDay']")
        if not sup.empty:
            st.write("**Available supply columns:**", list(sup.columns))
            st.write("**Supply data sample:**")
            st.dataframe(sup.head())
        else:
            st.write("**Supply DataFrame is empty - check facility type filtering**")
    
    # Supply-demand balance bar chart
    try:
        if 'GasDay' in model_adj.columns and 'Shortfall' in model_adj.columns:
            fig2 = px.bar(model_adj, x="GasDay", y="Shortfall",
                          color=model_adj["Shortfall"] >= 0,
                          color_discrete_map={True: "green", False: "red"},
                          labels={"Shortfall": "Supply-Demand Gap (TJ)"},
                          title="Daily Market Balance")
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.error("Missing columns for balance chart")
    except Exception as e:
        st.error(f"Error creating balance chart: {e}")
    
    # Data table
    st.subheader("Daily Balance Summary")
    try:
        display_cols = ["GasDay", "TJ_Available", "TJ_Demand", "Shortfall"]
        available_cols = [col for col in display_cols if col in model_adj.columns]
        
        if available_cols:
            display_df = model_adj[available_cols].copy()
            
            # Rename columns for display
            rename_map = {
                "GasDay": "Date",
                "TJ_Available": "Available Supply (TJ)",
                "TJ_Demand": "Demand (TJ)",
                "Shortfall": "Balance (TJ)"
            }
            display_df = display_df.rename(columns={k: v for k, v in rename_map.items() if k in display_df.columns})
            
            st.dataframe(display_df, use_container_width=True)
        else:
            st.error("No suitable columns available for data table")
            st.write("**Available columns:**", list(model_adj.columns))
    except Exception as e:
        st.error(f"Error creating data table: {e}")

# FINAL DEBUG SUMMARY
st.sidebar.write("**🎯 Debug Summary:**")
st.sidebar.write(f"Dashboard loaded: {'✅' if not model.empty else '❌'}")
st.sidebar.write(f"Supply data: {'✅' if not sup.empty else '❌'}")
st.sidebar.write(f"Model has TJ_Available: {'✅' if not model.empty and 'TJ_Available' in model.columns else '❌'}")
st.sidebar.write(f"Model has TJ_Demand: {'✅' if not model.empty and 'TJ_Demand' in model.columns else '❌'}")
st.sidebar.write(f"Supply has required cols: {'✅' if not sup.empty and all(col in sup.columns for col in ['TJ_Available', 'FacilityName', 'GasDay']) else '❌'}")

# STREAMLIT CLOUD LOGS REMINDER
st.sidebar.info("💡 **Tip:** Check Streamlit Cloud logs (Manage app → Logs) for detailed [DEBUG] messages from data_fetcher.py")
