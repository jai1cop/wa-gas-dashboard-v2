# wa-gas-dashboard-v2
# WA Gas Supply & Demand Dashboard

A real-time Western Australia gas market intelligence dashboard that integrates with AEMO Gas Bulletin Board data.

## Features

- **Real-time AEMO data integration** - Automatic daily refresh of official gas market data
- **Interactive supply visualization** - Stacked area chart showing facility-level capacity
- **Demand modeling** - Historical patterns with Yara Pilbara Fertilisers scenario planning
- **Market balance analysis** - Daily supply-demand gap identification with shortfall alerts
- **Automated data pipeline** - Handles AEMO format changes and connectivity issues

## Usage

1. Visit the deployed dashboard
2. Use the Yara consumption slider (0-100 TJ/day) to model market impact
3. Click "Refresh AEMO Data" to force data updates
4. Monitor supply charts for facility outages and constraints
5. Review daily balance table for detailed market conditions

## Data Sources

- GasBBActualFlowStorageLast31.CSV (historical flows)
- GasBBMediumTermCapacityOutlookFuture.csv (capacity constraints)
- GasBBNameplateRatingCurrent.csv (facility ratings)
