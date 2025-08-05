# **Python Plugins for Processing Engine**

This **WAL plugin** automatically collects statistical metrics for a table whenever data is written to it. It generates a new table that records the following statistics for each numerical column:

- **Min**, **Max**  
- **Mean**, **Median**, **Mode**  
- **95th Percentile**  

This functionality is similar to the `.describe()` method in Python, which summarizes numerical columns in a DataFrame.

## **Prerequisites**

Ensure a database exists before using the plugin:

```bash
influxdb3 create database <database_name>
```

## **Setting Up the Trigger**

Once the database is created, set up the trigger with the following command:(Make sure to include the table for which you want to collect the statistics in **--trigger-spec** and **--trigger-arguments**)

```bash
influxdb3 create trigger \
  --database <database-name> \
  --trigger-spec 'table:<table-name>' \
  --trigger-arguments 'table_name:<table-name>' \
  --plugin-filename <path-to-file>/stats_metrics.py stats_metrics_trigger
```

## **Enabling the Trigger**

After creating the trigger, enable it to start capturing statistical metrics whenever new data is written:

```bash
influxdb3 enable trigger --database <database-name> stats_metrics_trigger
```

Write data into the database using:

```bash
influxdb3 write --database <database-name> --file <lp-file-name.lp>
```

### **Generated Table Example**

When data is written to the specified table (e.g., `sensor_data`), the plugin creates a corresponding analytics table (`analytics_<table-name>`) that stores computed statistics:

```bash
------------+--------------------+--------------------+-----------------------+--------------------+--------------------+---------------------+
| field_name | min                | max                | mean                  | median             | mode               | 95th_percentile    |
+------------+--------------------+--------------------+-----------------------+--------------------+--------------------+--------------------+
| co         | 0.0011705085484379 | 0.0072680285963655 | 0.004494020980943046  | 0.0043415449971564 | 0.0014023067180012 | 0.0067827228544403 |
| humidity   | 16.600000381469727 | 92.0               | 63.77917173040387     | 60.70000076293945  | 77.19999694824219  | 79.30000305175781  |
| light      | 0.0                | 1.0                | 0.25358220551831306   | 0.0                | 0.0                | 1.0                |
| lpg        | 0.0026934786226618 | 0.0100926106082718 | 0.0069926626347598594 | 0.006952254607111  | 0.003069572712416  | 0.0096004658551668 |
| motion     | 0.0                | 1.0                | 0.000831180095043637  | 0.0                | 0.0                | 0.0                |
| smoke      | 0.0066920963173865 | 0.0274389440348949 | 0.018612339797727463  | 0.0184269059272954 | 0.0076947918250824 | 0.0260121274822193 |
| temp       | 0.3000000119209289 | 28.899999618530273 | 22.259955209882623    | 22.2               | 22.2               | 27.600000381469727 |
+------------+--------------------+--------------------+-----------------------+--------------------+--------------------+--------------------+
```

## **Time Bucket Feature**

The time bucket feature allows the user to specify the a particular time bucket based on which the data can be grouped together to calcuate the said statistical metrics. The time bucket can be given in the following format: d representing days,m representing minutes and s representing seconds.

```bash
influxdb3 create trigger \
  --database <database-name> \
  --trigger-spec 'table:<table-name>' \
  --trigger-arguments 'table_name:<table-name>,time_sampling:time 10d' \
  --plugin-filename <path-to-file>/stats_metrics.py stats_metrics_trigger
```

```bash
+--------------+---------+-------------+--------------+-----------------------+--------------------+--------------+-----------+-------------------------------+---------------------+
| 95Percentile | count   | field_name  | max          | mean                  | median             | min          | mode      | time                          | time_bucket         |
+--------------+---------+-------------+--------------+-----------------------+--------------------+--------------+-----------+-------------------------------+---------------------+
| 931.9571429  | 1708.0  | ac_power    | 1201.442857  | 322.50056171106166    | 200.9875           | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-06T00:00:00 |
| 1149.6375    | 19240.0 | ac_power    | 1394.285714  | 325.6492097438818     | 43.357142859999996 | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-16T00:00:00 |
| 1118.157143  | 20158.0 | ac_power    | 1405.3       | 318.287862895283      | 60.3125            | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-26T00:00:00 |
| 1084.6375    | 21028.0 | ac_power    | 1410.95      | 298.6168499481945     | 29.986607145       | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-05T00:00:00 |
| 930.9857143  | 6644.0  | ac_power    | 1352.271429  | 249.6047681350431     | 0.0                | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-15T00:00:00 |
| 6345.142857  | 1708.0  | daily_yield | 6471.0       | 2293.074926817813     | 1159.625           | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-06T00:00:00 |
| 8544.0       | 19240.0 | daily_yield | 9163.0       | 3487.325753554537     | 2922.2589285       | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-16T00:00:00 |
| 8125.857143  | 20158.0 | daily_yield | 9163.0       | 3205.855616641442     | 2319.0535715       | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-26T00:00:00 |
| 8288.75      | 21028.0 | daily_yield | 8774.0       | 3271.6562765510353    | 2560.5             | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-05T00:00:00 |
| 6916.0       | 6644.0  | daily_yield | 7590.0       | 3349.9988905744954    | 3828.5089285       | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-15T00:00:00 |
| 9541.285714  | 1708.0  | dc_power    | 12319.14286  | 3294.636500510388     | 2050.205357        | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-06T00:00:00 |
| 11786.14286  | 19240.0 | dc_power    | 14300.28571  | 3330.722975938894     | 448.2857143        | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-16T00:00:00 |
| 11454.42857  | 20158.0 | dc_power    | 14413.42857  | 3254.8462371687065    | 622.91964285       | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-26T00:00:00 |
| 11109.42857  | 21028.0 | dc_power    | 14471.125    | 3053.3728034474943    | 310.5357143        | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-05T00:00:00 |
| 9527.25      | 6644.0  | dc_power    | 13869.57143  | 2550.5444003746293    | 0.0                | 0.0          | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-15T00:00:00 |
| 4135001.0    | 1708.0  | plant_id    | 4135001.0    | 4135001.0             | 4135001.0          | 4135001.0    | 4135001.0 | 2025-02-27T14:44:40.758843047 | 2020-05-06T00:00:00 |
| 4135001.0    | 19240.0 | plant_id    | 4135001.0    | 4135001.0             | 4135001.0          | 4135001.0    | 4135001.0 | 2025-02-27T14:44:40.758843047 | 2020-05-16T00:00:00 |
| 4135001.0    | 20158.0 | plant_id    | 4135001.0    | 4135001.0             | 4135001.0          | 4135001.0    | 4135001.0 | 2025-02-27T14:44:40.758843047 | 2020-05-26T00:00:00 |
| 4135001.0    | 21028.0 | plant_id    | 4135001.0    | 4135001.0             | 4135001.0          | 4135001.0    | 4135001.0 | 2025-02-27T14:44:40.758843047 | 2020-06-05T00:00:00 |
| 4135001.0    | 6644.0  | plant_id    | 4135001.0    | 4135001.0             | 4135001.0          | 4135001.0    | 4135001.0 | 2025-02-27T14:44:40.758843047 | 2020-06-15T00:00:00 |
 2020-06-15T00:00:00 |
| 7212369.5    | 1708.0  | total_yield | 7609076.0    | 6853217.735426814     | 7023181.5715       | 6183645.0    | 7206408.0 | 2025-02-27T14:44:40.758843047 | 2020-05-06T00:00:00 |
| 7280512.0    | 19240.0 | total_yield | 7684020.0    | 6894069.900671478     | 7064201.0          | 6190002.0    | 6555136.0 | 2025-02-27T14:44:40.758843047 | 2020-05-16T00:00:00 |
| 7355661.0    | 20158.0 | total_yield | 7756621.0    | 6968278.873558895     | 7140899.0          | 6264579.0    | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-05-26T00:00:00 |
| 7429566.0    | 21028.0 | total_yield | 7828158.0    | 7041907.29143604      | 7213001.0          | 6337019.0    | 0.0       | 2025-02-27T14:44:40.758843047 | 2020-06-05T00:00:00 |
| 7455935.0    | 6644.0  | total_yield | 7846821.0    | 7087724.960398853     | 7256784.4465       | 6407683.0    | 7281035.0 | 2025-02-27T14:44:40.758843047 | 2020-06-15T00:00:00 |
+--------------+---------+-------------+--------------+-----------------------+--------------------+--------------+-----------+-------------------------------+---------------------+
```

## API endpoint through Redis and FastAPI

This feature exposes analytics data saved in a Redis cache through a FastAPI endpoint.

### **1. Set Up Redis Service**

First, Redis is used as an in-memory data store to cache the analytics data. In this setup, Redis runs in a Docker container, and the data is stored under a key format `database:table_name`.

### Steps to run Redis in Docker

1. **Pull and run the Redis Docker image** (if you haven't already):

 ```bash
 docker run -d --name redis_container -p 6380:6379 redis
 ```

2. **Setup FastAPI endpoint:** FastAPI is used to create a REST API endpoint that fetches the cached analytics data from Redis and exposes it to users. Make sure to install the same using the **influxdb3 install package** command

  ```bash
  influxdb3 install package fastapi
  influxdb3 install package uvicorn
  ```

3. **Build and run the docker-compose file**:

    ```bash
    docker-compose up --build
    ```

   FastAPI and Redis start on ports 8001 and 6379, respectively.

4. **Create a trigger to run the plugin in InfluxDB**:

   ```bash
   influxdb3 create trigger \
     -database <database-name> \
     -trigger-spec 'table:<table-name>' \
     --trigger-arguments 'table_name:<table-name>,database_name:<database_name>' \
     --plugin-filename <path-to-file>/stats_metrics.py stats_metrics_trigger
   ```

#### Test the endpoint

1. Ingest data into a table with the plugin enabled
2. Use cURL to check the FastAPI endpoint:

   ```bash
   curl -X 'GET' \
    'http://localhost:8001/analytics/{table_name}?database={database_name}' \
    --header 'accept: application/json'
   ```
