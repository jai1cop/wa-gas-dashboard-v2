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

# DEBUG SECTION (Optional - can be removed once working)
st.sidebar.write("**📊 Debug Information:**")
st.sidebar.write(f"Supply DataFrame shape: {sup.shape}")
st.sidebar.write(f"Model DataFrame shape: {model.shape}")

if not sup.empty:
    st.sidebar.write("**Supply columns:**", list(sup.columns))
    # Check for duplicates
    if all(col in sup.columns for col in ['GasDay', 'FacilityName']):
        duplicates = sup.groupby(['GasDay', 'FacilityName']).size()
        duplicate_count = len(duplicates[duplicates > 1])
        st.sidebar.write(f"Duplicate facility-date entries: {duplicate_count}")
else:
    st.sidebar.error("❌ Supply DataFrame is EMPTY")

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
        st.stop()
    
    # Apply Yara adjustment
    model_adj = model.copy()
    model_adj["TJ_Demand"] = model_adj["TJ_Demand"] + (yara_val - 80)
    model_adj["Shortfall"] = model_adj["TJ_Available"] - model_adj["TJ_Demand"]
    
    # Create supply stack chart with duplicate handling
    if not sup.empty and 'TJ_Available' in sup.columns and 'FacilityName' in sup.columns and 'GasDay' in sup.columns:
        try:
            # CRITICAL FIX: Aggregate duplicate facility-date combinations
            sup_agg = sup.groupby(['GasDay', 'FacilityName'])['TJ_Available'].sum().reset_index()
            
            # Now pivot the aggregated data
            stack = sup_agg.pivot(index="GasDay", columns="FacilityName", values="TJ_Available")
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
                st.write("This could mean all supply data is historical (before today)")
        except Exception as e:
            st.error(f"Error creating supply chart: {e}")
            
            # Enhanced debug information
            st.write("**Debug Info:**")
            if not sup.empty:
                # Check for duplicates
                duplicates = sup.groupby(['GasDay', 'FacilityName']).size()
                duplicate_entries = duplicates[duplicates > 1]
                if not duplicate_entries.empty:
                    st.write(f"Found {len(duplicate_entries)} duplicate facility-date combinations:")
                    st.dataframe(duplicate_entries.head(10))
                    st.write("Sample duplicate data:")
                    first_duplicate = duplicate_entries.index[0]
                    sample_duplicates = sup[
                        (sup['GasDay'] == first_duplicate[0]) & 
                        (sup['FacilityName'] == first_duplicate[1])
                    ]
                    st.dataframe(sample_duplicates)
                else:
                    st.write("No duplicates found - different error cause")
                    st.write("Supply data sample:")
                    st.dataframe(sup.head())
    else:
        st.error("❌ Supply data missing required columns for stacked chart")
        st.write("**Required columns:** ['TJ_Available', 'FacilityName', 'GasDay']")
        if not sup.empty:
            st.write("**Available supply columns:**", list(sup.columns))
        else:
            st.write("**Supply DataFrame is empty**")
    
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

# Final debug summary
st.sidebar.write("**🎯 Status Summary:**")
st.sidebar.write(f"Dashboard loaded: {'✅' if not model.empty else '❌'}")
st.sidebar.write(f"Supply data: {'✅' if not sup.empty else '❌'}")
st.sidebar.write(f"Model has TJ_Available: {'✅' if not model.empty and 'TJ_Available' in model.columns else '❌'}")
st.sidebar.write(f"Model has TJ_Demand: {'✅' if not model.empty and 'TJ_Demand' in model.columns else '❌'}")
st.sidebar.write(f"Supply has required cols: {'✅' if not sup.empty and all(col in sup.columns for col in ['TJ_Available', 'FacilityName', 'GasDay']) else '❌'}")
