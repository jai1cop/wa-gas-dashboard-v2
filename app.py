import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config("WA Gas Dashboard", layout="wide")
st.title("WA Gas Supply & Demand Dashboard")

# Test with sample data first
sample_data = {
    'Date': pd.date_range('2025-07-28', periods=30),
    'Supply': [1800 + i*5 for i in range(30)],
    'Demand': [1600 + i*3 for i in range(30)]
}

df = pd.DataFrame(sample_data)
df['Balance'] = df['Supply'] - df['Demand']

# Simple chart
fig = px.line(df, x='Date', y=['Supply', 'Demand'], 
              title="WA Gas Supply vs Demand")
st.plotly_chart(fig, use_container_width=True)

# Balance chart
fig2 = px.bar(df, x='Date', y='Balance',
              color=df['Balance'] > 0,
              color_discrete_map={True: 'green', False: 'red'},
              title="Daily Supply-Demand Balance")
st.plotly_chart(fig2, use_container_width=True)

st.success("✅ Basic dashboard working! Ready to add real AEMO data.")
