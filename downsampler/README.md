# InfluxDB 3 Downsampling Plugin  
  
This plugin enables downsampling of data in an InfluxDB 3 Core/Enterprise instance and writes the results to a target measurement and database. It supports flexible configuration for time intervals, field aggregations, tag filtering, and batch processing, with robust error handling and retry logic. The plugin can be triggered via a scheduler for periodic downsampling or through HTTP requests for on-demand processing.  
  
## Prerequisites  
- **InfluxDB v3 Core**: Public beta (March 29, 2025) or later.  
- **Python**: 3.10 or higher.
  
## Files  
- `downsampler.py`: The main plugin code for downsampling data.  
- No additional configuration files are provided, as the plugin is configured via trigger arguments or HTTP request bodies.  
  
## Features  
- **Flexible Downsampling**: Aggregate data over specified time intervals (e.g., seconds, minutes, hours, days, weeks, months, quarters, or years) using functions like `avg`, `sum`, `min`, `max`, or `derivative`.  
- **Field and Tag Filtering**: Select specific fields for aggregation and filter by tag values.  
- **Scheduler and HTTP Support**: Run periodically via InfluxDB triggers or on-demand via HTTP requests.  
- **Retry Logic**: Configurable retries for robust write operations.  
- **Batch Processing**: Process large datasets in configurable time batches for HTTP requests.  
- **Backfill Support**: Downsample historical data within a specified time window.
- **Task ID Tracking**: Each execution generates a unique task_id included in logs and error messages for traceability.
- **Metadata Columns**: Each downsampled record includes three additional columns:  
  - `record_count` — the number of original points compressed into this single downsampled row,  
  - `time_from` — the minimum timestamp among the original points in the interval,  
  - `time_to` — the maximum timestamp among the original points in the interval.  

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
| 2025-05-14T16:31:10.033275724 | my_scheduler    | INFO         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Downsampling job finished in 0.021356821060180664 seconds         |
| 2025-05-14T16:31:10.033232792 | my_scheduler    | INFO         | [4726cf36-3b15-442e-bd9d-f9b768ad8781] Successful write to home_downsampled                              |
| 2025-05-14T16:31:10.011881111 | some_scheduler  | INFO         | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Starting downsampling schedule for call_time: 2025-05-14 16:31:10 |
| 2025-05-14T16:31:10.001837231 | some_scheduler  | INFO         | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Starting execution with scheduled time 2025-05-14 16:31:10 UTC    |
| 2025-05-14T16:31:00.046641074 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Finished execution in 44ms 724us 139ns                            |
| 2025-05-14T16:31:00.046623022 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Downsampling job finished in 0.021102190017700195 seconds         |
| 2025-05-14T16:31:00.046579787 | some_scheduler  | ERROR        | [528a316e-b28c-4bd2-8c05-07ad50bc1de2] Error during write to home_downsampled                            |
| 2025-05-14T16:31:00.025482558 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] Starting downsampling schedule for call_time: 2025-05-14 16:31:00 |
| 2025-05-14T16:31:00.001903138 | my_scheduler    | INFO         | [cd5caa89-47db-443c-9621-5f90a129a0cc] starting execution with scheduled time 2025-05-14 16:31:00 UTC    |
+-------------------------------+--------------+-----------+----------------------------------------------------------------------------------------------------------------+

```

### Log Columns Description

-   **event_time**: Timestamp of the log event (with nanosecond precision).
-   **trigger_name**: Name of the trigger that generated the log (e.g., `my_scheduler`).
-   **log_level**: Severity level of the log entry (`INFO`, `WARN`, `ERROR`, etc.).
-   **log_text**: Message describing the action, status, or error encountered by the plugin with task_id.
  
## Setup, Run & Test  
  
### 1. Install & Run InfluxDB v3 Core/Enterprise  
- Download and install InfluxDB v3 Core/Enterprise from the official site or package manager.  
- Ensure the `plugins` directory exists; if not, create it:  
  ```bash  
  mkdir ~/.plugins 
  ```
 - Place `downsampler.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths for plugins and data directories:  
  ```bash  
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins 
  ```  
  
 
### 2. Configure & Create Trigger (Scheduler mode)  
Create a trigger for the plugin using the `influxdb3 create trigger` command.  
  
 #### Example
Example command to create a scheduler trigger for downsampling in the database `mydb`:  
```bash  
influxdb3 create trigger \
  --database mydb \
  --plugin-filename downsampler.py \
  --trigger-spec "every:10s" \
  --trigger-arguments source_measurement=home,target_measurement=home_downsampled,tag_values=room:Kitchen@LivingRoom@Bedroom@"Some value string",specific_fields=hum.co,interval=7min,window=10s \
  downsampling_trigger  
```

#### Arguments (Scheduler Mode)  
The following arguments are supported in the `--trigger-arguments` string for scheduler-based triggers:  
  
| Argument              | Description                                                                | Constraints                                                                                                                                                                                              | Default                 |  
|-----------------------|----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------|  
| `source_measurement`  | Name of the source measurement to downsample.                              | Must be an existing measurement in the database. **Required.**                                                                                                                                           | `None`                  |  
| `target_measurement`  | Name of the target measurement to write downsampled data.                  | **Required.**                                                                                                                                                                                            | `None`                  |  
| `interval`            | Time interval for downsampling (e.g., `10min`, `2h`, `1m`, `1y`).          | Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`, `m`, `q`, `y`. Number ≥ 1. Months (`m`), quarters (`q`), and years (`y`) are converted to days (30.42, 91.25, 365 days, respectively). | `10min`                 |  
| `window`              | Time window for each downsampling job (e.g., `1h`, `1d`).                  | Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`. Number ≥ 1. **Required.**                                                                                                              | `None`                  |  
| `offset`              | Time offset to apply to the window (e.g., `10min`, `1h`).                  | Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`. Number ≥ 1.                                                                                                                                 | `0`                     |  
| `calculations`        | Aggregation functions (e.g., `avg` or `field1:avg.field2:sum`).            | Either a single function (`avg`, `sum`, `min`, `max`, `derivative`, `median`) or a dot-separated list of `field:aggregation` pairs.                                                                      | `avg`                   |  
| `specific_fields`     | Fields to downsample (e.g., `co.temperature`).                             | Dot-separated field names matching `^[a-zA-Z]+(\.[a-zA-Z]+)*$`. Optional. Non-existent fields are ignored with a warning.                                                                                | All aggregatable fields |  
| `excluded_fields`     | Fields to exclude from downsampling (e.g., `field1.field2`).               | Dot-separated field names matching `^[a-zA-Z]+(\.[a-zA-Z]+)*$`. Optional. Non-existent fields are ignored with a warning.                                                                                | `None`                  |  
| `tag_values`          | Tag filters (e.g., `room:Kitchen@Bedroom@"My room"`).                      | Dot-separated `tag:value1@value2` pairs matching the required pattern. Optional. Non-existent tags are ignored with a warning.                                                                           | `None`                  |  
| `max_retries`         | Maximum number of retries for write operations.                            | Integer ≥ 0.                                                                                                                                                                                             | `5`                     |  
| `target_database`     | Target database for writing downsampled data (e.g., for remote instances). | Optional. If not provided, uses the local database.                                                                                                                                                      | `None`                  |  
  
#### Enable Trigger  
Enable the trigger to start periodic downsampling:  
```bash  
influxdb3 enable trigger --database mydb downsampling_trigger
```  
  
### 3. Configure & Create Trigger (HTTP Request Mode)  
The plugin also supports on-demand downsampling via HTTP requests. Send a POST request to the InfluxDB 3 HTTP endpoint with a JSON body containing the parameters.  

Create an HTTP-triggered plugin using the `influxdb3 create trigger` command. This trigger will expose an HTTP endpoint that can be called to execute the plugin manually.

#### Example
The following command creates an HTTP trigger for downsampling in the database `mydb`:

```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename downsampler.py \
  --trigger-spec "request:downsample" \
  downsampling_http_trigger
```

This command registers an HTTP endpoint at:

```
/api/v3/engine/downsample
```

To invoke the plugin, send an HTTP `POST` request to the endpoint. For example:

```bash
curl -X POST http://localhost:8181/api/v3/engine/downsample
```

> **Note:**  
> - Use `--trigger-spec "request:<ENDPOINT_PATH>"` to define the HTTP endpoint path.  
> - The plugin receives the full HTTP request object, including method, headers, and body.  

#### Arguments (HTTP Mode)

The JSON body supports the following parameters:

| Argument              | Description                                                                            | Constraints                                                                                                                       | Default                           |
|-----------------------|----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|-----------------------------------|
| `source_measurement`  | Name of the source measurement to downsample.                                          | Must be an existing measurement in the database. **Required.**                                                                    | `None`                            |
| `target_measurement`  | Name of the target measurement to write downsampled data.                              | **Required.**                                                                                                                     | `None`                            |
| `interval`            | Time interval for downsampling (e.g., `10min`, `2h`, `1m`, `1y`).                      | Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`, `m`, `q`, `y`. Number ≥ 1. `m`, `q`, `y` are converted to days. | `10min`                           |
| `batch_size`          | Time interval for batch processing (e.g., `1h`, `1d`).                                 | Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`. Number ≥ 1.                                                          | `30d`                             |
| `calculations`        | Aggregation functions. Either `"avg"` or a list of `['field', 'aggregation']`.         | Valid aggregations: `avg`, `sum`, `min`, `max`, `derivative`, `median`.                                                           | `"avg"`                           |
| `specific_fields`     | List of fields to downsample (e.g., `["usage_user", "usage_system"]`).                 | Must be valid field names. Non-existent fields are ignored with a warning. Optional.                                              | All aggregatable fields           |
| `excluded_fields`     | List of fields to exclude (e.g., `["usage_idle"]`).                                    | Must be valid field names. Non-existent fields are ignored with a warning. Optional.                                              | `None`                            |
| `tag_values`          | Dictionary of tag names to lists of values (e.g., `{"host": ["server1", "server2"]}`). | Non-existent tags are ignored with a warning. Optional.                                                                           | `None`                            |
| `backfill_start`      | Start time for backfill (e.g., `2025-05-01T00:00:00+03:00`).                           | Format: `YYYY-MM-DDTHH:MM:SS±HH:MM` (ISO 8601). Must be earlier than `backfill_end`. Optional.                                    | Earliest timestamp in measurement |
| `backfill_end`        | End time for backfill (e.g., `2025-05-02T00:00:00+03:00`).                             | Format: `YYYY-MM-DDTHH:MM:SS±HH:MM` (ISO 8601). Optional.                                                                         | Current time                      |
| `max_retries`         | Maximum number of retries for write operations.                                        | Integer ≥ 0.                                                                                                                      | `5`                               |
| `target_database`     | Target database for writing downsampled data.                                          | Optional. If not provided, uses the same database.                                                                                | `None`                            |


#### Example HTTP Request  
```bash  
curl -X POST http://localhost:8181/api/v3/engine/webhook \
-H "Authorization: Bearer YOUR_TOKEN" \
-d '{
    "source_measurement": "home",
    "target_measurement": "home_downsampled",
    "target_database": "mydb",
    "tag_values": {
      "room": ["Kitchen", "LivingRoom"]
    },
    "calculations": [["co", "avg"], ["co", "max"], ["co", "min"]],
    "specific_fields": ["co"],
    "interval": "10s",
    "batch_size": "1h",
    "max_retries": 5
  }'
```  
 
  
## Questions/Comments  
Hope this plugin use useful. If any questions/issues, please feel free to open a GitHub issue and find us comments on [Discord](https://discord.com/invite/vZe2w2Ds8B) in the #influxdb3_core channel, [Slack](https://influxcommunity.slack.com/join/shared_invite/zt-2z3n3fs0i-jnF9Ag6NVBO26P98iY_h_g#/shared-invite/email) in the #influxdb3_core channel, or our [Community Forums](https://community.influxdata.com/).