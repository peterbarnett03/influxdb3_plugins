# Threshold and deadman checks Plugin for InfluxDB 3

This plugin system provides checks capabilities for InfluxDB 3 through two complementary plugins: `scheduler` and `data write`. These plugins detect checks conditions and use the **Notification Sender Plugin for InfluxDB 3** to dispatch notifications via various channels.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: with the Processing Engine enabled.
- **Table schema**: The plugin assumes that the table schema is already defined in the database, as it relies on this schema to retrieve field and tag names required for processing.
- **Notification Sender Plugin for InfluxDB 3**: This plugin is required for sending notifications. [Link to Notification Sender Plugin](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/notifier).

## Files
- `threshold_deadman_checks_plugin.py`: The main plugin code containing handlers for `scheduler` and `data write`.

## Features
- **Scheduler Plugin**: Periodically checks for data presence (e.g., for deadman alerts) or evaluates aggregation-based conditions and sends notifications when conditions are met.
- **Data Write Plugin**: Triggers on data writes to the database, checks threshold conditions, and sends notifications.
- **Args Overriding**: Allows overriding arguments for scheduler and data write types via TOML file (env var `PLUGIN_DIR` and `config_file_path` parameter should be set, see toml files example on [Git](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/threshold_deadman_checks). Override args parameter in handler function). The `config_file_path` must be specified as a path relative to the directory defined by PLUGIN_DIR.
- **Multi-Channel Notifications**: Notifications are sent via the Notification Sender Plugin, supporting Slack, Discord, HTTP, SMS, or WhatsApp.
- **Customizable Messages**: Allows dynamic variables in notification text.
- **Retry Logic**: Retries failed notifications with exponential backoff.
- **Environment Variable Support**: Can be configured using environment variables (e.g., `INFLUXDB3_AUTH_TOKEN`).

## Logging
Logs are stored in the `_internal` database (or the database where the trigger is created) in the `system.processing_engine_logs` table. To view logs, use the following query:

```bash
influxdb3 query --database _internal "SELECT * FROM system.processing_engine_logs"
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
- Place `threshold_deadman_checks_plugin.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package requests
```

### 3. Install and Configure the Notification Sender Plugin
- Ensure the [Notification Sender Plugin for InfluxDB 3](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/notifier) is installed and configured. This plugin is **required** for sending notifications via Slack, Discord, HTTP, SMS, or WhatsApp. The Notification Sender Plugin must be properly installed and configured for the alerting system to function.

## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin performs periodic checks, including deadman alerts and aggregation-based threshold checks, and sends notifications when conditions are met.

#### Arguments (Scheduler Mode)
The following arguments are extracted from the `args` dictionary for the Scheduler Plugin:

| Argument                      | Description                                                                                                                                            | Required | Example                                                                                                                                   |
|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|----------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `measurement`                 | The InfluxDB table (measurement) to monitor.                                                                                                           | Yes      | `"cpu"`                                                                                                                                   |
| `senders`                     | Dot-separated list of notification channels (e.g., `"slack.discord"`). Supported channels: `slack`, `discord`, `sms`, `whatsapp`, `http`.              | Yes      | `"slack.discord"`                                                                                                                         |
| `influxdb3_auth_token`        | API token for your InfluxDB 3 instance. Can be set via environment variable `INFLUXDB3_AUTH_TOKEN`.                                                    | No       | `"YOUR_API_TOKEN"`                                                                                                                        |
| `window`                      | Time window to check for data (e.g., `"5m"` for 5 minutes).                                                                                            | Yes      | `"5m"`                                                                                                                                    |
| `interval`                    | Time interval for aggregation (e.g., `10min`, `2s`, `1h`). Used in `DATE_BIN` for aggregation-based checks.                                            | No       | `10min` (default: `5min`)                                                                                                                 |
| `trigger_count`               | Number of consecutive failed checks before sending an alert.                                                                                           | No       | `3` (default: `1`)                                                                                                                        |
| `notification_deadman_text`   | Template for deadman notification message with variables `$table`, `$time_from`, `$time_to`.                                                           | No       | `"Deadman Alert: No data received from \$table from \$time_from to \$time_to."`                                                           |
| `notification_threshold_text` | Template for threshold notification message with variables `$level`, `$table`, `$field`, `$aggregation`, `$op_sym`, `$compare_val`, `$actual`, `$row`. | No       | `"[$level] Threshold Alert on table \$table: \$aggregation of \$field \$op_sym \$compare_val (actual: \$actual) — matched in row \$row."` |
| `notification_path`           | URL path for the notification sending plugin (specified when creating an HTTP type trigger).                                                           | No       | `some/path` (default: `notify`)                                                                                                           |
| `port_override`               | The port number where InfluxDB accepts requests.                                                                                                       | No       | `8182` (default: `8181`)                                                                                                                  |
| `deadman_check`               | Boolean flag to enable deadman checks. If `True`, the plugin will check for the absence of data. Default is False.                                     | No       | `True` or `False`                                                                                                                         |
| `field_aggregation_values`    | Aggregation conditions for threshold checks (e.g., `field:avg@">=10-INFO"$field2:min@"<5.0-WARN"`).                                                    | No       | `field:avg@">=10-ERROR"\$field2:min@"<5.0-INFO"`                                                                                          |
| `config_file_path`            | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                                                                    | No       | `'example.toml'`                                                                                                                          |

#### Aggregation-Based Checks
The Scheduler Plugin supports aggregation-based threshold checks. Use the `field_aggregation_values` parameter to define conditions on aggregated values (e.g., `avg`, `min`, `max`, `count`, `sum`, `derivative`, `median`. The format is:
- `field:aggregation@"operator value-level"` (e.g., `temp:avg@">=30-INFO"`).
- Multiple conditions are separated by `$` (e.g., `temp:avg@">=30-INFO"$status:count@">=5-ERROR"`).

#### The `row` Parameter in Notifications
In threshold notifications, the `row` variable represents a unique combination of the table name, level, tag names, and tag values (e.g., `cpu:level:host=server1:region=eu`). This ensures that alerts are triggered only when the condition is met for a specific combination of tags, and the `trigger_count` threshold must be reached independently for each unique `row`.

#### Sender-Specific Configurations in `senders_config`
Depending on the channels specified in `senders`, additional arguments are required to configure each notification sender. These arguments are passed as part of the trigger configuration and are used by the Notification Sender Plugin to dispatch notifications.

- **Slack**:
  - `slack_webhook_url` (string): The webhook URL provided by Slack for sending messages to a specific channel. Obtain this from your Slack workspace's app settings.
  - `slack_headers` (string, optional): Base64-encoded HTTP headers for additional customization (e.g., `{"Authorization": "Bearer ..."}` encoded in base64). Useful for advanced authentication or custom integrations.
  - Example: `"slack_webhook_url=https://hooks.slack.com/services/..."`.

- **Discord**:
  - `discord_webhook_url` (string): The webhook URL provided by Discord for posting messages to a specific channel. Create this in your Discord server settings under Integrations.
  - `discord_headers` (string, optional): Base64-encoded HTTP headers for additional customization, similar to Slack.
  - Example: `"discord_webhook_url=https://discord.com/api/webhooks/..."`.

- **HTTP**:
  - `http_webhook_url` (string): A custom webhook URL for sending HTTP POST requests. This can be any endpoint that accepts a JSON payload.
  - `http_headers` (string, optional): Base64-encoded HTTP headers for authentication or customization (e.g., `{"Content-Type": "application/json"}` encoded in base64).
  - Note: The plugin sends a POST request with a JSON body in the format `{"message": "notification_text"}`.
  - Example: `"http_webhook_url=https://example.com/webhook"`.

- **SMS** (via Twilio):
  - `twilio_sid` (string): Your Twilio Account SID, available from the Twilio Console. Alternatively, set via the `TWILIO_SID` environment variable.
  - `twilio_token` (string): Your Twilio Auth Token, also from the Twilio Console. Alternatively, set via the `TWILIO_TOKEN` environment variable.
  - `twilio_from_number` (string): The phone number provided by Twilio for sending SMS (e.g., `+1234567890`).
  - `twilio_to_number` (string): The recipient's phone number (e.g., `+0987654321`).
  - Example: `"twilio_sid=ACxxx,twilio_token=xxx,twilio_from_number=+1234567890,twilio_to_number=+0987654321"`.

- **WhatsApp** (via Twilio):
  - `twilio_sid` (string): Your Twilio Account SID, available from the Twilio Console. Alternatively, set via the `TWILIO_SID` environment variable.
  - `twilio_token` (string): Your Twilio Auth Token, also from the Twilio Console. Alternatively, set via the `TWILIO_TOKEN` environment variable.
  - `twilio_from_number` (string): The WhatsApp-enabled sender number provided by Twilio (e.g., `+1234567890`).
  - `twilio_to_number` (string): The recipient's WhatsApp number (e.g., `+0987654321`).
  - Example: `"twilio_sid=ACxxx,twilio_token=xxx,twilio_from_number=+1234567890,twilio_to_number=+0987654321"`.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename threshold_deadman_checks_plugin.py \
  --trigger-spec "every:10m" \
  --trigger-arguments measurement=cpu,senders=slack,field_aggregation_values="temp:avg@>=30",interval=5min,window=10m,trigger_count=3,deadman_check=true,slack_webhook_url="https://hooks.slack.com/services/..." \
  scheduler_trigger
```

### Data Write Plugin
The Data Write Plugin triggers on data writes to the database and checks for threshold conditions on specified fields.

#### Arguments (Data Write Mode)
The following arguments are extracted from the `args` dictionary for the Data Write Plugin:

| Argument                | Description                                                                                                     | Required | Example                                                                                              |
|-------------------------|-----------------------------------------------------------------------------------------------------------------|----------|------------------------------------------------------------------------------------------------------|
| `measurement`           | The InfluxDB table (measurement) to monitor.                                                                    | Yes      | `"cpu"`                                                                                              |
| `field_conditions`      | Conditions for triggering alerts (e.g., `temp>'30.0'-WARN:status=='ok'-INFO`).                                  | Yes      | `temp>'30.0'-WARN:status=='ok'-INFO`                                                                 |
| `senders`               | Dot-separated list of notification channels.                                                                    | Yes      | `"slack.discord"`                                                                                    |
| `influxdb3_auth_token`  | API token for your InfluxDB 3 instance. Can be set via environment variable `INFLUXDB3_AUTH_TOKEN`.             | No       | `"YOUR_API_TOKEN"`                                                                                   |
| `trigger_count`         | Number of times the condition must be met before sending an alert.                                              | No       | `2` (default: 1)                                                                                     |
| `notification_text`     | Template for the notification message with variables `$level`, `$field`, `$op_sym`, `$compare_val`, `$actual`.  | No       | `"[$level] InfluxDB 3 alert triggered. Condition \$field \$op_sym \$compare_val matched (\$actual)"` |
| `notification_path`     | URL path for the notification sending plugin.                                                                   | No       | `some/path` (default: `notify`)                                                                      |
| `port_override`         | The port number where InfluxDB accepts requests.                                                                | No       | `8182` (default: `8181`)                                                                             |
| `config_file_path`      | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                             | No       | `'example.toml'`                                                                                     |

#### Sender-Specific Configurations in `senders_config`
The same sender-specific arguments as described in the Scheduler Plugin section apply here.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename threshold_deadman_checks_plugin.py \
  --trigger-spec "all_tables" \
  --trigger-arguments measurement=cpu,field_conditions="temp>30-INFO:status==ok-ERROR",senders=slack,trigger_count=3,slack_webhook_url="https://hooks.slack.com/services/..." \
  data_write_trigger
```

## Important Notes
- **Environment Variables**: Sensitive data like API tokens can be set via environment variables (e.g., `INFLUXDB3_AUTH_TOKEN`).
- **Retries**: The plugin retries failed notifications with exponential backoff.
- **Row in Notifications**: The `row` variable in threshold notifications uniquely identifies the combination of message level, table and tags, ensuring alerts are specific to each tag set.
- **Measurements/Tag Name Caching**: The plugin caches the list of measurements in database and tag names for each measurement for one hour to avoid unnecessary repeated queries and improve performance.


## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).