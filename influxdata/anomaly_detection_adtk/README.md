| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database` | string | required | Target database name for anomaly detection results |
| `table` | string | required | Source table name containing time series data |
| `field` | string | required | Numeric field name to analyze for anomalies |
| `output_table` | string | required | Destination table name for anomaly detection results |
| `detector_type` | string | `"IsolationForestAD"` | Anomaly detection algorithm type (IsolationForestAD, LocalOutlierFactorAD, OneClassSVMAD) |
| `contamination` | float | `0.1` | Expected proportion of anomalies in the dataset (0.0 to 0.5) |
| `window_size` | integer | `10` | Number of data points to include in detection window |
| `time_column` | string | `"time"` | Column name containing timestamp values |