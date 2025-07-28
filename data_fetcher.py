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
    # Debug: Check what facility types actually exist
    if not df.empty and 'facilitytype' in df.columns:
        print(f"[DEBUG] Nameplate facility types: {df['facilitytype'].unique()}")
    
    # Look for production facilities - try different possible values
    production_variants = ['production', 'Production', 'PRODUCTION', 'prod']
    prod_mask = df['facilitytype'].isin(production_variants) if 'facilitytype' in df.columns else pd.Series([False] * len(df))
    
    if not prod_mask.any():
        print(f"[WARNING] No production facilities found in nameplate data")
        print(f"Available facility types: {df['facilitytype'].unique() if 'facilitytype' in df.columns else 'Column missing'}")
        return pd.DataFrame(columns=["FacilityName", "TJ_Nameplate"])

    prod = df[prod_mask].copy()
    
    # Handle capacity quantity column
    capacity_col = None
    for col in ['capacityquantity', 'capacity', 'nameplaterating']:
        if col in prod.columns:
            capacity_col = col
            break
    
    if capacity_col is None:
        print(f"[WARNING] No capacity column found in nameplate data")
        return pd.DataFrame(columns=["FacilityName", "TJ_Nameplate"])
    
    result = prod[['facilityname', capacity_col]].copy()
    result.rename(columns={
        'facilityname': 'FacilityName',
        capacity_col: 'TJ_Nameplate'
    }, inplace=True)
    
    print(f"[DEBUG] Cleaned nameplate: {len(result)} facilities")
    return result

def clean_mto(df):
    # Debug: Check facility types in MTO data
    if not df.empty and 'facilitytype' in df.columns:
        print(f"[DEBUG] MTO facility types: {df['facilitytype'].unique()}")
    
    # Look for production facilities
    production_variants = ['production', 'Production', 'PRODUCTION', 'prod']
    prod_mask = df['facilitytype'].isin(production_variants) if 'facilitytype' in df.columns else pd.Series([False] * len(df))
    
    if not prod_mask.any():
        print(f"[WARNING] No production facilities found in MTO data")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available"])

    # Handle date column
    date_col = None
    for col in ['fromgasdate', 'gasdate', 'date']:
        if col in df.columns:
            date_col = col
            break
    
    if date_col is None:
        print(f"[WARNING] No date column found in MTO data")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available"])
    
    # Handle capacity column
    capacity_col = None
    for col in ['outlookquantity', 'capacity', 'quantity']:
        if col in df.columns:
            capacity_col = col
            break
    
    if capacity_col is None:
        print(f"[WARNING] No capacity column found in MTO data")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available"])

    prod = df[prod_mask].copy()
    prod[date_col] = pd.to_datetime(prod[date_col], errors="coerce")
    prod = prod.dropna(subset=[date_col])
    
    result = prod[['facilityname', date_col, capacity_col]].copy()
    result.rename(columns={
        'facilityname': 'FacilityName',
        date_col: 'GasDay',
        capacity_col: 'TJ_Available'
    }, inplace=True)
    
    print(f"[DEBUG] Cleaned MTO: {len(result)} records")
    return result

def build_supply_profile():
    nameplate = clean_nameplate(fetch_csv("nameplate"))
    mto = clean_mto(fetch_csv("mto_future"))

    print(f"[DEBUG] Nameplate shape: {nameplate.shape}, MTO shape: {mto.shape}")

    if nameplate.empty and mto.empty:
        print("[WARNING] Both nameplate and MTO data empty")
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available", "TJ_Nameplate"])
    
    if mto.empty:
        # If no MTO data, create dummy future dates with nameplate capacity
        print("[WARNING] No MTO data, using nameplate only")
        if not nameplate.empty:
            dates = pd.date_range(start=pd.Timestamp.now(), periods=30, freq='D')
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
        return pd.DataFrame(columns=["FacilityName", "GasDay", "TJ_Available", "TJ_Nameplate"])

    if nameplate.empty:
        # If no nameplate data, use MTO data only
        print("[WARNING] No nameplate data, using MTO only")
        mto['TJ_Nameplate'] = mto['TJ_Available']  # Use MTO as nameplate
        return mto

    # Merge nameplate and MTO data
    supply = mto.merge(nameplate, on="FacilityName", how="left")
    supply["TJ_Available"] = supply["TJ_Available"].fillna(supply["TJ_Nameplate"])
    
    print(f"[DEBUG] Final supply profile: {supply.shape}")
    return supply

def build_demand_profile():
    flows = fetch_csv("flows")
    
    # Handle different possible date column names
    date_col = None
    for col in ['gasdate', 'date', 'gasday']:
        if col in flows.columns:
            date_col = col
            break
    
    if date_col is None:
        print("[WARNING] No date column found in flows data")
        return pd.DataFrame(columns=["GasDay", "TJ_Demand"])

    flows[date_col] = pd.to_datetime(flows[date_col], errors="coerce")
    flows = flows.dropna(subset=[date_col])
    
    # Aggregate demand by date (sum all demand across facilities)
    if 'demand' in flows.columns:
        demand = flows.groupby(date_col)['demand'].sum().reset_index()
        demand.rename(columns={date_col: 'GasDay', 'demand': 'TJ_Demand'}, inplace=True)
        print(f"[DEBUG] Demand profile: {demand.shape}")
        return demand
    else:
        print("[WARNING] No 'demand' column found in flows data")
        return pd.DataFrame(columns=["GasDay", "TJ_Demand"])

def get_model():
    sup = build_supply_profile()
    dem = build_demand_profile()

    print(f"[DEBUG] get_model - Supply: {sup.shape}, Demand: {dem.shape}")

    if dem.empty:
        print("[WARNING] No demand data - model incomplete")
        return sup, dem

    if sup.empty:
        print("[WARNING] No supply data - creating model with demand only")
        dem['TJ_Available'] = 0  # No supply available
        dem['Shortfall'] = dem['TJ_Available'] - dem['TJ_Demand']
        return sup, dem

    # Aggregate total daily supply
    total_supply = sup.groupby("GasDay")["TJ_Available"].sum().reset_index()
    
    # Merge with demand and calculate shortfall
    model = dem.merge(total_supply, on="GasDay", how="left")
    model['TJ_Available'] = model['TJ_Available'].fillna(0)  # Fill missing supply with 0
    model["Shortfall"] = model["TJ_Available"] - model["TJ_Demand"]
    
    print(f"[DEBUG] Final model: {model.shape}, columns: {list(model.columns)}")
    return sup, model
