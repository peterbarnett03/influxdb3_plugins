
# InfluxDB 3 Data Replicator Plugin

This plugin replicates data from a local InfluxDB 3 Core/Enterprise instance to a remote InfluxDB 3 instance. It supports filtering of tables and fields, renaming of tables and fields. The plugin can be triggered via a scheduler or data write triggers.

## Prerequisites
- **InfluxDB v3 Core**: Public beta (March 29, 2025) or later.
- **Python**: 3.10 or higher.

## Files
- `data_replicator.py`: The main plugin code for data replication.

## Features
- **Data Replication**: Replicate data from a local InfluxDB 3 instance to a remote one.
- **Filtering**: Specify which tables to replicate and which fields to exclude.
- **Renaming**: Rename tables and fields during replication.
- **Downsampling**: When enabled, downsample all data within the specified time window for scheduled triggers, or for each individual run for data writes triggers.
- **Scheduler and Data write Support**: Run periodically or on data writes via InfluxDB triggers.
- **Queue Management**: Use a compressed JSONL queue file for reliable delivery.
- **Retry Logic**: Handle errors and rate limits with retry mechanisms.

## Logging

During execution, the plugin writes internal logs into the InfluxDB `_internal` database, in the `system.processing_engine_logs` table. You can inspect the most recent log entries with:

```bash
influxdb3 query --database _internal "SELECT * FROM system.processing_engine_logs"
```

Example output:

```text
+-------------------------------+-----------------+--------------+----------------------------------------------------------------------------------------------------------+
| event_time                    | trigger_name    | log_level    | log_text                                                                                                 |
+-------------------------------+-----------------+--------------+----------------------------------------------------------------------------------------------------------+
| 2025-05-14T16:31:10.033295886 | my_scheduler    | INFO         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Finished execution in 31ms 449us 193ns                            |
| 2025-05-14T16:31:10.033275724 | my_scheduler    | INFO         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Replicated 10 lines to remote instance                            |
| 2025-05-14T16:31:10.033232792 | my_scheduler    | INFO         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Queued 10 lines from table1,table2                                |
| 2025-05-14T16:31:10.011881111 | some_scheduler  | INFO         | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Starting data replication process                                 |
| 2025-05-14T16:31:10.001837231 | some_scheduler  | INFO         | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Starting execution with scheduled time 2025-05-14 16:31:10 UTC    |
| 2025-05-14T16:31:00.046641074 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Finished execution in 44ms 724us 139ns                            |
| 2025-05-14T16:31:00.046623022 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Replicated 5 lines to remote instance                             |
| 2025-05-14T16:31:00.046579787 | some_scheduler  | ERROR        | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Error during replication: Connection failed                       |
| 2025-05-14T16:31:00.025482558 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Starting data replication process                                 |
| 2025-05-14T16:31:00.001903138 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Starting execution with scheduled time 2025-05-14 16:31:00 UTC    |
+-------------------------------+--------------+-----------+----------------------------------------------------------------------------------------------------------------+
```

### Log Columns Description

-   **event_time**: Timestamp of the log event (with nanosecond precision).
-   **trigger_name**: Name of the trigger that generated the log (e.g., `my_scheduler`).
-   **log_level**: Severity level of the log entry (`INFO`, `WARN`, `ERROR`, etc.).
-   **log_text**: Message describing the action, status, or error encountered by the plugin with task_id.
- 

## Queue Management

The plugin uses a compressed JSONL queue file to ensure reliable data delivery.

### File Location
- **Default**: `~/.plugins` (if `PLUGIN_DIR` is not set).
- **Custom**: Set via the `PLUGIN_DIR` environment variable.

### File Name
- **Data Writes Mode**: `edr_queue_writes.jsonl.gz`
- **Schedule Mode**: `edr_queue_schedule.jsonl.gz`

### File Format
- Compressed with **gzip**.
- Uses **JSON Lines (JSONL)** format, where each line is a JSON object.

### File Purpose
- Temporarily stores data before replication.
- Ensures reliability by retaining data until successfully sent.

### File Management
- **Maximum Size**: Controlled by `max_size` (default 1024 MB). Exceeding this raises an error.
- **Cleanup**: Data is removed from the file after successful replication.

### Notes
- Monitor file size to avoid disk overflow.


## Setup, Run & Test

### 1. Install & Run InfluxDB v3 Core/Enterprise
- Download and install InfluxDB v3 Core/Enterprise from the official site or package manager.
- Ensure the `plugins` directory exists; if not, create it:
  ```bash
  mkdir ~/.plugins
  ```
- Place `data_replicator.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths for plugins and data directories:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Configure & Create Trigger (Scheduler Mode)

Create a trigger for the plugin using the `influxdb3 create trigger` command.

#### Example
Example command to create a scheduler trigger for data replication in the database `mydb`:
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename data_replicator.py \
  --trigger-spec "every:10s" \
  --trigger-arguments host=<remote_host>,token=<remote_token>,database=<remote_db>,tables=table1.table2 \
  data_replicator_trigger
```

#### Arguments (Scheduler Mode)
The following arguments are supported in the `--trigger-arguments` string for scheduler-based triggers:

| Argument              | Description                                                    | Constraints                                                                             | Default |
|-----------------------|----------------------------------------------------------------|-----------------------------------------------------------------------------------------|---------|
| `host`                | Remote InfluxDB host URL.                                      | Required. (`http://127.0.0.1`, `12.4.0.1`, `https://12.4.0.1`)                          | `None`  |
| `token`               | Remote InfluxDB API token.                                     | Required.                                                                               | `None`  |
| `database`            | Remote database name.                                          | Required.                                                                               | `None`  |
| `source_measurement`  | The name of table to replicate.                                | Required.                                                                               | `None`  |
| `max_size`            | Maximum size for the queue file in MB.                         | Integer ≥ 1.                                                                            | `1024`  |
| `verify_ssl`          | Whether to verify SSL certificates when connecting via HTTPS.  | True or False. Optional.                                                                | `true`  |
| `port_override`       | Override the default write port (e.g., 8181).                  | Integer port number. Optional.                                                          | `443`   |
| `max_retries`         | Maximum number of retries for write operations.                | Integer ≥ 0.                                                                            | `3`     |
| `excluded_fields`     | String defining fields to exclude per table.                   | Format: `<table1>:<field1>@<field2>.<table2>:<field3>...`                               | `None`  |
| `tables_rename`       | String defining table renames.                                 | Format: `<old_table1>:<new_table1>.<old_table2>:<new_table2>...`                        | `None`  |
| `field_renames`       | String defining field renames per table.                       | Format: `table1:oldA@newA$oldB@newB.table2:oldX@newX$oldY@newY`                         | `None`  |
| `offset`              | Time offset to apply to the window (e.g., `10min`, `1h`).      | Format: `<number><unit>` where unit is `min`, `h`, `d`, `w`. Number ≥ 1.                | `0`     |
| `window`              | Time window for each replication job (e.g., `1h`, `1d`).       | Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`. Number ≥ 1. Required. | `None`  |

#### Enable Trigger
Enable the trigger to start periodic replication:
```bash
influxdb3 enable trigger --database mydb data_replicator_trigger
```



### 3. Configure & Create Trigger (Data write Mode)

The Data Replicator Plugin can be configured to automatically replicate data whenever data is written to the local InfluxDB database and the Write-Ahead Log (WAL) is flushed. This is achieved by creating a trigger, which executes the plugin each time a write operation is committed to the database.

#### Example
The following command creates a Data write trigger for replication in the database `mydb`:

```bash
influxdb3 create trigger \
  --database mydb \
  --trigger-spec "all_tables" \
  --plugin-filename data_replicator.py \
  --trigger-arguments host=<remote_host>,token=<remote_token>,database=<remote_db>,tables=table1.table2,aggregate_interval=1m \
  data_replicator_trigger
```

#### Arguments (Data write Mode)
The following arguments are supported in the `--trigger-arguments` string for data write trigger:

| Argument              | Description                                                      | Constraints                                                                  | Default  |
|-----------------------|------------------------------------------------------------------|------------------------------------------------------------------------------|----------|
| `host`                | Remote InfluxDB host URL.                                        | Required. (`http://127.0.0.1`, `12.4.0.1`, `https://12.4.0.1`)               | `None`   |
| `token`               | Remote InfluxDB API token.                                       | Required.                                                                    | `None`   |
| `database`            | Remote database name.                                            | Required.                                                                    | `None`   |
| `tables`              | Dot-separated list of tables to replicate.                       | Optional. If not provided, all tables are replicated.                        | `None`   |
| `verify_ssl`          | Whether to verify SSL certificates when connecting via HTTPS.    | True or False. Optional.                                                     | `true`   |
| `port_override`       | Override the default write port (e.g., 8181).                    | Integer port number. Optional.                                               | `443`    |
| `max_retries`         | Maximum number of retries for write operations.                  | Integer ≥ 0.                                                                 | `3`      | 
| `max_size`            | Maximum size for the queue file in MB.                           | Integer ≥ 1.                                                                 | `1024`   |
| `excluded_fields`     | String defining fields to exclude per table.                     | Format: `<table1>:<field1>@<field2>.<table2>:<field3>...`                    | `None`   |
| `tables_rename`       | String defining table renames.                                   | Format: `<old_table1>:<new_table1>.<old_table2>:<new_table2>...`             | `None`   |
| `field_renames`       | String defining field renames per table.                         | Format: `table1:oldA@newA$oldB@newB.table2:oldX@newX$oldY@newY`              | `None`   |

#### Enable Trigger
To start replication on WAL flush events, enable the trigger with the following command:

```bash
influxdb3 enable trigger --database mydb data_replicator_trigger
```

> **Note:**
> - The plugin is automatically triggered whenever the WAL is flushed, which happens after data is written.
> - The plugin processes the batches of data written to the database, using the arguments specified in `--trigger-arguments`.

## Questions/Comments
If you have questions or encounter issues, please open a GitHub issue or reach out on [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/join/shared_invite/zt-2z3n3fs0i-jnF9Ag6NVBO26P98iY_h_g#/shared-invite/email) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).