# State Change Monitoring Plugin for InfluxDB 3

This plugin system provides field change and threshold monitoring capabilities for InfluxDB 3 through two complementary plugins: `scheduler` and `data writes`. These plugins detect changes in field values or threshold conditions and use the **Notification Sender Plugin for InfluxDB 3** to dispatch notifications via various channels.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: Latest version.
- **Python**: Version 3.10 or higher.
- **Notification Sender Plugin for InfluxDB 3**: Required for sending notifications. [Link to Notification Sender Plugin](#) (to be added).

## Files
- `state_change_check_plugin.py`: The main plugin code containing handlers for `scheduler` and `data writes` triggers.

## Features
- **Scheduler Plugin**: Periodically queries a measurement within a time window, counts field value changes for unique tag combinations, and sends notifications if thresholds are exceeded.
- **Data Write Plugin**: Triggers on data writes, monitors field thresholds (count or duration-based), and suppresses notifications for unstable data states.
- **Multi-Channel Notifications**: Supports Slack, Discord, HTTP, SMS, and WhatsApp via the Notification Sender Plugin.
- **Customizable Messages**: Notification templates support dynamic variables (e.g., `$table`, `$field`, `$changes`, `$tags`).
- **Retry Logic**: Retries failed notifications with randomized backoff.
- **Environment Variable Support**: Configurable via environment variables (e.g., `INFLUXDB3_AUTH_TOKEN`).
- **State Stability Check**: Suppresses notifications if field values change too frequently (data writes type).

## Logging
Logs are stored in the `_internal` database in the `system.processing_engine_logs` table. To view logs, use the following query:

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
- Place `state_change_check_plugin.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package requests
```

### 3. Install and Configure the Notification Sender Plugin
- Ensure the [Notification Sender Plugin for InfluxDB 3](#) (link to be added) is installed and configured. This plugin is **required** for sending notifications via Slack, Discord, HTTP, SMS, or WhatsApp.

## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin periodically queries a measurement within a specified time window, counts changes in field values for each unique tag combination, and sends notifications if the number of changes exceeds the defined threshold.

#### Arguments (Scheduler Mode)
The following arguments are extracted from the `args` dictionary for the Scheduler Plugin:

| Argument                | Description                                                                                          | Required | Example                                                                                             |
|-------------------------|------------------------------------------------------------------------------------------------------|----------|-----------------------------------------------------------------------------------------------------|
| `measurement`           | The InfluxDB table (measurement) to monitor.                                                         | Yes      | `"cpu"`                                                                                             |
| `field_change_count`    | Dot-separated list of field thresholds (e.g., `field:count`). Example: `temp:3.load:2`.              | Yes      | `"temp:3.load:2"`                                                                                   |
| `senders`               | Dot-separated list of notification channels (e.g., `slack.discord`).                                 | Yes      | `"slack.discord"`                                                                                   |
| `window`                | Time window for data analysis (e.g., `1h` for 1 hour). Units: `s`, `min`, `h`, `d`, `w`.             | Yes      | `"1h"`                                                                                              |
| `influxdb3_auth_token`  | API token for InfluxDB 3. Can be set via `INFLUXDB3_AUTH_TOKEN` environment variable.                | Yes      | `"YOUR_API_TOKEN"`                                                                                  |
| `notification_text`     | Template for notification message with variables `$table`, `$field`, `$changes`, `$window`, `$tags`. | No       | `"Field $field in table $table changed $changes times in window $window for tags $tags"`            |
| `notification_path`     | URL path for the notification sending plugin.                                                        | No       | `"some/path"` (default: `notify`)                                                                   |
| `port_override`         | Port number where InfluxDB accepts requests.                                                         | No       | `8182` (default: `8181`)                                                                            |

#### Sender-Specific Configurations
Depending on the channels specified in `senders`, additional arguments are required:

- **Slack**:
  - `slack_webhook_url` (string): Webhook URL from Slack.
  - `slack_headers` (string, optional): Base64-encoded HTTP headers.
  - Example: `"slack_webhook_url=https://hooks.slack.com/services/..."`.

- **Discord**:
  - `discord_webhook_url` (string): Webhook URL from Discord.
  - `discord_headers` (string, optional): Base64-encoded HTTP headers.
  - Example: `"discord_webhook_url=https://discord.com/api/webhooks/..."`.

- **HTTP**:
  - `http_webhook_url` (string): Custom webhook URL for POST requests.
  - `http_headers` (string, optional): Base64-encoded HTTP headers.
  - Example: `"http_webhook_url=https://example.com/webhook"`.

- **SMS** (via Twilio`):
  - `twilio_service_id` (string): Twilio ID, or via `TWILIO_SID` env var.
  - `twilio_token` (string): Twilio Auth Token, or via `TWILIO_TOKEN` env var.
  - `twilio_from_number` (string): Twilio sender number (e.g., `+1234567890`).
  - `twilio_to_number` (string): Recipient number (e.g., `+0987654321`).
  - Example: `"twilio_service_id=ACxxx,twilio_token=xxx,twilio_from_number=+1234567890,twilio_to_number=+0987654321"`.

- **WhatsApp** (via Twilio):
  - Same as SMS arguments, with WhatsApp-enabled numbers.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename state_change_check_plugin.py \
  --trigger-spec "every:10m" \
  --trigger-arguments measurement=cpu,field_change_count="temp:3.load:2",window=10m,senders=slack,slack_webhook_url="https://hooks.slack.com/services/...",influxdb3_auth_token="YOUR_API_TOKEN" \
  scheduler_trigger
```

### Data Write Plugin
The Data Write Plugin triggers on data writes to the database, monitors field thresholds based on count or duration, and sends notifications when conditions are met. It also suppresses notifications if field values change too frequently.

#### Arguments (Data Write Mode)
The following arguments are extracted from the `args` dictionary for the Data Write Plugin:

| Argument                  | Description                                                                                                                     | Required   | Example                                                                                                          |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------|------------|------------------------------------------------------------------------------------------------------------------|
| `measurement`             | The InfluxDB table (measurement) to monitor.                                                                                    | Yes        | `"cpu"`                                                                                                          |
| `field_thresholds`        | Threshold conditions (e.g., `field:value:count` or `field:value:time`). Example: `temp:"30.5":10@humidity:"true":2h`.           | Yes        | `"temp:"30.1":10@humidity:"true":2h"`                                                                            |
| `senders`                 | Dot-separated list of notification channels.                                                                                    | Yes        | `"slack.discord"`                                                                                                |
| `influxdb3_auth_token`    | API token for InfluxDB 3. Can be set via `INFLUXDB3_AUTH_TOKEN` environment variable.                                           | Yes        | `"YOUR_API_TOKEN"`                                                                                               |
| `state_change_window`     | Number of recent values to check for stability.                                                                                 | No         | `5` (default: `1`)                                                                                               |
| `state_change_count`      | Maximum allowed changes within `state_change_window` to allow notifications.                                                    | No         | `2` (default: `1`)                                                                                               |
| `notification_count_text` | Template for notification message (when condition with count) with variables `$table`, `$field`, `$value`, `$duration`, `$row`. | No         | `"State change detected: Field $field in table $table changed to $value during last $duration times. Row: $row"` |
| `notification_time_text`  | Template for notification message (when condition with time) with variables `$table`, `$field`, `$value`, `$duration`, `$row`.  | No         | `"State change detected: Field $field in table $table changed to $value during $duration. Row: $row`             |
| `notification_path`       | URL path for the notification sending plugin.                                                                                   | No         | `"some/path"` (default: `notify`)                                                                                |
| `port_override`           | Port number where InfluxDB accepts requests.                                                                                    | No         | `8182` (default: `8181`)                                                                                         |

#### Field Thresholds Format
- Format: `field_name:"value":count_or_time` (e.g., `temp:"30":10` for 10 occurrences, or `humidity:"true":2h` for 2 hours).
- Multiple conditions are separated by `@` (e.g., `temp:"30":10@humidity:"true":2h`).
- `value` can be an integer, float, boolean, or string.
- `count_or_duration` is either an integer (count) or a duration (e.g., `2h`, `30s`, `2d`, `1w`, `2min`).

#### Sender-Specific Configurations
The same sender-specific arguments as described in the Scheduler Plugin section apply here.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename state_change_check_plugin.py \
  --trigger-spec "all_tables" \
  --trigger-arguments measurement=cpu,field_thresholds="temp:"30":10@status:"ok":1h",senders=slack,slack_webhook_url="https://hooks.slack.com/services/...",influxdb3_auth_token="YOUR_API_TOKEN" \
  data_write_trigger
```

## Important Notes
- **Environment Variables**: Use environment variables for sensitive data (e.g., `INFLUXDB3_AUTH_TOKEN`, `TWILIO_SID`, `TWILIO_TOKEN`).
- **Retries**: Notifications are retried up to three times with randomized backoff delays.
- **Row in Notifications (Data Write)**: The `row` variable represents a unique combination of measurement, field, value, and tags (e.g., `cpu:temp:30:host=server1`).
- **Tags in Notifications (Scheduler)**: The `tags` variable includes all tag names and values for the triggering condition (e.g., `host=server1,region=eu`).

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).