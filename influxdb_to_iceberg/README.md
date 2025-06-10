# InfluxDB to Iceberg Data Transfer Plugin for InfluxDB 3

This plugin transfers data from InfluxDB 3 to Apache Iceberg tables. It operates as a scheduler plugin, periodically querying specified measurements within a time window, transforming the data, and appending it to an Iceberg table.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: Latest version.
- **Python**: Version 3.10 or higher.

## Files
- `influxdb_to_iceberg.py`: The main plugin code containing the handler for the `scheduler` trigger.

## Features
- **Scheduler Plugin**: Periodically queries InfluxDB measurement within a specified time window.
- **Data Transformation**: Converts InfluxDB query results to a format suitable for Iceberg tables.
- **Schema Management**: Automatically creates the Iceberg table schema based on the queried data if the table does not exist.
- **Namespace and Table Naming**: Allows customization of Iceberg namespace and table names, defaulting to "default" namespace and the measurement name for the table.
- **Field Filtering**: Supports including or excluding specific fields from the query results.

## Logging
Logs are stored in the `_internal` database (or exactly the name of the database where the trigger is created) in the `system.processing_engine_logs` table. To view logs, use the following query:

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
> - You should provide additional packages while installing `pyiceberg` as needed for your specific use case base on what type of Iceberg catalog you are using. See the [PyIceberg documentation](https://py.iceberg.apache.org/#installation) for more details.


## Configure & Create Triggers

### Scheduler Plugin
The Scheduler Plugin periodically queries the specified InfluxDB measurement within a time window, transforms the data, and appends it to an Iceberg table. It handles schema creation and ensures the table exists before appending data.

#### Arguments
The following arguments are extracted from the `args` dictionary:

| Argument          | Description                                                                                                                                                  | Required  | Example                                      |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|----------------------------------------------|
| `measurement`     | The InfluxDB measurement to query.                                                                                                                           | Yes       | `"cpu"`                                      |
| `window`          | Time window for data analysis (e.g., `1h` for 1 hour). Units: `s`, `min`, `h`, `d`, `w`.                                                                     | Yes       | `"1h"`                                       |
| `catalog_configs` | Base64-encoded JSON string containing Iceberg catalog configuration. See the [PyIceberg catalog documentation](https://py.iceberg.apache.org/configuration/) | Yes       | `"eyJ1cmkiOiAiaHR0cDovL25lc3NpZTo5MDAwIn0="` |
| `included_fields` | Dot-separated list of field names to include in the query (optional).                                                                                        | No        | `"usage_user.usage_idle"`                    |
| `excluded_fields` | Dot-separated list of field names to exclude from the query (optional).                                                                                      | No        | `"usage_system"`                             |
| `namespace`       | Iceberg namespace for the table (optional, default: `"default"`).                                                                                            | No        | `"production"`                               |
| `table_name`      | Iceberg table name (optional, default: same as `measurement`).                                                                                               | No        | `"cpu_metrics"`                              |

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

## Important Notes
- **Data Requirements**: Ensure that the queried measurement contains a `time` column for proper data transformation.
- **Schema Evolution**: The plugin does not handle schema evolution; if the schema changes, manual intervention may be required.
- **Performance**: Each time the plugin runs, Iceberg creates a new file in the data storage. To avoid a large number of files, which can degrade performance, it is necessary to adjust the window parameter.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).