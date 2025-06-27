# ADTK Anomaly Detection Plugin for InfluxDB 3

This plugin provides anomaly detection capabilities for time series data in InfluxDB 3 using the ADTK library through a `scheduler` trigger. It leverages the **Notification Sender Plugin for InfluxDB 3** to send notifications via various channels when anomalies are detected.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: Latest version.
- **Python**: Version 3.10 or higher.
- **Notification Sender Plugin for InfluxDB 3**: Required for sending notifications. [Link to Notification Sender Plugin](#) (to be added).

## Files
- `adtk_anomaly_detection_plugin.py`: The main plugin code containing the handler for the `scheduler` trigger.

## Features
- **Scheduler Plugin**: Periodically queries a measurement within a time window, applies one or more ADTK detectors to a numeric field, and sends notifications when anomalies are detected.
- **Multi-Channel Notifications**: Supports Slack, Discord, HTTP, SMS, and WhatsApp via the Notification Sender Plugin.
- **Args Overriding**: Allows overriding arguments for scheduler type via TOML file (env var `PLUGIN_DIR` and `config_file_path` parameter should be set, all parameters and their values should be the same as in `--trigger-arguments`, override args parameter in handler function).
- **Customizable Messages**: Notification templates support dynamic variables (e.g., `$table`, `$field`, `$timestamp`, `$value`, `$detectors`, `$tags`).
- **ADTK Stateless Detectors**: Supports multiple detectors:
    - `InterQuartileRangeAD`
    - `ThresholdAD`
    - `QuantileAD`
    - `LevelShiftAD`
    - `VolatilityShiftAD`
    - `PersistAD`
    - `SeasonalAD`
- **Retry Logic**: Retries failed notifications with randomized backoff.
- **Environment Variable Support**: Configurable via environment variables (e.g., `INFLUXDB3_AUTH_TOKEN`).
- **Consensus Detection**: Uses a `min_consensus` parameter to require a minimum number of detectors to agree on an anomaly before flagging it (default: 1).

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
- Place `adtk_anomaly_detection_plugin.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package requests
influxdb3 install package adtk
influxdb3 install package pandas
```

### 3. Install and Configure the Notification Sender Plugin
- Ensure the [Notification Sender Plugin for InfluxDB 3](#) (link to be added) is installed and configured. This plugin is **required** for sending notifications via Slack, Discord, HTTP, SMS, or WhatsApp.

## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin periodically queries a specified measurement within a time window, applies one or more ADTK detectors to a numeric field, and sends notifications when anomalies are detected. The `min_consensus` parameter defines the minimum number of detectors that must agree on an anomaly for it to be flagged, ensuring more reliable detection by requiring consensus among multiple detection methods.

#### Arguments
The following arguments are extracted from the `args` dictionary:

| Argument                  | Description                                                                                                                           | Required | Example                                                                                                    |
|---------------------------|---------------------------------------------------------------------------------------------------------------------------------------|----------|------------------------------------------------------------------------------------------------------------|
| `measurement`             | The InfluxDB measurement (table) to query.                                                                                            | Yes      | `"cpu"`                                                                                                    |
| `field`                   | The numeric field to evaluate for anomalies.                                                                                          | Yes      | `"usage"`                                                                                                  |
| `detectors`               | Dot-separated list of ADTK detectors (e.g., `QuantileAD.LevelShiftAD`).                                                               | Yes      | `"QuantileAD.LevelShiftAD"`                                                                                |
| `detector_params`         | Base64-encoded JSON string specifying parameters for each detector (see Detector Parameters below).                                   | Yes      | `"eyJRdWFudGlsZUFKIjogeyJsb3dfcXVhbnRpbGUiOiA..."`, decodes to {"QuantileAD": {"low": 0.05, "high": 0.95}} |
| `min_consensus`           | Minimum number of detectors that must agree to flag a point as anomalous.                                                             | No       | `2` (default: `1`)                                                                                         |
| `window`                  | Time window for data analysis (e.g., `1h` for 1 hour). Units: `s`, `min`, `h`, `d`, `w`.                                              | Yes      | `"1h"`                                                                                                     |
| `senders`                 | Dot-separated list of notification channels (e.g., `slack.discord`).                                                                  | Yes      | `"slack.discord"`                                                                                          |
| `influxdb3_auth_token`    | API token for InfluxDB 3. Can be set via `INFLUXDB3_AUTH_TOKEN` environment variable.                                                 | No       | `"YOUR_API_TOKEN"`                                                                                         |
| `min_condition_duration`  | Minimum duration for an anomaly condition to persist before triggering a notification (e.g., `5m`). Units: `s`, `min`, `h`, `d`, `w`. | No       | `"5m"` (default: `0s`)                                                                                     |
| `notification_text`       | Template for notification message with variables `$table`, `$field`, `$value`, `$detectors`, `$tags`.                                 | No       | `"Anomaly detected in \$table.\$field with value \$value by \$detectors. Tags: \$tags"`                    |
| `notification_path`       | URL path for the notification sending plugin.                                                                                         | No       | `"some/path"` (default: `notify`)                                                                          |
| `port_override`           | Port number where InfluxDB accepts requests.                                                                                          | No       | `8182` (default: `8181`)                                                                                   |
| `config_file_path`        | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                                                   | No       | `'example.toml'`                                                                                           |

#### Detector Parameters
Supported ADTK detectors: `InterQuartileRangeAD`, `LevelShiftAD`, `PersistAD`, `QuantileAD`, `SeasonalAD`, `ThresholdAD`, `VolatilityShiftAD`.
Some detector in `detectors` requires specific parameters provided in the `detector_params` base64-encoded JSON string:

- **LevelShiftAD**:
  - `window` (int): Window size for shift detection (required).
  
- **VolatilityShiftAD**:
  - `window` (int): Window size for volatility detection. (required)

You can find the documentation for each detector with its additional parameters in the [ADTK documentation](https://adtk.readthedocs.io/en/stable/api/detectors.html).

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename adtk_anomaly_detection_plugin.py \
  --trigger-spec "every:10m" \
  --trigger-arguments measurement=cpu,field=usage,detectors="QuantileAD.LevelShiftAD",detector_params="eyJRdWFu...",window=10m,senders=slack,slack_webhook_url="https://hooks.slack.com/services/..." \
  anomaly_trigger
```

## Important Notes
- **Environment Variables**: Use environment variables for sensitive data (e.g., `INFLUXDB3_AUTH_TOKEN`).
- **Retries**: Notifications are retried up to three times with randomized backoff delays.
- **Detector Configuration**: Ensure `detector_params` is a valid base64-encoded JSON string matching the specified detectors.
- **Consensus Detection**: The `min_consensus` parameter helps reduce false positives by requiring multiple detectors to confirm an anomaly.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).