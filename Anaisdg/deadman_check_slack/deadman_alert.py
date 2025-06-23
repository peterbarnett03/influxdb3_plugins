import time
import json
import urllib.request

# Define the plugin function
def process_scheduled_call(influxdb3_local, call_time, args=None):
    # Configuration
    table_name = args.get("table", "sensor_data") if args else "sensor_data"
    threshold_minutes = int(args.get("threshold_minutes", 5)) if args else 5
    slack_webhook = args.get(
        "slack_webhook",
        "https://hooks.slack.com/services/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"
    )

    # Query to check for data in the past N minutes
    query = f"""
        SELECT * FROM {table_name}
        WHERE time > now() - INTERVAL '{threshold_minutes} minutes'
        LIMIT 1
    """
    results = influxdb3_local.query(query)

    if not results:
        influxdb3_local.warn(f"No data found in '{table_name}' in the last {threshold_minutes} minutes. Sending alert.")
        send_slack_alert(slack_webhook, table_name, threshold_minutes)
    else:
        influxdb3_local.info(f"Data exists in '{table_name}' in the last {threshold_minutes} minutes.")

# Send a Slack alert
def send_slack_alert(webhook_url, table, minutes):
    message = {
        "text": f":rotating_light: *Deadman Alert*: No data received from `{table}` in the last {minutes} minutes."
    }
    data = json.dumps(message).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req) as response:
            if 200 <= response.status < 300:
                print(f"Slack alert sent successfully for table {table}")
            else:
                print(f"Failed to send Slack alert: {response.status}")
    except Exception as e:
        print(f"Error sending Slack alert: {e}")