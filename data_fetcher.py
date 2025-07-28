import os
import requests
import pandas as pd
from datetime import datetime

# Base URL for AEMO Gas Bulletin Board reports
GBB_BASE = "https://nemweb.com.au/Reports/Current/GBB/"

FILES = {
    "flows": "GasBBActualFlowStorageLast31.CSV",
    "mto_future": "GasBBMediumTermCapacityOutlookFuture.csv",
    "nameplate": "GasBBNameplateRatingCurrent.csv",
}

CACHE_DIR = "data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def _download(fname):
    try:
        url = GBB_BASE + fname
        response = requests.get(url, timeout=40)
        response.raise_for_status()

        text = response.text.strip().lower()
        if text.startswith("<!doctype html") or text.startswith("<html"):
            raise ValueError(f"{url} returned HTML page, not CSV data")

        path = os.path.join(CACHE_DIR, fname)
        with open(path, "wb") as f:
            f.write(response.content)
        return path

    except Exception as e:
        print(f"[ERROR] Failed to download {fname}: {e}")
        error_path = os.path.join(CACHE_DIR, fname)
        if os.path.exists(error_path):
            os.remove(error_path)
        raise

def _stale(path):
    if not os.path.exists(path):
        return True
    last_modified = datetime.utcfromtimestamp(os.path.getmtime(path))
    return (datetime.utcnow() - last_modified).days > 0

def fetch_csv(key, force=False):
    try:
        fname = FILES[key]
        fpath = os.path.join(CACHE_DIR, fname)
        
        if force or _stale(fpath):
            fpath = _download(fname)

        df = pd.read_csv(fpath)
        df.columns = df.columns.str.lower()
        return df

    except Exception as e:
        print(f"[ERROR] Could not load {key}: {e}")
        return pd.DataFrame()

def clean_nameplate(df):
    """Extract ALL facilities from nameplate data"""
    print(f"[DEBUG] Nameplate input: {df.shape}")
    
    if df.empty or 'capacityquantity' not in df.columns:
        return pd.DataFrame(columns=["FacilityName", "TJ_Nameplate"])
    
    result = df[['facilityname', 'capacityquantity']].copy()
    result.rename(columns={
        'facilityname': 'FacilityName',
        'capacityquantity': 'TJ_Nameplate'
    }, inplace=True)
    
    result = result.dropna()
    print(f"[DEBUG] Nameplate output: {result.shape} facilities")
    return result

def clean_mto(df):
    """Extract ALL facilities from MTO data and aggregate duplicates"""
    print(f"[DEBUG] MTO input: {df.shape}")
    
    if df.empty:
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available"])
    
    required_cols = ['facilityname', 'fromgasdate', 'outlookquantity']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        print(f"[WARNING] Missing MTO columns: {missing}")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available"])

    df['fromgasdate'] = pd.to_datetime(df['fromgasdate'], errors="coerce")
    result = df[['facilityname', 'fromgasdate', 'outlookquantity']].copy()
    result = result.dropna(subset=['fromgasdate'])
    
    result.rename(columns={
        'facilityname': 'FacilityName',
        'fromgasdate': 'GasDay',
        'outlookquantity': 'TJ_Available'
    }, inplace=True)
    
    # Aggregate duplicates by summing capacity for same facility-date
    result = result.groupby(['FacilityName', 'GasDay'])['TJ_Available'].sum().reset_index()
    
    print(f"[DEBUG] MTO output: {result.shape} records (after deduplication)")
    return result

def build_supply_profile():
    """Build supply profile using ALL facilities"""
    nameplate = clean_nameplate(fetch_csv("nameplate"))
    mto = clean_mto(fetch_csv("mto_future"))

    print(f"[DEBUG] Supply building - Nameplate: {nameplate.shape}, MTO: {mto.shape}")

    if nameplate.empty and mto.empty:
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available", "TJ_Nameplate"])
    
    # If no MTO data, create future dates with nameplate capacity
    if mto.empty and not nameplate.empty:
        dates = pd.date_range(start=pd.Timestamp.now(), periods=365, freq='D')
        supply_list = []
        for _, facility in nameplate.iterrows():
            for date in dates:
                supply_list.append({
                    'FacilityName': facility['FacilityName'],
                    'GasDay': date,
                    'TJ_Available': facility['TJ_Nameplate'],
                    'TJ_Nameplate': facility['TJ_Nameplate']
                })
        return pd.DataFrame(supply_list)

    # If no nameplate data, use MTO only
    if nameplate.empty and not mto.empty:
        mto['TJ_Nameplate'] = mto['TJ_Available']
        return mto

    # Merge nameplate and MTO
    supply = mto.merge(nameplate, on="FacilityName", how="left")
    supply["TJ_Available"] = supply["TJ_Available"].fillna(supply["TJ_Nameplate"])
    
    print(f"[DEBUG] Final supply profile: {supply.shape}")
    return supply

def build_demand_profile():
    """Build demand profile from flows data"""
    flows = fetch_csv("flows")
    print(f"[DEBUG] Demand building from flows: {flows.shape}")
    
    if flows.empty or 'gasdate' not in flows.columns or 'demand' not in flows.columns:
        return pd.DataFrame(columns=["GasDay", "TJ_Demand"])

    flows['gasdate'] = pd.to_datetime(flows['gasdate'], errors="coerce")
    flows = flows.dropna(subset=['gasdate'])
    
    # Aggregate all demand by date
    demand = flows.groupby('gasdate')['demand'].sum().reset_index()
    demand.rename(columns={'gasdate': 'GasDay', 'demand': 'TJ_Demand'}, inplace=True)
    
    print(f"[DEBUG] Demand profile: {demand.shape}")
    return demand

def get_model():
    """Main function returning supply and demand model"""
    sup = build_supply_profile()
    dem = build_demand_profile()

    print(f"[DEBUG] get_model - Supply: {sup.shape}, Demand: {dem.shape}")

    if dem.empty:
        return sup, dem

    if sup.empty:
        dem['TJ_Available'] = 0
        dem['Shortfall'] = dem['TJ_Available'] - dem['TJ_Demand']
        return sup, dem

    # Aggregate total daily supply and merge with demand
    total_supply = sup.groupby("GasDay")["TJ_Available"].sum().reset_index()
    model = dem.merge(total_supply, on="GasDay", how="left")
    model['TJ_Available'] = model['TJ_Available'].fillna(0)
    model["Shortfall"] = model["TJ_Available"] - model["TJ_Demand"]
    
    print(f"[DEBUG] Final model: {model.shape}, columns: {list(model.columns)}")
    return sup, model
