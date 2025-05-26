
  
# Alerting and Notification Plugins for InfluxDB 3
  
This plugin system provides alerting and notification capabilities for InfluxDB 3 through three complementary plugins: `scheduler`, `data write`, and `HTTP`. The `scheduler` and `data write` plugins detect alerting conditions and use the `HTTP` plugin to send notifications via various channels.  
  
## Prerequisites  
- **InfluxDB v3 Core/Enterprise**: latest.  
- **Python**: Version 3.10 or higher.  
  
## Files  
- `alerting_plugin.py`: The main plugin code containing handlers for `scheduler`, `data write`, and `HTTP`.  
  
## Features  
- **Scheduler Plugin**: Periodically checks for data presence (e.g., for deadman alerts) and sends notifications when conditions are met.  
- **Data Write Plugin**: Triggers on data writes to the database, checks threshold conditions, and sends notifications.  
- **HTTP Plugin**: Sends notifications via channels such as Slack, Discord, HTTP, SMS, or WhatsApp based on requests from other plugins.  
- **Multi-Channel Notifications**: Supports Slack, Discord, HTTP (POST), SMS, and WhatsApp.  
- **Customizable Messages**: Allows dynamic variables in notification text.  
- **Retry Logic**: Retries failed notifications with exponential backoff.  
- **Environment Variable Support**: Can be configured using environment variables (INFLUXDB3_AUTH_TOKEN, TWILIO_SID, and TWILIO_TOKEN).  
  
## Logging  
Logs are written to the `_internal` database in InfluxDB in the `system.processing_engine_logs` table. To view logs, use the following query:  
  
```bash  
influxdb3 query --database _internal "SELECT * FROM system.processing_engine_logs"
```
Example output:  
  
```text  
+-------------------------------+-----------------+--------------+----------------------------------------------------------------------------------------------------------+  
| event_time                    | trigger_name    | log_level    | log_text                                                                                                 |  
+-------------------------------+-----------------+--------------+----------------------------------------------------------------------------------------------------------+  
| 2025-05-14T16:31:10.033295886 | my_scheduler    | INFO         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Finished execution in 31ms 449us 193ns                            |  
| 2025-05-14T16:31:10.033275724 | my_scheduler    | ERROR        | [4726cf36-3b15-442e-bd9d-f9b768ad8781] No valid senders configured                                       |  
| 2025-05-14T16:31:10.033232792 | my_scheduler    | WARN         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Field temp not found in row                                       |  
| 2025-05-14T16:31:10.011881111 | some_scheduler  | INFO         | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Notification sent successfully                                    |  
| 2025-05-14T16:31:10.001837231 | some_scheduler  | INFO         | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Starting execution with scheduled time 2025-05-14 16:31:10 UTC    |  
| 2025-05-14T16:31:00.046641074 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Finished execution in 44ms 724us 139ns                            |  
| 2025-05-14T16:31:00.046623022 | my_scheduler    | ERROR        | [cd5caa89-47db-443c-9621-5f90a129a0cc] Failed to send SMS message after 3 attempts                       |  
| 2025-05-14T16:31:00.046579787 | some_scheduler  | ERROR        | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] No valid senders configured                                       |  
| 2025-05-14T16:31:00.025482558 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Notification sent successfully                                    |  
| 2025-05-14T16:31:00.001903138 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Starting execution with scheduled time 2025-05-14 16:31:00 UTC    |  
+-------------------------------+-----------------+--------------+----------------------------------------------------------------------------------------------------------+  
```
  
### Log Columns Description  
- **event_time**: Timestamp of the log event.  
- **trigger_name**: Name of the trigger that generated the log.  
- **log_level**: Severity level (`INFO`, `WARN`, `ERROR`, etc.).  
- **log_text**: Message describing the action or error.  
  
## Setup & Run  
  
### 1. Install & Run InfluxDB v3 Core/Enterprise  
- Download and install InfluxDB v3 Core/Enterprise.  
- Ensure the `plugins` directory exists; if not, create it:  
  ```bash  
  mkdir ~/.plugins 
  ```
- Place `alerting_plugin.py` in `~/.plugins/`.  
- Start InfluxDB 3 with the correct paths:  
  ```bash  
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins 
  ``` 
 
### 2. Download & Install InfluxDB 3 python packages used by plugin  
 ```bash  
 influxdb3 install package influxdb3-python  
 ```
  ```bash  
 influxdb3 install package httpx  
 ```
   ```bash  
 influxdb3 install package requests  
 ```
   ```bash  
 influxdb3 install package twilio  
 ```
  
## 2. Configure & Create Triggers  
  
## Scheduler Plugin  
The Scheduler Plugin performs periodic checks (e.g., for deadman alerts) and sends notifications when no data received.  
  
##### Arguments (Scheduler Mode)  
The following arguments are extracted from the `args` dictionary for the Scheduler Plugin:  
  
| Argument               | Description                                                                                                                               | Required | Example                                                                         |  
|------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|----------|---------------------------------------------------------------------------------|  
| `measurement`          | The InfluxDB table (measurement) to monitor.                                                                                              | Yes      | `"cpu"`                                                                         |  
| `senders`              | Dot-separated list of notification channels (e.g., `"slack.discord"`). Supported channels: `slack`, `discord`, `sms`, `whatsapp`, `http`. | Yes      | `"slack.discord"`                                                               |  
| `influxdb3_auth_token` | API token for your Influxdb3.                                                                                                             | Yes      | `"YOUR_API_TOKEN"`                                                              |  
| `window`               | Time window to check for missing data (e.g., `"5m"` for 5 minutes).                                                                       | Yes      | `"5m"`                                                                          |  
| `trigger_count`        | Number of consecutive failed checks before sending an alert.                                                                              | No       | `3` (default: `1`)                                                              |  
| `notification_text`    | Template for the notification message with variable `$table`, `$time_from`, `$time_to`.                                                   | No       | `"Deadman Alert: No data received from \$table from \$time_from to \$time_to."` |  
| `notification_path`    | URL path for your notification sending plugin (specified when creating an HTTP type trigger)                                              | No       | `some/path` (default: `notify`)                                                 |  
| `port_override`        | The port number where your influx accepts requests.                                                                                       | No       | `8182` (default: `8181`)                                                        |  

  
### Sender-Specific Arguments

This section documents all **sender-specific arguments** required when using the `senders` parameter. These arguments must be included in the `args` dictionary depending on which notification channels are selected.

Each supported sender has its own required and optional parameters.

---

#### Slack

| Argument            | Description                                    | Required | Example                             |
|---------------------|------------------------------------------------|----------|-------------------------------------|
| `slack_webhook_url` | Incoming webhook URL for Slack notifications.  | Yes      | `https://hooks.slack.com/...`       |
| `slack_headers`     | Optional headers as **base64-encoded string**. | No       | `{"Authorization": "Bearer ..."}`   |

---

#### Discord

| Argument               | Description                                    | Required | Example                                      |
|------------------------|------------------------------------------------|----------|----------------------------------------------|
| `discord_webhook_url`  | Incoming webhook URL for Discord.              | Yes      | `https://discord.com/api/webhooks/...`       |
| `discord_headers`      | Optional headers as **base64-encoded string**. | No       | `{"Authorization": "Bot ..."}`               |

---

#### HTTP (Custom Webhook)

| Argument           | Description                           | Required | Example                          |
|--------------------|---------------------------------------|----------|----------------------------------|
| `http_webhook_url` | Target webhook URL for HTTP alerts.   | Yes      | `https://example.com/webhook`    |
| `http_headers`     | Optional headers as **base64-encoded string**. | No       | `{"X-Custom": "value"}`          |

> ⚠️ **Important:** Plugin send only POST requests with body {"message": "notification_text"}.
---

#### SMS (via Twilio)

| Argument              | Description                                 | Required | Example                          |
|-----------------------|---------------------------------------------|----------|----------------------------------|
| `twilio_sid`          | Twilio Account SID                          | Yes      | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`|
| `twilio_token`        | Twilio Auth Token                           | Yes      | `your_auth_token`                |
| `twilio_to_number`    | Recipient phone number                      | Yes      | `+1234567890`                    |
| `twilio_from_number`  | Twilio sender phone number (verified)       | Yes      | `+19876543210`                   |

---

#### WhatsApp (via Twilio)

| Argument              | Description                                 | Required | Example                               |
|-----------------------|---------------------------------------------|----------|---------------------------------------|
| `twilio_sid`          | Twilio Account SID                          | Yes      | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`     |
| `twilio_token`        | Twilio Auth Token                           | Yes      | `your_auth_token`                     |
| `twilio_to_number`    | Recipient WhatsApp number                   | Yes      | `whatsapp:+1234567890`                |
| `twilio_from_number`  | Twilio WhatsApp sender number (sandbox)     | Yes      | `whatsapp:+19876543210`               |

---

> ⚠️ **Important:** When using multiple senders (e.g., `slack.sms`), make sure all required parameters for each specified sender are included in the `args` dictionary.

  
- **Example**:  
  ```bash  
  influxdb3 create trigger \
  --database mydb \
  --plugin-filename alerting_plugin.py \
  --trigger-spec "every:10s" \
  --trigger-arguments measurement=cpu,senders=slack,influxdb3_auth_token=YOUR_TOKEN,window=10s,trigger_count=3,notification_text="No data from \$table between \$time_from and \$time_to",slack_webhook_url="https://discord.com/api/webhooks/custom" \ scheduler_trigger 
  ```  



## Data Write Plugin  
The Data Write Plugin triggers on data writes to the database and checks for threshold conditions on specified fields.  
  
### Arguments (Data Write Mode)  
The following arguments are extracted from the `args` dictionary for the Data Write Plugin:  
  
| Argument                | Description                                                                                         | Required | Example                                                                                     |  
|-------------------------|-----------------------------------------------------------------------------------------------------|----------|---------------------------------------------------------------------------------------------|  
| `measurement`           | The InfluxDB table (measurement) to monitor.                                                        | Yes      | `"cpu"`                                                                                     |  
| `field_conditions`      | Conditions for triggering alerts (e.g., `temp>30:status==ok`).                                      | Yes      | `temp>30:status==ok`                                                                        |  
| `senders`               | Dot-separated list of notification channels.                                                        | Yes      | `"slack.discord"`                                                                           |  
| `influxdb3_auth_token`  | API token for your Influxdb3.                                                                       | Yes      | `"YOUR_API_TOKEN"`                                                                          |  
| `trigger_count`         | Number of times the condition must be met before sending an alert.                                  | No       | `2` (default: 1)                                                                            |  
| `notification_text`     | Template for the notification message with variable `$field`, `$op_sym`, `$compare_val`, `$actual`. | No       | `"InfluxDB 3 alert triggered. Condition \$field \$op_sym \$compare_val matched (\$actual)"` |  
| `notification_path`     | URL path for your notification sending plugin (specified when creating an HTTP type trigger)        | No       | `some/path` (default: `notify`)                                                             |  
| `port_override`         | The port number where your influx accepts requests.                                                 | No       | `8182` (default: `8181`)                                                                    |  
---
  
## Sender-Specific Arguments
 Same as for the Scheduler Plugin.  



- **Example**:  
  ```bash  
  influxdb3 create trigger \
  --database mydb \
  --plugin-filename alerting_plugin.py \
  --trigger-spec "all_tables" \
  --trigger-arguments measurement=cpu,senders=slack,field_conditions=temp>30:status==error,influxdb3_auth_token=YOUR_TOKEN,trigger_count=3,slack_webhook_url="https://discord.com/api/webhooks/custom" data_write_trigger 
  ```    


## HTTP Plugin  
The HTTP Plugin processes incoming HTTP requests to send notifications. Arguments are passed in the request body as JSON.  
  
##### Request Body Arguments (HTTP Mode)  
The JSON body for HTTP requests should include:  
  
| Argument              | Description                                                                 | Required | Example                           |  
|-----------------------|-----------------------------------------------------------------------------|----------|-----------------------------------|  
| `notification_text`   | The text of the notification message.                                       | Yes      | `"Test alert"`                    |  
| `senders_config`      | Configuration for each sender, including sender-specific arguments.         | Yes      | See below                         |  
  
- **senders_config**: A dictionary where keys are sender names and values are their configurations.    

- **Example HTTP Request**:  
  ```bash  
  curl -X POST http://localhost:8181/api/v3/engine/notify \ -H "Authorization: Bearer YOUR_TOKEN" \ -d '{"notification_text": "Test alert", "senders_config": {"slack": {"slack_webhook_url": "https://hooks.slack.com/services/..."}}}' ```  

## 3. Enable Triggers  
Enable the triggers to start the alerting processes:  
```bash  
influxdb3 enable trigger --database mydb scheduler_trigger
```  
  
## Important Notes  
- **Environment Variables**: Sensitive data like API tokens and Twilio credentials can be set via environment variables for security (e.g., `TWILIO_SID`, `INFLUXDB3_AUTH_TOKEN`). These take precedence over arguments in `args`.  
- **Retries**: The `HTTP` plugin retries failed notifications with exponential backoff.  

  
## Questions/Comments  
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).