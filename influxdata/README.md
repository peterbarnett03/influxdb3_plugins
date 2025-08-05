# influxdata

Official Python plugins for InfluxDB 3, developed by InfluxData.

## Available Plugins

See each plugin's README for details on configuration, requirements, and usage.

## Plugin metadata

These plugins include a JSON metadata schema in their docstring that defines supported trigger types and configuration parameters. This metadata enables the [InfluxDB 3 Explorer](https://docs.influxdata.com/influxdb3/explorer/) UI to display and configure the plugin.

## Test the plugins

From the repository root, use Docker Compose to run tests against the InfluxDB 3 Core image:

```bash
# Test all influxdata plugins
docker compose --profile test run --rm test-core-all

# Test specific plugin
PLUGIN_PATH="influxdata/basic_transformation" \
docker compose --profile test run --rm test-core-specific

# Test with TOML configuration
PLUGIN_PATH="influxdata/basic_transformation" \
PLUGIN_FILE="basic_transformation.py" \
TOML_CONFIG="basic_transformation_config_scheduler.toml" \
docker compose --profile test run --rm test-core-toml
```

See the [compose file](/compose.yml) for details on the test setup.

## Support

For additional support with InfluxData plugins, visit:

- [Discord](https://discord.com/invite/influxdata) - #influxdb3_core channel
- [Community Forums](https://community.influxdata.com/)
- [GitHub Issues](https://github.com/influxdata/influxdb3_plugins/issues)
