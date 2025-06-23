import pandas as pd
from prophet import Prophet

def process_scheduled_call(influxdb3_local, call_time, args=None):
    influxdb3_local.info("Running Prophet forecast on 'peyton_views'")

    # Query data from InfluxDB
    query = """
        SELECT time AS ds, pageviews AS y
        FROM peyton_views
        ORDER BY time
    """
    results = influxdb3_local.query(query)

    if not results:
        influxdb3_local.warn("No data found in 'peyton_views'")
        return

    # Create DataFrame for Prophet
    df = pd.DataFrame(results)
    df["ds"] = pd.to_datetime(df["ds"])

    # Fit the Prophet model
    m = Prophet()
    m.fit(df)

    # Forecast 365 days into the future
    future = m.make_future_dataframe(periods=365)
    forecast = m.predict(future)

    last = forecast.iloc[-1]

    for _, row in forecast.iterrows():
        ts_ns = int(pd.to_datetime(row["ds"]).timestamp() * 1e9)
    
        line = LineBuilder("prophet_forecast")
        line.time_ns(ts_ns)
        line.string_field("forecast_day", str(row["ds"]))
        line.float64_field("yhat", row["yhat"])
        line.float64_field("yhat_lower", row["yhat_lower"])
        line.float64_field("yhat_upper", row["yhat_upper"])
        influxdb3_local.write(line)
    
    influxdb3_local.info(
    f"Forecast complete for {str(last['ds'])}: yhat={last['yhat']:.2f}"
    )
