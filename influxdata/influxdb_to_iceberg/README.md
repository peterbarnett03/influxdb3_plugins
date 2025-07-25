# InfluxDB to Iceberg Data Transfer Plugin for InfluxDB 3

This plugin transfers data from InfluxDB 3 to Apache Iceberg tables. It supports two trigger types:
- **Scheduler Plugin**: Periodically queries specified measurement within a time window, transforms the data, and appends it to an Iceberg table.
- **HTTP Plugin**: Allows on-demand data replication via HTTP POST requests, enabling flexible control over the replication process.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: with the Processing Engine enabled.
- **Table schema**: The plugin assumes that the table schema is already defined in the database, as it relies on this schema to retrieve field and tag names required for processing.

## Files
- `influxdb_to_iceberg.py`: The main plugin code containing handlers for both `scheduler` and `http` triggers.

## Features
- **Scheduler Plugin**: Periodically queries InfluxDB measurements within a specified time window.
- **HTTP Plugin**: Allows on-demand replication via HTTP POST requests, supporting batch processing and backfill windows.
- **Args Overriding**: Allows overriding arguments for scheduler type via TOML file (env var `PLUGIN_DIR` and `config_file_path` parameter should be set, see toml files examples on [Git](https://github.com/influxdata/influxdb3_plugins/tree/main/influxdata/influxdb_to_iceberg). Override args parameter in handler function). The `config_file_path` must be specified as a path relative to the directory defined by PLUGIN_DIR.
- **Data Transformation**: Converts InfluxDB query results to a format suitable for Iceberg tables.
- **Schema Management**: Automatically creates the Iceberg table schema based on the queried data if the table does not exist.
- **Namespace and Table Naming**: Customizable Iceberg namespace and table names, defaulting to "default" namespace and the measurement name for the table.
- **Field Filtering**: Supports including or excluding specific fields from the query results.
- **Batch Processing**: For HTTP requests, data is processed in batches to optimize performance and resource usage.

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
- Place `influxdb_to_iceberg.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package pandas
influxdb3 install package pyarrow
influxdb3 install package "pyiceberg[s3fs,hive,sql-sqlite]"
```

> **Note:**
> - You should provide additional packages while installing `pyiceberg` as needed for your specific use case based on what type of Iceberg catalog you are using. See the [PyIceberg documentation](https://py.iceberg.apache.org/#installation) for more details.

## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin periodically queries the specified InfluxDB measurement within a time window, transforms the data, and appends it to an Iceberg table. It handles schema creation and ensures the table exists before appending data.

#### Arguments
The following arguments are extracted from the `args` dictionary:

| Argument            | Description                                                                                                                                                   | Required  | Example                                      |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|----------------------------------------------|
| `measurement`       | The InfluxDB measurement to query.                                                                                                                            | Yes       | `"cpu"`                                      |
| `window`            | Time window for data analysis (e.g., `1h` for 1 hour). Units: `s`, `min`, `h`, `d`, `w`.                                                                      | Yes       | `"1h"`                                       |
| `catalog_configs`   | Base64-encoded JSON string containing Iceberg catalog configuration. See the [PyIceberg catalog documentation](https://py.iceberg.apache.org/configuration/). | Yes       | `"eyJ1cmkiOiAiaHR0cDovL25lc3NpZTo5MDAwIn0="` |
| `included_fields`   | Dot-separated list of field names to include in the query (optional).                                                                                         | No        | `"usage_user.usage_idle"`                    |
| `excluded_fields`   | Dot-separated list of field names to exclude from the query (optional).                                                                                       | No        | `"usage_system.usage_user"`                  |
| `namespace`         | Iceberg namespace for the table (optional, default: `"default"`).                                                                                             | No        | `"production"`                               |
| `table_name`        | Iceberg table name (optional, default: same as `measurement`).                                                                                                | No        | `"cpu_metrics"`                              |
| `config_file_path`  | Path to the configuration file from `PLUGIN_DIR` env var. Format: `'example.toml'`.                                                                           | No        | `'example.toml'`                             |


#### Schema Creation and Naming
- **Schema Creation**: 
  - If the specified Iceberg table does not exist, the plugin automatically creates it with a schema inferred from the queried data's DataFrame. The schema maps Pandas data types to corresponding Iceberg types (e.g., `int64` to `IntegerType`, `float64` to `FloatType`, `datetime64[us]` to `TimestampType`, etc.).
  - Fields are marked as `required` if they contain no null values in the DataFrame; otherwise, they are `optional`.
  - The `time` column is converted to `datetime64[us]` to ensure compatibility with Iceberg’s `TimestampType`.
- **Naming Convention**: 
  - The Iceberg table is created in the specified `namespace` (default: `"default"`) with the name specified in `table_name` (default: same as `measurement`).
  - For example, if `measurement` is `"cpu"`, `namespace` is `"monitoring"`, and `table_name` is not provided, the table will be named `"monitoring.cpu"`. If no `namespace` is specified, it defaults to `"default.cpu"`.

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename influxdb_to_iceberg.py \
  --trigger-spec "every:1h" \
  --trigger-arguments measurement=cpu,window=1h,catalog_configs="eyJ1cmkiOiAiaHR0cDovL25lc3NpZTo5MDAwIn0=",namespace=monitoring,table_name=cpu_metrics \
  influxdb_to_iceberg_trigger
```

### HTTP Plugin
The HTTP Plugin allows on-demand data replication via HTTP POST requests. It processes the request body to configure the replication parameters, including optional backfill windows and batch sizes.

#### Trigger Creation
Create an HTTP trigger using the `influxdb3 create trigger` command:
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename influxdb_to_iceberg.py \
  --trigger-spec "request:replicate" \
  influxdb_to_iceberg_http_trigger
```
This registers an HTTP endpoint at `/api/v3/engine/replicate`.

#### Enable Trigger
Enable the trigger to start processing requests:
```bash
influxdb3 enable trigger --database mydb influxdb_to_iceberg_http_trigger
```

#### Request Body Arguments
The plugin expects a JSON body with the following structure:

| Argument          | Description                                                                                                                                                 | Required  | Example                                        |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|------------------------------------------------|
| `measurement`     | The InfluxDB measurement to replicate.                                                                                                                      | Yes       | `"cpu"`                                        |
| `catalog_configs` | Configuration dictionary for Iceberg catalog loading. See the [PyIceberg catalog documentation](https://py.iceberg.apache.org/configuration/)               | Yes       | `{"type": "sql", "uri": "http://nessie:9000"}` |
| `included_fields` | List of field names to include in replication (optional).                                                                                                   | No        | `["usage_user", "usage_idle"]`                 |
| `excluded_fields` | List of field names to exclude from replication (optional).                                                                                                 | No        | `["usage_system"]`                             |
| `namespace`       | Target Iceberg namespace (optional, default: `"default"`).                                                                                                  | No        | `"production"`                                 |
| `table_name`      | Target Iceberg table name (optional, default: same as `measurement`).                                                                                       | No        | `"cpu_metrics"`                                |
| `batch_size`      | Batch size duration for processing (e.g., `"1d"`, `"12h"`). Units: `s`, `min`, `h`, `d`, `w`. Default: `"1d"`.                                              | No        | `"1d"`                                         |
| `backfill_start`  | ISO 8601 datetime string with timezone for the start of the backfill window (optional). If not provided, uses the oldest available data.                    | No        | `"2023-01-01T00:00:00+00:00"`                  |
| `backfill_end`    | ISO 8601 datetime string with timezone for the end of the backfill window (optional). If not provided, uses the current UTC time.                           | No        | `"2023-01-02T00:00:00+00:00"`                  |


#### Schema Creation and Naming
- **Schema Creation**: 
  - If the specified Iceberg table does not exist, the plugin automatically creates it with a schema inferred from the queried data's DataFrame. The schema maps Pandas data types to corresponding Iceberg types (e.g., `int64` to `IntegerType`, `float64` to `FloatType`, `datetime64[us]` to `TimestampType`, etc.).
  - Fields are marked as `required` if they contain no null values in the DataFrame; otherwise, they are `optional`.
  - The `time` column is converted to `datetime64[us]` to ensure compatibility with Iceberg’s `TimestampType`.
- **Naming Convention**: 
  - The Iceberg table is created in the specified `namespace` (default: `"default"`) with the name specified in `table_name` (default: same as `measurement`).
  - For example, if `measurement` is `"cpu"`, `namespace` is `"monitoring"`, and `table_name` is not provided, the table will be named `"monitoring.cpu"`. If no `namespace` is specified, it defaults to `"default.cpu"`.


#### Example HTTP Request
- **Replicate data with specific backfill window**:
  ```bash
  curl -X POST http://localhost:8181/api/v3/engine/replicate \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -d '{
      "measurement": "cpu",
      "catalog_configs": {
        "type": "sql",
        "uri": "http://nessie:9000"
      },
      "included_fields": ["usage_user", "usage_idle"],
      "namespace": "monitoring",
      "table_name": "cpu_metrics",
      "batch_size": "12h",
      "backfill_start": "2023-01-01T00:00:00+00:00",
      "backfill_end": "2023-01-02T00:00:00+00:00"
    }'
  ```

## Important Notes
- **Data Requirements**: Ensure that the queried measurement contains a `time` column for proper data transformation.
- **Schema Evolution**: The plugin does not handle schema evolution; if the schema changes, manual intervention may be required.
- **Performance**: 
  - For the scheduler plugin, each run creates a new file in Iceberg. Adjust the `window` parameter to avoid creating too many small files, which can degrade performance.
  - For the HTTP plugin, the `batch_size` parameter controls the size of data batches processed in each iteration. Larger batches may improve performance but require more memory.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).