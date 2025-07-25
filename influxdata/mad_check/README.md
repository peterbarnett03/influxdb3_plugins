# MAD-Based Anomaly Detection Plugin for InfluxDB 3

This plugin provides Median Absolute Deviation (MAD)-based anomaly detection for InfluxDB 3 using the `data writes` trigger. It detects anomalies in field values by maintaining in-memory deques of recent data points and computing MAD. The plugin supports both count-based and duration-based thresholds for triggering alerts and integrates with the **Notification Sender Plugin for InfluxDB 3** to send notifications via various channels.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: with the Processing Engine enabled.
- **Notification Sender Plugin for InfluxDB 3**: Required for sending notifications. [Link to Notification Sender Plugin](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/notifier).
- **Table schema**: The plugin assumes that the table schema is already defined in the database, as it relies on this schema to retrieve field and tag names required for processing.

## Files
- `mad_check_plugin.py`: The main plugin code containing the handler for the `data writes` trigger.

## Features
- **MAD-Based Anomaly Detection**: Detects anomalies in field values using Median Absolute Deviation without repeated database queries.
- **In-Memory Deques**: Maintains recent values in memory for efficient MAD computation.
- **Count and Duration-Based Triggers**: Supports triggering alerts based on the number of consecutive outliers or the duration of outlier conditions.
- **Args Overriding**: Allows overriding arguments for  data write type via TOML file (env var `PLUGIN_DIR` and `config_file_path` parameter should be set, see toml files example on [Git](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/mad_check). Override args parameter in handler function). The `config_file_path` must be specified as a path relative to the directory defined by PLUGIN_DIR.
- **Flip Detection**: Suppresses notifications if field values change too frequently within a specified window.
- **Multi-Channel Notifications**: Supports Slack, Discord, HTTP, SMS, and WhatsApp via the Notification Sender Plugin.
- **Customizable Messages**: Notification templates support dynamic variables (e.g., `$table`, `$field`, `$threshold_count`, `$tags`).
- **Retry Logic**: Retries failed notifications with randomized backoff.
- **Environment Variable Support**: Configurable via environment variables (e.g., `INFLUXDB3_AUTH_TOKEN`).

## Logging
Logs are stored in the `_internal` database (or the database where the trigger is created) in the `system.processing_engine_logs` table. To view logs, use the following query:

```bash
influxdb3 query --database _internal "SELECT * FROM system.processing_engine_logs"
```

### Log Columns Description
- **event_time**: Timestamp of the log event.
- **trigger_name**: Name of the trigger that generated the log.
- **log_level**: Severity level (`INFO`, `WARN`, `ERROR`).
- **log_text**: Message describing the action or error.

## Setup & Run

### 1. Install & Run InfluxDB v3 Core/Enterprise
- Download and install InfluxDB v3 Core/Enterprise.
- Ensure the `plugins` directory exists; if not, create it:
  ```bash
  mkdir ~/.plugins
  ```
- Place `mad_check_plugin.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package requests
```

### 3. Install and Configure the Notification Sender Plugin
- Ensure the [Notification Sender Plugin for InfluxDB 3](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/notifier) is installed and configured. This plugin is **required** for sending notifications via Slack, Discord, HTTP, SMS, or WhatsApp.

## Configure & Create Triggers

### Data Write Plugin
The Data Write Plugin triggers on data writes to the database, performs MAD-based anomaly detection on specified fields, and sends notifications when anomaly thresholds are met. It also suppresses notifications if field values change too frequently.

#### Arguments (Data Write Mode)
The following arguments are extracted from the `args` dictionary for the Data Write Plugin:

| Argument                  | Description                                                                                                                               | Required | Example                                                                                                  |
|---------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|----------|----------------------------------------------------------------------------------------------------------|
| `measurement`             | The InfluxDB table (measurement) to monitor.                                                                                              | Yes      | `"cpu"`                                                                                                  |
| `mad_thresholds`          | Threshold conditions for MAD-based anomaly detection (e.g., `field:k:window_count:threshold`). Example: `temp:"2.5":20:5@load:3.0:10:2m`. | Yes      | `"temp:"2.5":20:5@load:"3.0":10:2m"`                                                                     |
| `senders`                 | Dot-separated list of notification channels.                                                                                              | Yes      | `"slack.discord"`                                                                                        |
| `influxdb3_auth_token`    | API token for InfluxDB 3. Can be set via `INFLUXDB3_AUTH_TOKEN` environment variable.                                                     | No       | `"YOUR_API_TOKEN"`                                                                                       |
| `state_change_count`      | Maximum allowed flips (changes) in recent values before suppressing notifications. If `0` suppression is disabled.                        | No       | `2` (default: `0`)                                                                                       |
| `notification_count_text` | Template for count-based notification messages with variables `$table`, `$field`, `$threshold_count`, `$tags`.                            | No       | `"MAD count alert: Field $field in $table outlier for $threshold_count consecutive points. Tags: $tags"` |
| `notification_time_text`  | Template for duration-based notification messages with variables `$table`, `$field`, `$threshold_time`, `$tags`.                          | No       | `"MAD duration alert: Field $field in $table outlier for $threshold_time. Tags: $tags"`                  |
| `notification_path`       | URL path for the notification sending plugin.                                                                                             | No       | `"some/path"` (default: `notify`)                                                                        |
| `port_override`           | Port number where InfluxDB accepts requests.                                                                                              | No       | `8182` (default: `8181`)                                                                                 |
| `config_file_path`        | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                                                       | No       | `'example.toml'`                                                                                         |

#### MAD Thresholds Format
- Format: `field_name:k:window_count:threshold` (e.g., `temp:"2.5":20:5` for 5 consecutive outliers, or `load:"3.0":10:2m` for 2 minutes of outlier conditions).
- Multiple conditions are separated by `@` (e.g., `temp:"2":20:5@load:"3.0":10:2m`).
- `field_name`: The numeric field to monitor.
- `k`: The multiplier for MAD to define the anomaly threshold.
- `window_count`: The number of recent points to use for computing the median and MAD, also used for flip detection.
- `threshold`: Either an integer (for count-based triggering) or a duration string (e.g., `2m`, `30s`, `1h`, `1d`, `1w`) for duration-based triggering.

#### Sender-Specific Configurations
Depending on the channels specified in `senders`, additional arguments are required:

- **Slack**:
  - `slack_webhook_url` (string): Webhook URL from Slack (required).
  - `slack_headers` (string, optional): Base64-encoded HTTP headers (optional).
  - Example: `"slack_webhook_url=https://hooks.slack.com/services/..."`.

- **Discord**:
  - `discord_webhook_url` (string): Webhook URL from Discord (required).
  - `discord_headers` (string, optional): Base64-encoded HTTP headers (optional).
  - Example: `"discord_webhook_url=https://discord.com/api/webhooks/..."`.

- **HTTP**:
  - `http_webhook_url` (string): Custom webhook URL for POST requests (required).
  - `http_headers` (string, optional): Base64-encoded HTTP headers (optional).
  - Example: `"http_webhook_url=https://example.com/webhook"`.

- **SMS** (via Twilio):
  - `twilio_sid` (string): Twilio Account SID, or via `TWILIO_SID` env var (required).
  - `twilio_token` (string): Twilio Auth Token, or via `TWILIO_TOKEN` env var (required).
  - `twilio_from_number` (string): Twilio sender number (e.g., `+1234567890`) (required).
  - `twilio_to_number` (string): Recipient number (e.g., `+0987654321`) (required).
  - Example: `"twilio_sid=ACxxx,twilio_token=xxx,twilio_from_number=+1234567890,twilio_to_number=+0987654321"` (required).

- **WhatsApp** (via Twilio):
  - Same as SMS arguments, with WhatsApp-enabled numbers.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename mad_check_plugin.py \
  --trigger-spec "all_tables" \
  --trigger-arguments measurement=cpu,mad_thresholds="temp:"2.5":20:5@load:3:10:2m",senders=slack,slack_webhook_url="https://hooks.slack.com/services/...",influxdb3_auth_token="YOUR_API_TOKEN" \
  data_write_trigger
```

## Important Notes
- **Environment Variables**: Use environment variables for sensitive data (e.g., `INFLUXDB3_AUTH_TOKEN`, `TWILIO_SID`, `TWILIO_TOKEN`).
- **Retries**: Notifications are retried up to three times with randomized backoff delays.
- **Tags in Notifications**: The `tags` variable in notification messages includes all tag names and values for the triggering condition (e.g., `host=server1,region=eu`).
- **In-Memory Processing**: The plugin uses cached deques to maintain recent values and compute MAD efficiently without database queries.
- **Measurements/Tag Name Caching**: The plugin caches the list of measurements in database and tag names for each measurement for one hour to avoid unnecessary repeated queries and improve performance.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).