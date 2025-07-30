| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database` | string | required | Database name where forecast results are written |
| `table` | string | required | Table name containing the historical time series data |
| `field` | string | required | Numeric field name to generate forecasts for |
| `output_table` | string | required | Table name where forecast predictions are stored |
| `forecast_periods` | integer | `24` | Number of future time periods to predict |
| `frequency` | string | `"H"` | Data frequency for the Prophet model. Valid values: H (hourly), D (daily), W (weekly), M (monthly) |
| `seasonality_mode` | string | `"additive"` | Seasonality model type. Valid values: additive, multiplicative |
| `confidence_interval` | float | `0.95` | Confidence level for prediction intervals. Range: 0.0 to 1.0 |
| `time_column` | string | `"time"` | Column name that contains timestamp values |
| `include_history` | boolean | `false` | Include historical data points in the forecast output |