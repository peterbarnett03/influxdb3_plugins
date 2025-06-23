import pandas as pd
from datetime import datetime
import json
def process_request(influxdb3_local, query_parameters, request_headers, request_body, args=None):
    url = "https://raw.githubusercontent.com/facebook/prophet/main/examples/example_wp_log_peyton_manning.csv"
    df = pd.read_csv(url)

    count = 0
    for _, row in df.iterrows():
        # Convert the 'ds' column (string) to datetime and then to nanoseconds
        ts = pd.to_datetime(row["ds"])
        ts_ns = int(ts.timestamp() * 1e9)

        line = LineBuilder("peyton_views")
        line.time_ns(ts_ns)
        line.float64_field("pageviews", row["y"])
        influxdb3_local.write(line)
        count += 1

    influxdb3_local.info(f"Wrote {count} rows to 'peyton_views'")
    return (
    200,
    {"Content-Type": "application/json"},
    json.dumps({"status": "success", "rows_written": count})
    )
