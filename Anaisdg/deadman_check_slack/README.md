# Deadman Alert Plugin for InfluxDB 3 Core

This plugin is a **deadman alert** for InfluxDB 3 Core using the Python Processing Engine. It checks if a specific table has received any data within a configured time window. If no data is found, it sends a Slack notification to alert you that something might be wrong with your data pipeline, devices, or systems.

## 🔍 What It Does

-	Runs on a schedule (e.g., every 5 minutes)
-	Queries a specified table to check for recent writes
-	If no data was written within the threshold (e.g., past 5 minutes), sends a message to Slack
-	Keeps you aware of silent failures or inactive data sources

## 📦 How It Works

This plugin uses the `process_scheduled_call` trigger to:

1.	Run on a fixed schedule (like `every:5m`)
2.	Query the configured table to see if any data arrived recently
3.	If not, send a message to a configured Slack webhook URL

## ⚙️ Setup

### 1. Save the Plugin

Save the file as `deadman_alert.py` in your configured plugin directory (e.g., `/path/to/plugins/`).

### 2. Create a Trigger

```bash
influxdb3 create trigger \
  --trigger-spec "every:1m" \
  --plugin-filename "deadman_check_slack/deadman_alert.py" \
  --trigger-arguments table=sensor_data,threshold_minutes=5,slack_webhook=https://hooks.slack.com/services/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 \
  --database my_database \
  sensor_deadman
```

---

### 🔧 Trigger Arguments

| Argument            | Description                                    | Default        |
|---------------------|------------------------------------------------|----------------|
| `table`             | The table to monitor for recent writes         | `sensor_data`  |
| `threshold_minutes` | How far back to look for new data (in minutes) | `5`            |
| `slack_webhook`     | Slack webhook URL to send alerts to            | **(required)** |

> You can adjust the `--trigger-spec` to run more or less frequently.

---

### 🔔 Example Slack Message

> 🚨 *Deadman Alert*: No data received from `sensor_data` in the last 5 minutes.

---

### ✅ Requirements

-	InfluxDB 3 Core with the Processing Engine enabled  
-	Python plugin support  
-	A Slack webhook URL (can be created [here](https://api.slack.com/messaging/webhooks)) or you can use https://hooks.slack.com/services/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, which is a public webhook in the #notifications-testing channel in InfluxCommunity Slack.

---
