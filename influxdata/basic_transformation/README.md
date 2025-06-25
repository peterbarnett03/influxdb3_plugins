# Basic Transformation Plugin for InfluxDB 3

This plugin enables transformation of time series data stored in InfluxDB 3 (transformations are supported for field/tag names and values). It supports scheduled tasks to periodically transform data from a source measurement and write the results to a target measurement.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: Latest version.
- **Python**: Version 3.10 or higher.

## Files
- `basic_transformation.py`: The main plugin code containing handlers for scheduled tasks.

## Features
- **Scheduled Tasks**: Periodically performs data transformation on specified InfluxDB measurements.
- **Data Transformation**: Applies transformations to field names and values based on predefined and custom rules.
- **Data Writing**: Writes transformed data to a specified InfluxDB measurement.
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
- Place `basic_transformation.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
```bash
influxdb3 install package pint
```

## Configure & Create Triggers

### Scheduled Tasks
The Scheduled Tasks feature periodically performs data transformation on the specified InfluxDB measurement, using the provided configuration to transform field names and values, and writes the transformed data to a target measurement.

#### Arguments
The following arguments are extracted from the `args` dictionary:

| Argument                   | Description                                                                                                                                                            | Required    | Example                                                       |
|----------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|---------------------------------------------------------------|
| `measurement`              | The InfluxDB measurement to query for historical data.                                                                                                                 | Yes         | `"temperature"`                                               |
| `window`                   | Historical window duration for data retrieval (e.g., `30d`). Format: `<number><unit>` where unit is `s`, `min`, `h`, `d`, `w`, `m`, `q`, `y`.                          | Yes         | `"30d"`                                                       |
| `target_measurement`       | Destination measurement for storing transformed data.                                                                                                                  | Yes         | `"transformed_temperature"`                                   |
| `names_transformations`    | Rules for transforming field and tag names. Format: `'field1:"transform1 transform2".pattern_name:"transform3 transform4'`.                                            | Yes         | `'room:"lower snake".temp:"upper".name:"custom_replacement"'` |
| `values_transformations`   | Rules for transforming field values. Format: `'field1:"transform1 transform2".pattern:"transform3"'`.                                                                  | Yes         | `'temp:"convert_C_to_F".hum:"upper".something:"lower"'`       |
| `target_database`          | Optional InfluxDB database name for writing transformed data.                                                                                                          | No          | `"transformed_db"`                                            |
| `included_fields`          | Dot-separated list of field names to include in the query.                                                                                                             | No          | `"temp.hum.something"`                                        |
| `excluded_fields`          | Dot-separated list of field names to exclude from the query.                                                                                                           | No          | `"co.h-u_m2"`                                                 |
| `dry_run`                  | If `"true"`, simulates the transformation without writing to the database. Defaults to `"false"`.                                                                      | No          | `"true"`                                                      |
| `custom_replacements`      | Custom replacement rules for transformations. Format: `'replace_space_underscore:" =_".cust_replace:"Some text=Another text"'`.                                        | No          | `'replace_space_underscore:" =_"'`                            |
| `custom_regex`             | Custom regex patterns for applying transformations. Format: `'regex_temp:"temp%"'`. Just `%` (zero, one or more) and `_` (exactly one) are allowed in regex patterns   | No          | `'regex_temp:"temp%"'`                                        |
| `filters`                  | Filters for querying specific data. Format: `'field:"=value".field2:">value2"'`. Supported operators: `=`, `!=`, `>`, `<`, `>=`, `<=`.                                 | No          | `'temp:>=101.hum:<=182'`                                      |

#### Example
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename data_transformation.py \
  --trigger-spec "every:1d" \
  --trigger-arguments measurement=temperature,window=30d,target_measurement=transformed_temperature,names_transformations='room:"lower".temp:"snake"',values_transformations='temp:"convert_C_to_F".something:"upper"' \
  data_transform_trigger
```

## Available Transformations
The plugin supports the following predefined transformations for both names and values:

| Transformation           | Description                                                                                          |
|--------------------------|------------------------------------------------------------------------------------------------------|
| `lower`                  | Converts the string to lowercase.                                                                    |
| `upper`                  | Converts the string to uppercase.                                                                    |
| `space_to_underscore`    | Replaces spaces with underscores.                                                                    |
| `remove_space`           | Removes all spaces from the string.                                                                  |
| `alnum_underscore_only`  | Keeps only alphanumeric characters and underscores, removing all other characters.                   |
| `collapse_underscore`    | Collapses multiple consecutive underscores into a single underscore.                                 |
| `trim_underscore`        | Trims underscores from the beginning and end of the string.                                          |
| `snake`                  | Converts the string to snake_case (lowercase with underscores).                                      |

## Transformation Logic
- **Specific Field Transformations**: If a field or tag is explicitly specified in the transformation rules (e.g., `temp:"snake"`), the transformations are applied only to that field or tag, and regex patterns are not applied to it.
- **Regex-based Transformations**: If a regex pattern is specified in the transformation rules (e.g., `regex_temp:"temp%"` in `custom_regex`), the transformations are applied to all fields or tags that match the pattern, except those that are explicitly specified. You should use `%` (zero, one or more) and `_` (exactly one) in the regex patterns. To use this custom regex, you need to specify transformation rules for regex_temp in `values_transformations` or `names_transformations` (e.g., `regex_temp:"snake lower"`). 
- **Order of Application**: Transformations are applied in the order they are specified in the rules.

## Custom Transformations
- **Unit Conversions**: Use `convert_<from>_to_<to>` to convert units of measurement (e.g., `convert_C_to_F` for Celsius to Fahrenheit). The plugin uses the `pint` library [link to the documentation](https://pint.readthedocs.io/en/stable/) for unit conversions and supports temperature conversions (e.g., `degC`, `degF`, `kelvin`, `degR`) as well as other units like length or time.
- **Custom Replacements**: Define custom string replacements using the `custom_replacements` parameter. For example, `'replace_space_underscore:" =_"'` replaces spaces with underscores in the specified fields or values.

## Error Handling
- If a transformation fails (e.g., due to incompatible types or units), the plugin logs a warning in the `system.processing_engine_logs` table and retains the original value unchanged.
- Errors during data writing are handled with a retry mechanism (up to 3 attempts) before logging an error.

## Usage Examples
### Example 1: Basic Transformation
Transform the `temperature` measurement by converting field names to lowercase and values to uppercase.

```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename data_transformation.py \
  --trigger-spec "every:1d" \
  --trigger-arguments measurement=temperature,window=30d,target_measurement=transformed_temperature,names_transformations='room:"lower".temp:"lower"',values_transformations='room:"upper".something:"upper"' \
  data_transform_trigger
```

### Example 2: Using Custom Replacements
Transform the `temperature` measurement by replacing spaces with underscores in field names and values.

```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename data_transformation.py \
  --trigger-spec "every:1d" \
  --trigger-arguments measurement=temperature,window=30d,target_measurement=transformed_temperature,names_transformations='room:"replace_space_underscore"',values_transformations='room:"replace_space_underscore"',custom_replacements='replace_space_underscore:" =_"' \
  data_transform_trigger
```

### Example 3: Using Regex Patterns
Transform all fields starting with `temp` by converting their values to Fahrenheit.

```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename data_transformation.py \
  --trigger-spec "every:1d" \
  --trigger-arguments measurement=temperature,window=30d,target_measurement=transformed_temperature,values_transformations='regex_temp:"convert_C_to_F"',custom_regex='regex_temp:"temp%"' \
  data_transform_trigger
```

## Important Notes
- **Data Requirements**: The queried measurement must contain a `time` column and the specified fields for transformation.
- **Field Inclusion/Exclusion**: Only one of `included_fields` or `excluded_fields` can be specified. If both are provided, the plugin will raise an error.
- **Dry Run Mode**: When `dry_run` is set to `"true"`, the plugin logs the transformed data without writing it to the database, allowing for testing and validation.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).