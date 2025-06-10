"""
{
    "plugin_name": "influxdb_to_iceberg",
    "plugin_type": "Scheduled",
    "dependencies": ["pandas", "pyarrow", "pyiceberg"],
    "required_plugins": [],
    "category": "Data Transfer",
    "description": "This plugin transfers data from InfluxDB 3 to Apache Iceberg tables. It periodically queries specified measurement within a time window, transforming the data, and appending it to an Iceberg table.",
    "docs_file_link": "https://github.com/InfluxData/influxdb3-python/blob/main/plugins/influxdb_to_iceberg/README.md",
    "args_config": [
        {
            "name": "measurement",
            "example": "cpu",
            "description": "The InfluxDB measurement to query.",
            "required": true
        },
        {
            "name": "window",
            "example": "1h",
            "description": "Time window for data analysis (e.g., '1h' for 1 hour). Supported units: s, min, h, d, w.",
            "required": true
        },
        {
            "name": "catalog_configs",
            "example": "eyJ1cmkiOiAiaHR0cDovL25lc3NpZTo5MDAwIn0=",
            "description": "Base64-encoded JSON string containing Iceberg catalog configuration (e.g., URI, credentials).",
            "required": true
        },
        {
            "name": "included_fields",
            "example": "usage_user.usage_idle",
            "description": "Dot-separated list of field names to include in the query.",
            "required": false
        },
        {
            "name": "excluded_fields",
            "example": "usage_system.usage_idle",
            "description": "Dot-separated list of field names to exclude from the query.",
            "required": false
        },
        {
            "name": "namespace",
            "example": "monitoring",
            "description": "Iceberg namespace for the table (default: 'default').",
            "required": false
        },
        {
            "name": "table_name",
            "example": "metrics",
            "description": "Iceberg table name (default: same as measurement).",
            "required": false
        }
    ]
}
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.types import (
    BooleanType,
    FloatType,
    IntegerType,
    NestedField,
    PrimitiveType,
    StringType,
    TimestampType,
)


def get_all_measurements(influxdb3_local) -> list[str]:
    """
    Retrieves a list of all tables of type 'BASE TABLE' from the current InfluxDB database.

    Args:
        influxdb3_local: InfluxDB client instance.

    Returns:
        list[str]: List of table names (e.g., ["cpu", "memory", "disk"]).
    """
    result: list = influxdb3_local.query("SHOW TABLES")
    return [
        row["table_name"] for row in result if row.get("table_type") == "BASE TABLE"
    ]


def parse_time_duration(raw: str, task_id: str) -> timedelta:
    """
    Convert a duration string (e.g., "5m", "2h", "1d") into a timedelta.

    Args:
        raw (str): Duration with unit suffix. Supported suffixes: s, min, h, d, w.
        task_id (str): Unique task identifier (for error messages).

    Returns:
        timedelta.

    Raises:
        Exception: if format is invalid or number conversion fails.
    """
    units: dict = {
        "s": "seconds",
        "min": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }
    num_part, unit_part = "", ""
    for u in sorted(units.keys(), key=len, reverse=True):
        if raw.endswith(u):
            num_part = raw[: -len(u)]
            unit_part = u
            break
    if not num_part or unit_part not in units:
        raise Exception(f"[{task_id}] Invalid duration '{raw}'")
    try:
        val: int = int(num_part)
    except ValueError:
        raise Exception(f"[{task_id}] Invalid number in duration '{raw}'")
    return timedelta(**{units[unit_part]: val})


def parse_fields(args: dict, key: str) -> list[str]:
    """Splits a dot-separated string into a list of strings."""
    string_input: str | None = args.get(key, None)
    if not string_input:
        return []
    return string_input.split(".")


def parse_catalog_configs(args: dict, task_id: str) -> dict:
    """Decode and parse a base64-encoded JSON string."""
    base64_params: str = args["catalog_configs"]
    try:
        # Decode base64-encoded string
        decoded_bytes: bytes = base64.b64decode(base64_params)
        decoded_str: str = decoded_bytes.decode("utf-8")
    except Exception:
        raise Exception(
            f"[{task_id}] Invalid base64 encoding in catalog_configs: {base64_params}"
        )

    try:
        # Parse JSON from decoded string
        params: dict = json.loads(decoded_str)
    except json.JSONDecodeError:
        raise Exception(
            f"[{task_id}] Invalid JSON in decoded catalog_configs: {decoded_str}"
        )

    return params


def get_tag_names(influxdb3_local, measurement: str, task_id: str) -> list[str]:
    """
    Retrieves the list of tag names for a measurement.

    Args:
        influxdb3_local: InfluxDB client instance.
        measurement (str): Name of the measurement to query.
        task_id (str): Unique task identifier.

    Returns:
        list[str]: List of tag names with 'Dictionary(Int32, Utf8)' data type.
    """
    query: str = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = $measurement
        AND data_type = 'Dictionary(Int32, Utf8)'
    """
    res: list[dict] = influxdb3_local.query(query, {"measurement": measurement})

    if not res:
        influxdb3_local.info(
            f"[{task_id}] No tags found for measurement '{measurement}'."
        )
        return []

    tag_names: list[str] = [tag["column_name"] for tag in res]
    return tag_names


def get_fields_names(influxdb3_local, measurement: str, task_id: str) -> list[str]:
    """
    Retrieves the list of field names for a measurement.

    Args:
        influxdb3_local: InfluxDB client instance.
        measurement (str): Name of the measurement to query.
        task_id (str): Unique task identifier.

    Returns:
        list[str]: List of field names.
    """
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = $measurement
        AND data_type != 'Dictionary(Int32, Utf8)'
    """
    res: list[dict] = influxdb3_local.query(query, {"measurement": measurement})

    if not res:
        influxdb3_local.info(
            f"[{task_id}] No fields found for measurement '{measurement}'."
        )
        return []

    field_names: list[str] = [field["column_name"] for field in res]
    return field_names


def generate_fields_string(tags: list[str], fields: list[str]) -> str:
    """
    Generates a formatted SELECT clause with tags and fields.

    Args:
        tags (list[str]): List of tag names.
        fields (list[str]): List of field names.

    Returns:
        str: Formatted string with quoted field names separated by commas and newlines.
    """
    all_fields: list = tags + fields
    return ",\n\t".join(f'"{field}"' for field in all_fields)


def generate_query(
    measurement: str,
    tag_names: list[str],
    field_names: list[str],
    start_time: datetime,
    end_time: datetime,
) -> str:
    """
    Builds an SQL query.

    Args:
        measurement: source measurement name
        tag_names: list of tags
        field_names: list of field names
        start_time: UTC datetime for WHERE time > ...
        end_time:   UTC datetime for WHERE time < ...

    Returns:
        A complete SQL query string.
    """
    # SELECT clause
    fields_clause: str = generate_fields_string(tag_names, field_names)

    query: str = f"""
            SELECT
                {fields_clause}
            FROM
                '{measurement}'
            WHERE
                time >= '{start_time}'
            AND 
                time < '{end_time}'
        """
    return query


def pandas_dtype_to_iceberg_type(dtype) -> PrimitiveType:
    """Converts a Pandas dtype to an Iceberg type."""
    if pd.api.types.is_integer_dtype(dtype):
        return IntegerType()
    elif pd.api.types.is_float_dtype(dtype):
        return FloatType()
    elif pd.api.types.is_bool_dtype(dtype):
        return BooleanType()
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return TimestampType()
    elif pd.api.types.is_string_dtype(dtype):
        return StringType()
    else:
        raise TypeError(f"Unsupported dtype: {dtype}")


def df_to_iceberg_schema(df: pd.DataFrame) -> Schema:
    """Generates an Iceberg schema from a Pandas DataFrame."""
    fields: list = []
    for idx, (col_name, dtype) in enumerate(df.dtypes.items(), start=1):
        iceberg_type = pandas_dtype_to_iceberg_type(dtype)
        required: bool = not df[col_name].isnull().any()
        field: NestedField = NestedField(
            field_id=idx, name=col_name, field_type=iceberg_type, required=required
        )
        fields.append(field)
    return Schema(*fields)


def process_scheduled_call(
    influxdb3_local, call_time: datetime, args: dict | None = None
):
    """
    Main scheduled task for querying InfluxDB and appending data into an Iceberg table.

    Args:
        influxdb3_local: InfluxDB client instance.
        call_time (datetime): the timestamp when this task is run.
        args (dict): parameters for this call:
            - "measurement": str, InfluxDB measurement name (required).
            - "window": str, time window (e.g., "5m", "1h") (required).
            - "catalog_configs": str, base64-encoded JSON for load_catalog (required).
            - "included_fields": str, dot-separated field names to include (optional).
            - "excluded_fields": str, dot-separated field names to exclude (optional).
            - "namespace": str, Iceberg namespace (optional; default "default").
            - "table_name": str, Iceberg table name (optional; default = measurement).

    Returns:
        None. All outcomes and errors are logged via influxdb3_local.

    Notes:
      - If the Iceberg table does not exist, it is created with a schema inferred from the DataFrame.
      - If the table exists but schema differs, append may fail; handling schema evolution is not implemented here.
      - Each append writes a new file in Iceberg (normal behavior).
    """
    task_id = str(uuid.uuid4())

    # Validate required arguments
    required_keys: list = ["measurement", "window", "catalog_configs"]
    if not args or any(key not in args for key in required_keys):
        influxdb3_local.error(
            f"[{task_id}] Missing some of the required arguments: {', '.join(required_keys)}"
        )
        return

    measurement: str = args["measurement"]
    all_measurements: list = get_all_measurements(influxdb3_local)
    if measurement not in all_measurements:
        influxdb3_local.error(
            f"[{task_id}] Measurement '{measurement}' not found in database"
        )
        return

    try:
        # Parse config
        window: timedelta = parse_time_duration(args["window"], task_id)
        catalog_configs: dict = parse_catalog_configs(args, task_id)
        included_fields: list = parse_fields(args, "included_fields")
        excluded_fields: list = parse_fields(args, "excluded_fields")
        namespace: str = args.get("namespace", "default")
        table_name: str = args.get("table_name", measurement)
        full_table_name: str = f"{namespace}.{table_name}"

        # Determine time window
        end_time: datetime = call_time.replace(tzinfo=timezone.utc)
        start_time: datetime = end_time - window

        # Get data
        tags: list = get_tag_names(influxdb3_local, measurement, task_id)
        fields: list = get_fields_names(influxdb3_local, measurement, task_id)

        # Recognize fields to query
        if included_fields:
            fields_to_query: list = [
                field for field in fields if field in included_fields or field == "time"
            ]
        elif excluded_fields:
            fields_to_query = [
                field for field in fields if field not in excluded_fields
            ]
        else:
            fields_to_query = fields

        query: str = generate_query(
            measurement, tags, fields_to_query, start_time, end_time
        )
        results: list = influxdb3_local.query(query)
        if not results:
            influxdb3_local.info(
                f"[{task_id}] No data returned from {start_time} to {end_time}"
            )
            return

        # Convert to DataFrame and convert 'time' to datetime
        df: pd.DataFrame = pd.DataFrame.from_records(results)
        try:
            df["time"] = pd.to_datetime(
                df["time"]
            )  # Assuming 'time' column exists and is the timestamp
            influxdb3_local.info(
                f"[{task_id}] Successfully converted 'time' column to datetime."
            )
        except Exception as e:
            influxdb3_local.error(
                f"[{task_id}] Error while converting 'time' to datetime: {e}"
            )
            return
        df["time"] = df["time"].astype(
            "datetime64[us]"
        )  # Ensure time is microsecond datetime for Iceberg

        # Load catalog
        try:
            catalog = load_catalog("iceberg", **catalog_configs)
            influxdb3_local.info(f"[{task_id}] Catalog loaded successfully.")
        except Exception as e:
            influxdb3_local.error(f"[{task_id}] Error while loading catalog: {e}")
            return

        # Create the namespace if it doesn't exist
        catalog.create_namespace_if_not_exists(namespace)

        # Create the table if it doesn't exist
        if not catalog.table_exists(full_table_name):
            schema: Schema = df_to_iceberg_schema(df)
            catalog.create_table(full_table_name, schema)
            influxdb3_local.info(f"[{task_id}] Table created successfully.")

        table: Table = catalog.load_table(full_table_name)
        pa_schema: pa.Schema = table.schema().as_arrow()
        result_arrows: pa.Table = pa.Table.from_pandas(df, schema=pa_schema)
        table.append(result_arrows)
        influxdb3_local.info(
            f"[{task_id}] Data appended to table successfully ({len(result_arrows)} rows)."
        )

    except Exception as e:
        influxdb3_local.error(f"Error: {e}")
        return
