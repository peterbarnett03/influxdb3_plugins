import pandas as pd
import plotly.graph_objects as go

def process_request(influxdb3_local, query_parameters, request_headers, request_body, args=None):
    # Query historical data
    history_query = """
        SELECT time, pageviews
        FROM peyton_views
        ORDER BY time
    """
    history_results = influxdb3_local.query(history_query)
    if not history_results:
        influxdb3_local.warn("No historical data found in 'peyton_views'")
        return (500, {"Content-Type": "text/plain"}, "No historical data available")

    history_df = pd.DataFrame(history_results)
    history_df["time"] = pd.to_datetime(history_df["time"])

    # Query forecast data
    forecast_query = """
        SELECT time, yhat, yhat_lower, yhat_upper
        FROM prophet_forecast
        ORDER BY time
    """
    forecast_results = influxdb3_local.query(forecast_query)
    if not forecast_results:
        influxdb3_local.warn("No forecast data found in 'prophet_forecast'")
        return (500, {"Content-Type": "text/plain"}, "No forecast data available")

    forecast_df = pd.DataFrame(forecast_results)
    forecast_df["time"] = pd.to_datetime(forecast_df["time"])

    # Plot using Plotly
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=history_df["time"],
        y=history_df["pageviews"],
        name="Historical",
        mode="lines",
        line=dict(color="blue")
    ))

    fig.add_trace(go.Scatter(
        x=forecast_df["time"],
        y=forecast_df["yhat"],
        name="Forecast",
        mode="lines",
        line=dict(color="green")
    ))

    fig.add_trace(go.Scatter(
        x=forecast_df["time"],
        y=forecast_df["yhat_upper"],
        name="Upper Bound",
        mode="lines",
        line=dict(width=0),
        showlegend=False
    ))

    fig.add_trace(go.Scatter(
        x=forecast_df["time"],
        y=forecast_df["yhat_lower"],
        name="Lower Bound",
        mode="lines",
        fill='tonexty',
        fillcolor='rgba(0,255,0,0.1)',
        line=dict(width=0),
        showlegend=False
    ))

    fig.update_layout(
        title="Peyton Manning Pageviews Forecast",
        xaxis_title="Date",
        yaxis_title="Pageviews",
        template="plotly_white"
    )

    html = fig.to_html(full_html=False)

    return (
        200,
        {"Content-Type": "text/html"},
        html
    )
