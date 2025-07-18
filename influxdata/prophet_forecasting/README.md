# Prophet Forecasting Plugin for InfluxDB 3

This plugin enables forecasting of time series data stored in InfluxDB 3 using the Prophet library. It supports two trigger types:
- **Scheduler Plugin**: Periodically performs forecasting on specified measurements and writes the results to a target measurement.
- **HTTP Plugin**: Allows on-demand forecasting via HTTP POST requests, providing flexible control over the forecasting process.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: with the Processing Engine enabled.

## Files
- `prophet_forecasting.py`: The main plugin code containing handlers for both `scheduler` and `http` triggers.

## Features
- **Scheduler Plugin**: Periodically performs forecasting on specified InfluxDB measurements.
- **HTTP Plugin**: Allows on-demand forecasting via HTTP POST requests.
- **Args Overriding**: Allows overriding arguments for scheduled tasks via TOML file (env var `PLUGIN_DIR` and `config_file_path` parameter should be set, all parameters and their values should be the same as in `--trigger-arguments`, override args parameter in handler function). The `config_file_path` must be specified as a path relative to the directory defined by PLUGIN_DIR.
- **Model Training and Prediction**: Supports both training new models and using existing ones for prediction.
- **Forecast Validation**: Optionally validates forecasts against recent actual values using Mean Squared Relative Error (MSRE).
- **Data Writing**: Writes forecast results to a specified InfluxDB measurement.
- **Notifications**: Optionally sends alerts via configured channels if forecast validation fails.
- **Time Interval Parsing**: Supports a wide range of time units for intervals, including seconds (`s`), minutes (`min`), hours (`h`), days (`d`), weeks (`w`), months (`m`), quarters (`q`), and years (`y`).

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
- Place `prophet_forecasting.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package pandas
influxdb3 install package numpy
influxdb3 install package requests
influxdb3 install package prophet
```

## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin periodically performs forecasting on the specified InfluxDB measurement, using the provided configuration to train or predict with a Prophet model, and writes the forecast results to a target measurement.

#### Arguments
The following arguments are extracted from the `args` dictionary:

| Argument                   | Description                                                                                                                                               | Required    | Example                                                                                                                                                                          |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `measurement`              | The InfluxDB measurement to query for historical data.                                                                                                    | Yes         | `"temperature"`                                                                                                                                                                  |
| `field`                    | The field name within the measurement to forecast.                                                                                                        | Yes         | `"value"`                                                                                                                                                                        |
| `window`                   | Historical window duration for training data (e.g., `30d`). Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`, `m`, `q`, `y`.              | Yes         | `"30d"`                                                                                                                                                                          |
| `forecast_horizont`        | Future duration to forecast (e.g., `2d`). Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`, `m`, `q`, `y`.                                | Yes         | `"2d"`                                                                                                                                                                           |
| `tag_values`               | Dot-separated tag filter string for querying specific tag values (e.g., `key1:value1.key2:value2`).                                                       | Yes         | `"region:us-west.device:sensor1"`                                                                                                                                                |
| `target_measurement`       | Destination measurement for storing forecast results.                                                                                                     | Yes         | `"temperature_forecast"`                                                                                                                                                         |
| `model_mode`               | Mode of operation: `"train"` to train a new model, `"predict"` to use an existing one or train if not found.                                              | Yes         | `"train"`                                                                                                                                                                        |
| `unique_suffix`            | Unique identifier for model versioning and storage.                                                                                                       | Yes         | `"20250619_v1"`                                                                                                                                                                  |
| `seasonality_mode`         | Prophet seasonality mode (`"additive"` or `"multiplicative"`). Defaults to `"additive"`.                                                                  | No          | `"additive"`                                                                                                                                                                     |
| `changepoint_prior_scale`  | Flexibility of trend changepoints. Defaults to `0.05`.                                                                                                    | No          | `0.05`                                                                                                                                                                           |
| `changepoints`             | Space-separated list of changepoint dates (ISO format).                                                                                                   | No          | `"2025-01-01 2025-06-01"`                                                                                                                                                        |
| `holiday_date_list`        | Space-separated list of custom holiday dates (ISO format).                                                                                                | No          | `"2025-01-01 2025-12-25"`                                                                                                                                                        |
| `holiday_names`            | Dot-separated list of names corresponding to the holiday dates.                                                                                           | No          | `"New Year.Christmas"`                                                                                                                                                           |
| `holiday_country_names`    | Dot-separated list of country codes for built-in holidays (e.g., `"US.UK"`).                                                                              | No          | `"US.UK"`                                                                                                                                                                        |
| `inferred_freq`            | Manually specified frequency (e.g., `"1D"`, `"1H"`). If not provided, frequency is inferred from data.                                                    | No          | `"1D"`                                                                                                                                                                           |
| `validation_window`        | Duration for validation window (e.g., `"3d"`). Defaults to `"0s"` (no validation). Format: `<number><unit>`.                                              | No          | `"3d"`                                                                                                                                                                           |
| `msre_threshold`           | Maximum acceptable Mean Squared Relative Error (MSRE) for validation. Defaults to infinity (no threshold).                                                | No          | `0.05`                                                                                                                                                                           |
| `target_database`          | Optional InfluxDB database name for writing forecast results.                                                                                             | No          | `"forecast_db"`                                                                                                                                                                  |
| `is_sending_alert`         | Whether to send alerts on validation failure (`"true"` or `"false"`). Defaults to `"false"`.                                                              | No          | `"true"`                                                                                                                                                                         |
| `notification_text`        | Templated text for alert message. Variables like `$version`, `$measurement`, `$field`, `$start_time`, `$end_time`, and `$output_measurement` can be used. | No          | `"Validation failed for prophet model:$version on table:$measurement, field:$field for period from $start_time to $end_time, forecast not written to table:$output_measurement"` |
| `senders`                  | Dot-separated list of sender types (e.g., `"slack.sms"`).                                                                                                 | No          | `"slack"`                                                                                                                                                                        |
| `notification_path`        | URL path for posting the alert (e.g., `"notify"`). Defaults to `"notify"`.                                                                                | No          | `"notify"`                                                                                                                                                                       |
| `influxdb3_auth_token`     | Authentication token for sending notifications. If not provided, uses `INFLUXDB3_AUTH_TOKEN` environment variable.                                        | No          | `"your_token"`                                                                                                                                                                   |
| `port_override`            | Optional custom port for notification dispatch (1–65535). Defaults to `8181`.                                                                             | No          | `8182`                                                                                                                                                                           |
| `config_file_path`         | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                                                                       | No          | `'example.toml'`                                                                                                                                                                 |

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename prophet_forecasting.py \
  --trigger-spec "every:1d" \
  --trigger-arguments measurement=temperature,field=value,window=30d,forecast_horizont=2d,tag_values="region:us-west.device:sensor1",target_measurement=temperature_forecast,model_mode=train,unique_suffix=20250619_v1 \
  prophet_forecast_trigger
```

#### Sending Alert Configurations
If you set `is_sending_alert` to `"true"`, the plugin will send alerts on validation failure. For this to work, the plugin requires the following additional arguments to be provided:

- `notification_text` (string): Templated text for alert message. Variables like `$version`, `$measurement` can be used.
- `senders` (string): Dot-separated list of sender types (e.g., `"slack.sms"`).
- `notification_path` (string): URL path for posting the alert (e.g., `"notify"`).
- `influxdb3_auth_token` (string): Authentication token for sending notifications.
- `port_override` (integer): Optional custom port for notification dispatch (1–65535).

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



### HTTP Plugin
The HTTP Plugin allows on-demand forecasting via HTTP POST requests. It processes the request body to configure the forecasting parameters, including optional validation and notifications.

#### Trigger Creation
Create an HTTP trigger using the `influxdb3 create trigger` command:
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename prophet_forecasting.py \
  --trigger-spec "request:forecast" \
  prophet_forecast_http_trigger
```
This registers an HTTP endpoint at `/api/v3/engine/forecast`.

#### Enable Trigger
Enable the trigger to start processing requests:
```bash
influxdb3 enable trigger --database mydb prophet_forecast_http_trigger
```

#### Request Body Arguments
The plugin expects a JSON body with the following structure:

| Argument                  | Description                                                                                                                      | Required  | Example                                      |
|---------------------------|----------------------------------------------------------------------------------------------------------------------------------|-----------|----------------------------------------------|
| `measurement`             | The InfluxDB measurement to query for historical data.                                                                           | Yes       | `"temperature"`                              |
| `field`                   | The field name within the measurement to forecast.                                                                               | Yes       | `"value"`                                    |
| `forecast_horizont`       | Future duration to forecast (e.g., `"7d"`). Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`, `m`, `q`, `y`.     | Yes       | `"7d"`                                       |
| `tag_values`              | Dictionary of tag filters for the InfluxDB query (e.g., `{"region":"us-west"}`).                                                 | Yes       | `{"region":"us-west","device":"sensor1"}`    |
| `target_measurement`      | Destination measurement for storing forecast results.                                                                            | Yes       | `"temperature_forecast"`                     |
| `unique_suffix`           | Unique identifier for model versioning and storage.                                                                              | Yes       | `"20250619_v1"`                              |
| `start_time`              | Start of historical window (ISO 8601 format with timezone, e.g., `"2025-05-20T00:00:00Z"`).                                      | Yes       | `"2025-05-20T00:00:00Z"`                     |
| `end_time`                | End of historical window (ISO 8601 format with timezone, e.g., `"2025-06-19T00:00:00Z"`).                                        | Yes       | `"2025-06-19T00:00:00Z"`                     |
| `seasonality_mode`        | Prophet seasonality mode (`"additive"` or `"multiplicative"`). Defaults to `"additive"`.                                         | No        | `"additive"`                                 |
| `changepoint_prior_scale` | Flexibility of trend changepoints. Defaults to `0.05`.                                                                           | No        | `0.05`                                       |
| `changepoints`            | List of changepoint dates (ISO format).                                                                                          | No        | `["2025-01-01", "2025-06-01"]`               |
| `save_mode`               | Whether to load/save the model (`"true"` or `"false"`). Defaults to `"false"`.                                                   | No        | `"true"`                                     |
| `validation_window`       | Duration for validation window (e.g., `"3d"`). Defaults to `"0s"` (no validation). Format: the same as `forecast_horizont`.      | No        | `"3d"`                                       |
| `msre_threshold`          | Maximum acceptable MSRE for validation. Defaults to infinity (no threshold).                                                     | No        | `0.05`                                       |
| `target_database`         | Optional InfluxDB database name for writing forecast results.                                                                    | No        | `"forecast_db"`                              |
| `holiday_date_list`       | List of custom holiday dates (ISO format).                                                                                       | No        | `["2025-01-01", "2025-12-25"]`               |
| `holiday_names`           | List of names corresponding to the holiday dates.                                                                                | No        | `["New Year", "Christmas"]`                  |
| `holiday_country_names`   | List of country codes for built-in holidays (e.g., `["US", "UK"]`).                                                              | No        | `["US", "UK"]`                               |
| `inferred_freq`           | Manually specified frequency (e.g., `"1D"`). If not provided, frequency is inferred from data.                                   | No        | `"1D"`                                       |

#### Example HTTP Request
```bash
curl -X POST http://localhost:8181/api/v3/engine/forecast \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "measurement": "temperature",
    "field": "value",
    "forecast_horizont": "7d",
    "tag_values": {"region":"us-west","device":"sensor1"},
    "target_measurement": "temperature_forecast",
    "unique_suffix": "20250619_v1",
    "start_time": "2025-05-20T00:00:00Z",
    "end_time": "2025-06-19T00:00:00Z",
    "seasonality_mode": "additive",
    "changepoint_prior_scale": 0.05,
    "validation_window": "3d",
    "msre_threshold": 0.05
  }'
```

## Important Notes

### Model Storage and Unique Suffix
- **Model Storage Path**: Models are stored in the `prophet_models` directory within the plugin’s directory (e.g., alongside `prophet_forecasting.py`) or in `~/.plugins/prophet_models` if the plugin is run in an environment where `__file__` is not available (e.g., frozen executables).
- **File Naming**: Each model is saved as `prophet_model_{unique_suffix}.json`, where `unique_suffix` is a required parameter provided in the configuration (e.g., `"20250619_v1"`).
- **Purpose of Unique Suffix**: The `unique_suffix` ensures that each model is uniquely identifiable and prevents conflicts when multiple models are used or stored. It allows versioning and independent management of models, avoiding overwrites when different configurations or datasets are processed.

### Validation Process
The plugin includes an optional validation process to assess forecast accuracy against recent actual data. This process is enabled when the `validation_window` parameter is set.

- **Data Retrieval**:
  - **Training Data**: The forecasting model is trained on data queried from the InfluxDB measurement for the period from `call_time/start_time - window` to `call_time/start_time - validation_window`.
  - **Validation Data**: The actual values used for validation are queried from the InfluxDB measurement for the period from `call_time/start_time - validation_window` to `call_time/start_time`.
  - The model, trained on the training data, generates predicted values (`yhat`) for the validation period.

- **Sorting**: Both the validation data (actual values) and the predicted values (`yhat`) are sorted by time to ensure chronological alignment.

- **Trimming**: The datasets are trimmed to the same length, taking the minimum number of records available in either set to ensure a fair comparison.

- **Comparison**: The actual values (`y`) and predicted values (`yhat`) are compared after filtering out zero values in `y` to avoid division-by-zero errors. The Mean Squared Relative Error (MSRE) is calculated as:
  ```
  MSRE = mean((y - yhat)² / y²)
  ```
- **Threshold Check**: If the computed MSRE exceeds the specified `msre_threshold`, validation fails, the forecast is not written to the target measurement, and an alert is sent if configured (just for scheduler type via `is_sending_alert`).


### Mode-Specific Behavior
The plugin’s behavior depends on the mode specified, affecting how models are created, saved, or loaded:

- **Scheduler Plugin - Train Mode (`model_mode = "train"`)**:
  - Always trains a new Prophet model using the historical data retrieved from the specified `window`.
  - Uses the newly trained model to generate forecasts.
  - Does not save the model to disk.

- **Scheduler Plugin - Predict Mode (`model_mode = "predict"`)**:
  - Attempts to load an existing model from `prophet_model_{unique_suffix}.json`.
  - If the model file does not exist, it trains a new model using the historical data, saves it to the specified path, and then uses it for forecasting.
  - If the model file exists, it loads and uses it directly for prediction without retraining.

- **HTTP Plugin (`save_mode`)**:
  - **`"true"`**: Attempts to load an existing model from `prophet_model_{unique_suffix}.json`. If the file doesn’t exist, it trains a new model, saves it to that path, and uses it for forecasting.
  - **`"false"` or not provided**: Trains a new model in memory using the historical data from `start_time` to `end_time`, uses it for forecasting, and does not save it to disk.

### Structure of the Data Saved in InfluxDB

The Prophet plugin saves the forecast results in InfluxDB using the following data structure. The data includes tags, fields, and timestamps, which are described below.

#### Tags
Tags are used for identification and categorization of the data:
- **`model_version`**: Unique identifier for the model version (e.g., `"20250619_v1"`), set via the `unique_suffix` parameter.
- **Additional tags**: Defined in the configuration through the `tag_values` dictionary. Examples:
  - `region="us-west"`
  - `device="sensor1"`

#### Fields
Fields contain the main values related to the forecast:
- **`forecast`**: The predicted value (corresponds to `yhat` from the Prophet model).
- **`yhat_lower`**: The lower bound of the forecast's confidence interval.
- **`yhat_upper`**: The upper bound of the forecast's confidence interval.
- **`run_time`**: The time when the forecast was run, recorded in ISO 8601 format (e.g., `"2025-06-20T14:22:00Z"`).

#### Timestamp
- **`time`**: The timestamp of the forecast, representing the point in time for which the forecast is made. Recorded in nanoseconds (e.g., `1684569600000000000`).


### Additional Notes
- **Data Requirements**: The queried measurement must contain a `time` column and the specified `field` for forecasting.
- **Frequency Inference**: If `inferred_freq` is not provided, the plugin attempts to infer the frequency using `pd.infer_freq` from the historical data. If inference fails, an error is logged, and the process halts unless `inferred_freq` is manually specified.
- **Time Units**: Parameters like `window`, `forecast_horizont`, and `validation_window` support units: `s` (seconds), `min` (minutes), `h` (hours), `d` (days), `w` (weeks), `m` (months, ~30.42 days), `q` (quarters, ~91.25 days), `y` (years, 365 days).

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).