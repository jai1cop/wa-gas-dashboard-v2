import os
import requests
import pandas as pd
from datetime import datetime

# Base URL for AEMO Gas Bulletin Board reports
GBB_BASE = "https://nemweb.com.au/Reports/Current/GBB/"

# CSV filenames for key datasets
FILES = {
    "flows": "GasBBActualFlowStorageLast31.CSV",
    "mto_future": "GasBBMediumTermCapacityOutlookFuture.csv",
    "nameplate": "GasBBNameplateRatingCurrent.csv",
}

# Local cache directory for downloads
CACHE_DIR = "data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def _download(fname):
    """Download CSV file from AEMO GBB website and save locally."""
    try:
        url = GBB_BASE + fname
        response = requests.get(url, timeout=40)
        response.raise_for_status()

        # Validate it's a CSV, not HTML error page
        text = response.text.strip().lower()
        if text.startswith("<!doctype html") or text.startswith("<html"):
            raise ValueError(f"{url} returned HTML page, not CSV data")

        path = os.path.join(CACHE_DIR, fname)
        with open(path, "wb") as f:
            f.write(response.content)
        return path

    except Exception as e:
        print(f"[ERROR] Failed to download {fname}: {e}")
        # Clean up any partial files
        error_path = os.path.join(CACHE_DIR, fname)
        if os.path.exists(error_path):
            os.remove(error_path)
        raise

def _stale(path):
    """Check if cached file is older than 1 day."""
    if not os.path.exists(path):
        return True
    last_modified = datetime.utcfromtimestamp(os.path.getmtime(path))
    return (datetime.utcnow() - last_modified).days > 0

def fetch_csv(key, force=False):
    """Retrieve CSV data with caching."""
    try:
        fname = FILES[key]
        fpath = os.path.join(CACHE_DIR, fname)
        
        if force or _stale(fpath):
            fpath = _download(fname)

        df = pd.read_csv(fpath)
        df.columns = df.columns.str.lower()  # Handle case variations
        return df

    except Exception as e:
        print(f"[ERROR] Could not load {key}: {e}")
        # Return empty DataFrame with expected columns
        if key == "nameplate":
            return pd.DataFrame(columns=["facilityname", "facilitytype", "nameplaterating"])
        elif key == "mto_future":
            return pd.DataFrame(columns=["facilityname", "facilitytype", "gasday", "capacity"])
        elif key == "flows":
            return pd.DataFrame(columns=["gasday", "zonetype", "zonename", "quantity"])
        return pd.DataFrame()

def clean_nameplate(df):
    """Extract production facility nameplate ratings."""
    required = {"facilityname", "facilitytype", "nameplaterating"}
    if not required.issubset(df.columns):
        print(f"[WARNING] Missing nameplate columns: {required - set(df.columns)}")
        return pd.DataFrame(columns=["FacilityName", "TJ_Nameplate"])

    prod = df[df["facilitytype"] == "production"].copy()
    prod = prod[["facilityname", "nameplaterating"]]
    prod.rename(columns={
        "facilityname": "FacilityName", 
        "nameplaterating": "TJ_Nameplate"
    }, inplace=True)
    return prod

def clean_mto(df):
    """Extract medium-term capacity outlook for production facilities."""
    required = {"facilityname", "facilitytype", "gasday", "capacity"}
    if not required.issubset(df.columns):
        print(f"[WARNING] Missing MTO columns: {required - set(df.columns)}")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available"])

    df["gasday"] = pd.to_datetime(df["gasday"], errors="coerce")
    prod = df[df["facilitytype"] == "production"].copy()
    prod = prod[["facilityname", "gasday", "capacity"]].dropna(subset=["gasday"])
    prod.rename(columns={
        "facilityname": "FacilityName",
        "gasday": "GasDay", 
        "capacity": "TJ_Available"
    }, inplace=True)
    return prod

def build_supply_profile():
    """Build complete supply profile with nameplate and constraints."""
    nameplate = clean_nameplate(fetch_csv("nameplate"))
    mto = clean_mto(fetch_csv("mto_future"))

    if nameplate.empty or mto.empty:
        print("[WARNING] Empty supply data")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available", "TJ_Nameplate"])

    supply = mto.merge(nameplate, on="FacilityName", how="left")
    supply["TJ_Available"] = supply["TJ_Available"].fillna(supply["TJ_Nameplate"])
    return supply

def build_demand_profile():
    """Build WA demand profile from flow data."""
    flows = fetch_csv("flows")
    required = {"gasday", "zonetype", "zonename", "quantity"}
    if not required.issubset(flows.columns):
        print(f"[WARNING] Missing flow columns: {required - set(flows.columns)}")
        return pd.DataFrame(columns=["GasDay", "TJ_Demand"])

    flows["gasday"] = pd.to_datetime(flows["gasday"], errors="coerce")
    wa_demand = flows[
        (flows["zonetype"] == "demand") & 
        (flows["zonename"] == "whole wa")
    ]
    
    demand = wa_demand.groupby("gasday")["quantity"].sum().reset_index()
    demand.rename(columns={"gasday": "GasDay", "quantity": "TJ_Demand"}, inplace=True)
    demand = demand.dropna(subset=["GasDay"])
    return demand

def get_model():
    """
    Main function: Returns supply and demand model data.
    
    Returns:
        sup (DataFrame): Supply by facility and date
        model (DataFrame): Daily supply, demand, and shortfall
    """
    sup = build_supply_profile()
    dem = build_demand_profile()

    if sup.empty or dem.empty:
        print("[WARNING] Incomplete data - returning empty")
        return sup, dem

    # Aggregate total daily supply
    total_supply = sup.groupby("GasDay")["TJ_Available"].sum().reset_index()
    
    # Merge with demand and calculate shortfall
    model = dem.merge(total_supply, on="GasDay", how="left")
    model["Shortfall"] = model["TJ_Available"] - model["TJ_Demand"]
    
    return sup, model

# Test function for debugging
def test_connection():
    """Test AEMO data connectivity."""
    try:
        print("Testing AEMO connection...")
        nameplate = fetch_csv("nameplate", force=True)
        print(f"✅ Nameplate data: {nameplate.shape[0]} facilities")
        
        flows = fetch_csv("flows", force=True)
        print(f"✅ Flow data: {flows.shape[0]} records")
        
        sup, model = get_model()
        print(f"✅ Model data: {model.shape[0]} days")
        return True
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False
