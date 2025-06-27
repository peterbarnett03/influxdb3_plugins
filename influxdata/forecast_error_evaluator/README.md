# Forecast Error Evaluator Plugin for InfluxDB 3

This plugin evaluates the accuracy of forecast models in InfluxDB 3 by comparing predicted values with actual observations. It operates as a scheduler plugin, periodically querying specified measurements for forecast and actual data, computing error metrics (MSE, MAE, or RMSE), and detecting anomalies based on elevated errors. When anomalies are detected, it sends notifications via various channels using the **Notification Sender Plugin for InfluxDB 3**.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: Latest version.
- **Python**: Version 3.10 or higher.
- **Notification Sender Plugin for InfluxDB 3**: Required for sending notifications. [Link to Notification Sender Plugin](#) (to be added).

## Files
- `forecast_error_evaluator.py`: The main plugin code containing the handler for the `scheduler` trigger.

## Features
- **Scheduler Plugin**: Periodically queries forecast and actual measurements within a time window, computes error metrics, and detects anomalies based on error thresholds.
- **Args Overriding**: Allows overriding arguments for scheduler type via TOML file (env var `PLUGIN_DIR` and `config_file_path` parameter should be set, all parameters and their values should be the same as in `--trigger-arguments`, override args parameter in handler function).
- **Error Metrics**: Supports MSE, MAE, and RMSE for evaluating forecast accuracy.
- **Threshold-based Detection**: Flags anomalies when the computed error exceeds a specified threshold.
- **Debounce Logic**: Optional minimum condition duration to suppress transient anomalies.
- **Multi-Channel Notifications**: Supports Slack, Discord, HTTP, SMS, and WhatsApp via the Notification Sender Plugin.
- **Customizable Messages**: Notification templates support dynamic variables (e.g., `$measurement`, `$field`, `$error`, `$metric`, `$tags`).
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
- Place `forecast_error_evaluator.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package pandas
influxdb3 install package requests
```

### 3. Install and Configure the Notification Sender Plugin
- Ensure the [Notification Sender Plugin for InfluxDB 3](#) (link to be added) is installed and configured. This plugin is **required** for sending notifications via Slack, Discord, HTTP, SMS, or WhatsApp.

## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin periodically queries the specified forecast and actual measurements within a time window, computes the error metric for each timestamp, and sends notifications when the error exceeds the threshold. Optional debounce logic suppresses transient anomalies.

#### Arguments
The following arguments are extracted from the `args` dictionary:

| Argument                 | Description                                                                                                                                                                     | Required | Example                                                                               |
|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|---------------------------------------------------------------------------------------|
| `forecast_measurement`   | The InfluxDB measurement containing forecasted values.                                                                                                                          | Yes      | `"forecast_data"`                                                                     |
| `actual_measurement`     | The InfluxDB measurement containing actual (ground truth) values.                                                                                                               | Yes      | `"actual_data"`                                                                       |
| `forecast_field`         | The field name in `forecast_measurement` for forecasted values.                                                                                                                 | Yes      | `"predicted_temp"`                                                                    |
| `actual_field`           | The field name in `actual_measurement` for actual values.                                                                                                                       | Yes      | `"temp"`                                                                              |
| `error_metric`           | The error metric to use (`mse`, `mae`, `rmse`).                                                                                                                                 | Yes      | `"rmse"`                                                                              |
| `error_thresholds`       | The threshold value for the error metric to trigger an anomaly with levels                                                                                                      | Yes      | `INFO-"0.5":WARN-"0.9":ERROR-"1.2":CRITICAL-"1.5"`                                    |
| `window`                 | Time window for data analysis (e.g., `1h` for 1 hour). Units: `s`, `min`, `h`, `d`, `w`.                                                                                        | Yes      | `"1h"`                                                                                |
| `senders`                | Dot-separated list of notification channels (e.g., `slack.discord`).                                                                                                            | Yes      | `"slack"`                                                                             |
| `influxdb3_auth_token`   | API token for InfluxDB 3. Can be set via `INFLUXDB3_AUTH_TOKEN` environment variable.                                                                                           | No       | `"YOUR_API_TOKEN"`                                                                    |
| `min_condition_duration` | Minimum duration for an anomaly condition to persist before triggering a notification (e.g., `5m`). Units: `s`, `min`, `h`, `d`, `w`.                                           | No       | `"5min"`                                                                              |
| `rounding_freq`          | Frequency to round timestamps for alignment (e.g., `1s`). See all supported units here: [pandas doc](https://pandas.pydata.org/docs/reference/api/pandas.Series.dt.round.html). | No       | `"1s"`                                                                                |
| `notification_text`      | Template for notification message with variables `$measurement`, `$level`, `$field`, `$error`, `$metric`, `$tags`.                                                              | No       | `"[$level] Forecast error alert in $measurement.$field: $metric=$error. Tags: $tags"` |
| `notification_path`      | URL path for the notification sending plugin.                                                                                                                                   | No       | `"some/path"` (default: `notify`)                                                     |
| `port_override`          | Port number where InfluxDB accepts requests.                                                                                                                                    | No       | `8182` (default: `8181`)                                                              |
| `config_file_path`       | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                                                                                             | No       | `'example.toml'`                                                                      |


#### Sender-Specific Configurations
Depending on the channels specified in `senders`, additional arguments are required:

- **Slack**:
  - `slack_webhook_url` (string): Webhook URL from Slack (required).
  - `slack_headers` (string, optional): Base64-encoded HTTP headers.
  - Example: `"slack_webhook_url=https://hooks.slack.com/services/..."`.

- **Discord**:
  - `discord_webhook_url` (string): Webhook URL from Discord (required).
  - `discord_headers` (string, optional): Base64-encoded HTTP headers.
  - Example: `"discord_webhook_url=https://discord.com/api/webhooks/..."`.

- **HTTP**:
  - `http_webhook_url` (string): Custom webhook URL for POST requests (required). 
  - `http_headers` (string, optional): Base64-encoded HTTP headers.
  - Example: `"http_webhook_url=https://example.com/webhook"`.

- **SMS** (via Twilio):
  - `twilio_sid` (string): Twilio Account SID, or via `TWILIO_SID` env var (required).
  - `twilio_token` (string): Twilio Auth Token, or via `TWILIO_TOKEN` env var (required).
  - `twilio_from_number` (string): Twilio sender number (e.g., `+1234567890`) (required).
  - `twilio_to_number` (string): Recipient number (e.g., `+0987654321`) (required).
  - Example: `"twilio_sid=ACxxx,twilio_token=xxx,twilio_from_number=+1234567890,twilio_to_number=+0987654321"`.

- **WhatsApp** (via Twilio):
  - Same as SMS arguments, with WhatsApp-enabled numbers.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename forecast_error_evaluator.py \
  --trigger-spec "every:10m" \
  --trigger-arguments forecast_measurement=forecast_data,actual_measurement=actual_data,forecast_field=predicted_temp,actual_field=temp,error_metric=rmse,error_threshold=INFO-"0.5",window=10m,senders=slack,slack_webhook_url="https://hooks.slack.com/services/...",influxdb3_auth_token="YOUR_API_TOKEN",min_condition_duration="5m" \
  forecast_error_trigger
```

## Important Notes
- **Environment Variables**: Use environment variables for sensitive data (e.g., `INFLUXDB3_AUTH_TOKEN`, `TWILIO_SID`, `TWILIO_TOKEN`).
- **Retries**: Notifications are retried up to three times with randomized backoff delays.
- **Data Requirements**: Ensure that the forecast and actual measurements have overlapping timestamps within the specified window.
- **Timestamp Alignment**: Use `rounding_freq` to align timestamps if there are small differences.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).