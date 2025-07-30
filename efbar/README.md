## Prometheus Metrics Plugin for InfluxDB 3

⚡ scheduled 🏷️ system-metrics, monitoring 🔧 InfluxDB 3 Core, InfluxDB 3 Enterprise

This plugin scrapes metrics from a Prometheus endpoint and writes them to InfluxDB 3. It is designed to run on a schedule, allowing you to collect metrics at regular intervals.

1. Install the plugin's Python dependencies:

   ```bash
   influxdb3 install package requests
   influxdb3 install package prometheus_client
   ```

2. Create a database to use for the metrics:

   ```bash
   influxdb3 create database metrics
   ```

3. Save the plugin file in your configured `--plugin-dir`.

4. Create a trigger to run the plugin on a schedule:

   ```bash
   influxdb3 create trigger \
     --trigger-spec "every:10s" \
     --plugin-filename <path_to_file>/prometheus_metrics.py \
     --database metrics \
     --trigger-arguments "hostname=localhost,ip_address=100.100.100.100,port=80" \
     tailscale-localhost-metrics
   ```

The schedule trigger runs the plugin every 10 seconds and to scrape your local Tailscale service (more here <https://tailscale.com/kb/1482/client-metrics>) and write the metrics to the `metrics` database.

1. Query the metrics to see the results:

   ```bash
   influxdb3 query --database=metrics "SELECT * FROM tailscaled_inbound_bytes_total WHERE host='localhost'"
   ```

   ```bash
   influxdb3 query --database=metrics "SELECT path,value,time FROM tailscaled_inbound_bytes_total WHERE host='localhost' AND path='derp' ORDER BY time ASC"
   +------+-----------+-------------------------------+
   | path | value     | time                          |
   +------+-----------+-------------------------------+
   | derp | 2681308.0 | 2025-02-24T09:35:50.027185292 |
   | derp | 2688844.0 | 2025-02-24T09:36:00.027418810 |
   | derp | 2696380.0 | 2025-02-24T09:36:10.016980230 |
   | derp | 2703916.0 | 2025-02-24T09:36:20.018751834 |
   | derp | 2711452.0 | 2025-02-24T09:36:30.021800981 |
   | derp | 2719324.0 | 2025-02-24T09:36:40.023237792 |
   +------+-----------+-------------------------------+
   ```
