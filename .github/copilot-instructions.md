# AI Assistant Instructions

This file provides guidance to AI assistants when working with code in this repository.

## Project Overview

This repository contains publicly shared plugins for InfluxDB 3. See [README.md](../README.md) for detailed project description and documentation links.

## Plugin Architecture

See [README.md](../README.md#plugin-types) for plugin types and development guidelines.

### Core Plugin Structure
Each plugin must implement specific functions based on its type:

- `process_scheduled_call(influxdb3_local, call_time, args)` - for scheduled plugins
- `process_writes(influxdb3_local, table_batches, args)` - for data write plugins  
- `process_http_request(influxdb3_local, request_body, args)` - for HTTP plugins

### Plugin Organization
See [README.md](../README.md#plugin-organization) for directory structure and naming conventions.

## Key Components

### LineBuilder Usage
Most plugins use `LineBuilder` to construct line protocol data:
```python
line = LineBuilder("measurement_name")
    .tag("tag_key", "tag_value")
    .int64_field("field_name", value)
    .time_ns(timestamp)
influxdb3_local.write(line)
```

### Configuration Management
- TOML configuration files for plugin parameters
- Environment variable support via `PLUGIN_DIR`
- Runtime argument parsing from trigger configurations

### Common Patterns
- Configuration validation with required/optional parameters
- Error handling with task IDs for logging
- Retry logic for database operations
- Caching for performance optimization

## Available Plugins

### Core InfluxData Plugins
- **Basic Transformation**: Field/tag name and value transformations with unit conversions
- **Downsampler**: Time-based aggregation and downsampling
- **Prophet Forecasting**: Time series forecasting using Prophet library
- **Threshold/Deadman Checks**: Alerting based on thresholds and data absence
- **Anomaly Detection**: MAD-based and ADTK-based anomaly detection
- **Notification System**: Multi-channel notification dispatcher

### Plugin Development
Follow the development guidelines in [README.md](../README.md#development-guidelines) and documentation standards in [STYLE_GUIDE.md](../STYLE_GUIDE.md).

## Testing Plugin Functionality

See [README.md](../README.md#plugin-installation) for plugin installation and trigger creation examples.

### Common Development Tasks
- Plugin validation is performed through the InfluxDB 3 CLI
- Configuration files use TOML format
- No traditional build/test commands - plugins are validated at runtime
- Follow [STYLE_GUIDE.md](../STYLE_GUIDE.md) for all documentation standards

## Configuration Files

See [README.md](../README.md#configuration) for plugin configuration patterns and examples.

## Dependencies and Libraries

### Common Python Libraries
- `pint` - Unit conversions
- `pandas` - Data manipulation
- `requests` - HTTP communications
- `prophet` - Time series forecasting
- `adtk` - Anomaly detection
- `psutil` - System metrics

### Plugin Dependencies
Check `plugin_library.json` for required libraries and inter-plugin dependencies.

## Error Handling Patterns

Follow the error handling standards in [STYLE_GUIDE.md](../STYLE_GUIDE.md#error-handling).

### Standard Error Response
```python
try:
    # Plugin logic
    pass
except Exception as e:
    influxdb3_local.error(f"[{task_id}] Error: {e}")
    return
```

### Logging Levels
- `influxdb3_local.info()` - General information
- `influxdb3_local.warn()` - Warnings and non-critical issues
- `influxdb3_local.error()` - Critical errors and failures

## Plugin Library Management

The `influxdata/library/plugin_library.json` file maintains metadata for all official plugins including:
- Plugin descriptions and documentation links
- Required libraries and dependencies
- Supported trigger types
- Version information