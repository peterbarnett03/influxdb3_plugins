import json
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone


def parse_time_interval(
    influxdb3_local, args: dict, key: str, task_id: str
) -> tuple[int, str]:
    """
    Parses the interval string into a tuple of magnitude and unit for downsampling.

    Supports time units: seconds (s), minutes (min), hours (h), days (d), weeks (w),
    months (m), quarters (q), and years (y). Months, quarters, and years are converted
    to days using approximate values: 1 month ≈ 30.42 days, 1 quarter ≈ 91.25 days,
    1 year = 365 days.

    Args:
        influxdb3_local: InfluxDB client instance for querying the database.
        args (dict): Dictionary containing configuration parameters, including the 'interval' key
            with a string in the format '<number><unit>' (e.g., '10min', '2m', '1y').
        key (str): The key used to access the 'key' parameter in the 'args' dictionary.
        task_id (str): The task ID.

    Returns:
        tuple[int, str]: A tuple containing the magnitude (integer) and the unit (e.g., 'minutes' or 'days').
            For months, quarters, and years, the magnitude is the equivalent number of days, and the unit is 'days'.

    Raises:
        Exception: If the interval format is invalid, the unit is not supported, or the magnitude is less than 1.

    Example:
        >>> parse_time_interval(influxdb3_local, {'interval': '10min'}, 'interval', 'task_id')
        (10, 'minutes')
        >>> parse_time_interval(influxdb3_local, {'interval': '2m'}, 'interval', 'task_id')
        (60, 'days')  # 2 months ≈ 60.84 days, rounded to 60
        >>> parse_time_interval(influxdb3_local, {'interval': '1y'}, 'interval', 'task_id')
        (365, 'days')
    """
    unit_mapping = {
        "s": "seconds",
        "min": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
        "m": "days",  # Months converted to days
        "q": "days",  # Quarters converted to days
        "y": "days",  # Years converted to days
    }

    # Conversion factors to days for month, quarter, and year
    day_conversions = {
        "m": 30.42,  # Average days in a month (365 ÷ 12)
        "q": 91.25,  # Average days in a quarter (365 ÷ 4)
        "y": 365.0,  # Days in a year (non-leap)
    }

    valid_units = unit_mapping.keys()

    if key == "interval":
        interval: str = args.get(key, "10min")
    else:
        interval: str = args.get(key, "30d")

    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", interval)
    if match:
        number_part, unit = match.groups()
        magnitude = int(number_part)
        if unit in valid_units and magnitude >= 1:
            if unit in day_conversions:
                # Convert months, quarters, or years to days
                days = int(magnitude * day_conversions[unit])
                return days, "days"
            return magnitude, unit_mapping[unit]

    influxdb3_local.error(f"[{task_id}] Invalid {key} format: {interval}.")
    raise Exception(f"[{task_id}] Invalid {key} format: {interval}.")


def get_aggregatable_fields(
    influxdb3_local, measurement: str, task_id: str
) -> list[str]:
    """
    Retrieves the list of fields in a measurement that can be aggregated (numeric types).

    Args:
        influxdb3_local: InfluxDB client instance for querying the database.
        measurement (str): Name of the measurement to query.
        task_id (str): The task ID.

    Returns:
        list[str]: List of field names with 'Int64', 'Float64', or 'UInt64' data types.

    Raises:
        Exception: If no aggregatable fields are found for the measurement.
    """
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = $measurement
        AND data_type IN ('Int64', 'Float64', 'UInt64')
    """

    fields: list[dict] = influxdb3_local.query(query, {"measurement": measurement})

    if not fields:
        influxdb3_local.error(
            f"[{task_id}] No aggregatable fields found for measurement '{measurement}'."
        )
        raise Exception(
            f"[{task_id}] No aggregatable fields found for measurement '{measurement}'."
        )

    field_names: list[str] = [field["column_name"] for field in fields]

    return field_names


def parse_fields_for_http(
    influxdb3_local, measurement: str, key: str, args: dict, task_id: str
) -> list[str]:
    """
    Parses fields for HTTP-based downsampling.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Dictionary containing the 'key' key with a list of field names.
        measurement (str): Name of the measurement.
        key (str): The key used to access the 'key' parameter in the 'args' dictionary.
        task_id (str): The task ID.

    Returns:
        list[str]: List of valid field names to exclude from downsampling.
    """
    fields: list | None = args.get(key, None)
    result_fields: list = []
    if fields is not None:
        measurement_fields: list = get_aggregatable_fields(
            influxdb3_local, measurement, task_id
        )
        for field in fields:
            if field not in measurement_fields:
                influxdb3_local.info(
                    f"[{task_id}] Field '{field}' is not available for downsampling '{measurement}'."
                )
            else:
                result_fields.append(field)
    return result_fields


def get_tag_names(influxdb3_local, measurement: str, task_id: str) -> list[str]:
    """
    Retrieves the list of tag names for a measurement.

    Args:
        influxdb3_local: InfluxDB client instance.
        measurement (str): Name of the measurement to query.
        task_id (str): The task ID.

    Returns:
        list[str]: List of tag names with 'Dictionary(Int32, Utf8)' data type.
    """
    query = """
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


def parse_tag_values_for_scheduler(
    influxdb3_local, args: dict, source_measurement: str, task_id: str
) -> dict[str, list[str]] | None:
    """
    Parses tag values for scheduler-based downsampling requests.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Dictionary containing the 'tag_values' key with a dot-separated string
            of tag-value pairs (e.g., 'room:Kitchen-Bedroom-"Some other room"' ).
        source_measurement (str): Name of the source measurement.
        task_id (str): The task ID.

    Returns:
        dict[str, list[str]] | None: Dictionary mapping tag names to lists of values, or None if no tag values provided.

    Raises:
        Exception: If the 'tag_values' format is invalid (must match '^([^:.]+\:[^:.]+(?:\-[^:.]+)*)(\.[^:.]+\:[^:.]+(?:\-[^:.]+)*)*$').
    """
    tag_values: str | None = args.get("tag_values", None)
    pattern: str = r"^([^:.]+\:[^:.]+(?:\-[^:.]+)*)(\.[^:.]+\:[^:.]+(?:\-[^:.]+)*)*$"

    if tag_values is not None:
        if not re.match(pattern, tag_values):
            influxdb3_local.error(
                f"[{task_id}] Invalid tag_values format: {tag_values}."
            )
            raise Exception(f"[{task_id}] Invalid tag_values format: {tag_values}.")

        result: dict = {}
        tag_names: list = get_tag_names(influxdb3_local, source_measurement, task_id)

        pairs: list = tag_values.split(".")
        for pair in pairs:
            tag_name, value = pair.split(":")
            if tag_name in tag_names:
                values: list = value.split("-")
                if tag_name in result:
                    result[tag_name] += values
                else:
                    result[tag_name] = values
            else:
                influxdb3_local.warn(
                    f"[{task_id}] Tag '{tag_name}' does not exist in '{source_measurement}'."
                )

        return result
    return None


def parse_tag_values_for_http(
    influxdb3_local, data: dict, source_measurement: str, task_id: str
) -> dict[str, list[str]] | None:
    """
    Parses tag values for HTTP-based downsampling requests.

    Args:
        influxdb3_local: InfluxDB client instance.
        data (dict): Dictionary containing the 'tag_values' key with a dictionary mapping tag names to lists of values.
        source_measurement (str): Name of the source measurement.
        task_id (str): The task ID.

    Returns:
        dict[str, list[str]] | None: Dictionary mapping tag names to lists of values, or None if no tag values provided.
    """
    tag_value_filters: dict[str, list[str]] | None = data.get("tag_values", None)

    if tag_value_filters is not None:
        tag_names: list = get_tag_names(influxdb3_local, source_measurement, task_id)
        for tag_name in list(tag_value_filters.keys()):
            if tag_name not in tag_names:
                influxdb3_local.warn(
                    f"[{task_id}] Tag '{tag_name}' does not exist in '{source_measurement}'."
                )
                del tag_value_filters[tag_name]
        return tag_value_filters
    return None


def parse_field_aggregations_for_scheduler(
    influxdb3_local, args: dict, task_id: str
) -> list[tuple[str, str]]:
    """
    Parses field aggregations for scheduler-based downsampling.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Dictionary containing 'source_measurement' and 'calculations' keys.
            'calculations' can be a single aggregation (e.g., 'avg') or a dot-separated string of field:aggregation pairs.
        task_id (str): The task ID.

    Returns:
        list[tuple[str, str]]: List of tuples containing field names and their aggregation functions (e.g., [('co', 'avg')]).

    Raises:
        Exception: If no aggregatable fields are found, or if the aggregation format or type is invalid.
    """
    available_calculations: list = ["avg", "sum", "min", "max", "derivative", "median"]
    pattern: str = r"^([^:.]+:[^:.]+)(\.[^:.]+:[^:.]+)*$"
    measurement: str = args["source_measurement"]
    excluded_fields: list = parse_fields_for_scheduler(
        influxdb3_local, measurement, "excluded_fields", args, task_id
    )
    calculations_input: str = args.get("calculations", "avg")
    specific_fields: list = parse_fields_for_scheduler(
        influxdb3_local, measurement, "specific_fields", args, task_id
    )
    all_fields: list = get_aggregatable_fields(influxdb3_local, measurement, task_id)

    if specific_fields:
        fields_to_use = []
        for field in specific_fields:
            if field in all_fields:
                fields_to_use.append(field)
            else:
                influxdb3_local.info(
                    f"[{task_id}] Field '{field}' is not available for aggregation in measurement '{measurement}'."
                )
    else:
        fields_to_use = all_fields

    result: list = []
    if not re.match(pattern, calculations_input):
        if calculations_input not in available_calculations:
            influxdb3_local.error(
                f"[{task_id}] Aggregation '{calculations_input}' is not available."
            )
            raise Exception(
                f"[{task_id}] Aggregation '{calculations_input}' is not available."
            )

        result = [
            (field, calculations_input)
            for field in fields_to_use
            if field not in excluded_fields
        ]
    else:
        calculations: list = calculations_input.split(".")
        for calc in calculations:
            field_name, calculation = calc.split(":")
            if calculation not in available_calculations:
                influxdb3_local.error(
                    f"[{task_id}] Aggregation '{calculations_input}' is not available."
                )
                raise Exception(
                    f"[{task_id}] Aggregation '{calculations_input}' is not available."
                )
            if field_name in fields_to_use and field_name not in excluded_fields:
                result.append((field_name, calculation))
            else:
                influxdb3_local.info(
                    f"[{task_id}] Field '{field_name}' is not available or excluded."
                )

    if not result:
        influxdb3_local.error(
            f"[{task_id}] No aggregatable fields found for measurement."
        )
        raise Exception(f"[{task_id}] No aggregatable fields found for measurement.")
    return result


def parse_field_aggregations_for_http(
    influxdb3_local, data: dict, task_id: str
) -> list[tuple[str, str]]:
    """
    Parses field aggregations for HTTP-based downsampling.

    Args:
        influxdb3_local: InfluxDB client instance.
        data (dict): Dictionary containing 'source_measurement' and 'calculations' keys.
            'calculations' can be 'avg' or a list of tuples with 'field' and 'aggregation' (e.g., [('co', 'avg')]).
        task_id (str): The task ID.

    Returns:
        list[tuple[str, str]]: List of tuples containing field names and their aggregation functions.

    Raises:
        Exception: If no aggregatable fields are found, or if the aggregation format or type is invalid.
    """
    measurement: str = data["source_measurement"]
    calculations_input: list[tuple[str, str]] | str = data.get("calculations", "avg")
    excluded_fields: list = parse_fields_for_http(
        influxdb3_local, measurement, "excluded_fields", data, task_id
    )
    specific_fields: list = parse_fields_for_http(
        influxdb3_local, measurement, "specific_fields", data, task_id
    )
    all_fields: list = get_aggregatable_fields(influxdb3_local, measurement, task_id)
    available_calculations: list = ["avg", "sum", "min", "max", "derivative", "median"]

    if specific_fields:
        fields_to_use = []
        for field in specific_fields:
            if field in all_fields and field not in excluded_fields:
                fields_to_use.append(field)
            else:
                influxdb3_local.info(
                    f"[{task_id}] Field '{field}' is not available for aggregation in measurement '{measurement}' or excluded."
                )
    else:
        fields_to_use = [field for field in all_fields if field not in excluded_fields]

    result = []

    if calculations_input == "avg":
        result = [(field, calculations_input) for field in fields_to_use]
    else:
        if not isinstance(calculations_input, list):
            influxdb3_local.error(
                f"[{task_id}] Invalid calculations format: {calculations_input}."
            )
            raise Exception(
                f"[{task_id}] Invalid calculations format: {calculations_input}."
            )
        for filed, calc in calculations_input:
            if calc not in available_calculations:
                influxdb3_local.error(
                    f"[{task_id}] Aggregation '{calc}' is not available."
                )
                raise Exception(f"[{task_id}] Aggregation '{calc}' is not available.")
            if filed in fields_to_use:
                result.append((filed, calc))
            else:
                influxdb3_local.info(
                    f"[{task_id}] Field '{filed}' is not available or excluded."
                )

    if not result:
        influxdb3_local.error(
            f"[{task_id}] No aggregatable fields available for downsampling '{measurement}'."
        )
        raise Exception(
            f"[{task_id}] No aggregatable fields available for downsampling '{measurement}'."
        )
    return result


def parse_fields_for_scheduler(
    influxdb3_local, measurement: str, key: str, args: dict, task_id: str
) -> list[str]:
    """
    Parses fields for downsampling in scheduler-based requests.

    Args:
        influxdb3_local: InfluxDB client instance.
        measurement (str): Name of the measurement.
        args (dict): Dictionary containing the 'key' key with a dot-separated
            string of field names (e.g., 'co.temperature').
        key (str): The key used to access the 'key' parameter in the 'args' dictionary.
        task_id (str): The task ID.

    Returns:
        list[str]: List of valid field names that exist in the measurement.

    Raises:
        Exception: If the 'key' format is invalid.
    """
    fields: str | None = args.get(key, None)
    # Field names must start with letter or digit, may contain letters, digits, dashes or underscores,
    # and are separated by dots.
    pattern = r"^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9][A-Za-z0-9_-]*)*$"

    if fields is None:
        return []

    if not re.fullmatch(pattern, fields):
        influxdb3_local.error(
            f"[{task_id}] Invalid specific_fields format: {fields!r}."
        )
        raise Exception(f"[{task_id}] Invalid specific_fields format: {fields!r}.")

    requested = fields.split(".")
    measurement_fields = get_aggregatable_fields(influxdb3_local, measurement, task_id)
    valid = []

    for field in requested:
        if field not in measurement_fields:
            influxdb3_local.info(
                f"[{task_id}] Field '{field}' is not available for downsampling '{measurement}'."
            )
        else:
            valid.append(field)

    return valid


def parse_max_retries(args: dict) -> int:
    """
    Parses the maximum number of retries for write operations.

    Args:
        args (dict): Dictionary containing the 'max_retries' key with an integer value.

    Returns:
        int: Maximum number of retries (defaults to 5 if not provided).
    """
    max_retries = args.get("max_retries", 5)
    return int(max_retries)


def get_all_tables(influxdb3_local) -> list[str]:
    """
    Retrieves the list of all base tables in the database.

    Args:
        influxdb3_local: InfluxDB client instance.

    Returns:
        list[str]: List of table names with type 'BASE TABLE'.
    """
    result: list = influxdb3_local.query("SHOW TABLES")
    return [
        row["table_name"] for row in result if row.get("table_type") == "BASE TABLE"
    ]


def parse_source_and_target_measurement(
    influxdb3_local, args: dict, task_id: str
) -> tuple[str, str]:
    """
    Parses source and target measurement names for downsampling.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Dictionary containing 'source_measurement' and 'target_measurement' keys.
        task_id (str): The task ID.

    Returns:
        tuple[str, str]: Tuple of source and target measurement names.

    Raises:
        Exception: If 'source_measurement' or 'target_measurement' is missing or if the source measurement does not exist.
    """
    source_measurement: str | None = args.get("source_measurement", None)
    target_measurement: str | None = args.get("target_measurement", None)

    if source_measurement is None:
        influxdb3_local.error(f"[{task_id}] Missing source_measurement parameter.")
        raise Exception(f"[{task_id}] Missing source_measurement parameter.")
    if target_measurement is None:
        influxdb3_local.error(f"[{task_id}] Missing target_measurement parameter.")
        raise Exception(f"[{task_id}] Missing target_measurement parameter.")

    all_tables: list = get_all_tables(influxdb3_local)

    if source_measurement not in all_tables:
        influxdb3_local.error(
            f"[{task_id}] Source_measurement {source_measurement} does not exist in database."
        )
        raise Exception(
            f"[{task_id}] Source_measurement {source_measurement} does not exist in database."
        )

    return source_measurement, target_measurement


def parse_offset(influxdb3_local, args: dict, task_id: str) -> timedelta:
    """
    Parses the offset string into a timedelta for scheduler-based downsampling.

    Args:
        influxdb3_local: InfluxDB client instance for querying the database.
        args (dict): Dictionary containing the 'offset' key with a string in the format '<number><unit>' (e.g., '1h').
        task_id (str): The task ID.

    Returns:
        timedelta: Time delta representing the offset (defaults to 0 if not provided).

    Raises:
        Exception: If the offset format is invalid or the unit is not supported ('min', 'h', 'd', 'w').
    """
    valid_units = {"min": "minutes", "h": "hours", "d": "days", "w": "weeks"}

    offset: str | None = args.get("offset", None)

    if offset is None:
        return timedelta(0)

    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", offset)
    if match:
        number, unit = match.groups()
        number = int(number)

        if number >= 1 and unit in valid_units:
            return timedelta(**{valid_units[unit]: number})

    influxdb3_local.error(f"[{task_id}] Invalid interval format: {offset}.")
    raise Exception(f"[{task_id}] Invalid interval format: {offset}.")


def parse_window(influxdb3_local, args: dict, task_id: str) -> timedelta:
    """
    Parses the window string into a timedelta for scheduler-based downsampling.

    Args:
        influxdb3_local: InfluxDB client instance for querying the database.
        args (dict): Dictionary containing the 'window' key with a string in the format '<number><unit>' (e.g., '1h').
        task_id (str): The task ID.

    Returns:
        timedelta: Time delta representing the window.

    Raises:
        Exception: If the window parameter is missing or the format is invalid.
    """
    valid_units = {
        "s": "seconds",
        "min": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }

    window: str | None = args.get("window", None)

    if window is None:
        influxdb3_local.error(f"[{task_id}] Missing window parameter.")
        raise Exception(f"[{task_id}] Missing window parameter.")

    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", window)

    if match:
        number, unit = match.groups()
        number = int(number)

        if number >= 1 and unit in valid_units:
            return timedelta(**{valid_units[unit]: number})

    influxdb3_local.error(f"[{task_id}] Invalid interval format: {window}.")
    raise Exception(f"[{task_id}] Invalid interval format: {window}.")


def parse_backfill_window(
    influxdb3_local, args: dict, task_id: str
) -> tuple[datetime | None, datetime]:
    """
    Parses the backfill window for HTTP-based downsampling. Requires timezone-aware datetime strings
    in ISO 8601 format (e.g., '2025-05-01T00:00:00+03:00').

    Args:
        influxdb3_local: InfluxDB client instance for querying the database.
        args (dict): Dictionary containing 'backfill_start' and 'backfill_end' keys.
        task_id (str): The task ID.

    Returns:
        tuple[datetime | None, datetime]: Tuple of start and end datetimes in UTC.

    Raises:
        Exception: If the datetime format is invalid, lacks timezone info, or if start ≥ end.
    """

    def parse_iso_datetime(name: str, value: str) -> datetime:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            influxdb3_local.error(
                f"[{task_id}] Invalid ISO 8601 datetime for {name}: '{value}'."
            )
            raise Exception(
                f"[{task_id}] Invalid ISO 8601 datetime for {name}: '{value}'."
            )
        if dt.tzinfo is None:
            influxdb3_local.error(
                f"[{task_id}] {name} must include timezone info (e.g., '+00:00')."
            )
            raise Exception(
                f"[{task_id}] {name} must include timezone info (e.g., '+00:00')."
            )
        return dt.astimezone(timezone.utc)

    start_str = args.get("backfill_start")
    end_str = args.get("backfill_end")

    if end_str:
        backfill_end = parse_iso_datetime("backfill_end", end_str)
    else:
        backfill_end = datetime.now(timezone.utc)

    if start_str is None:
        return None, backfill_end

    backfill_start = parse_iso_datetime("backfill_start", start_str)

    if backfill_start >= backfill_end:
        influxdb3_local.error(
            f"[{task_id}] backfill_start must be earlier than backfill_end."
        )
        raise Exception(
            f"[{task_id}] backfill_start must be earlier than backfill_end."
        )

    return backfill_start, backfill_end


def generate_fields_string(
    fields_aggregate_list: list[tuple[str, str]],
    interval: tuple[int, str],
    tags_list: list,
):
    """
    Generates the SELECT clause for downsampling.

    Args:
        fields_aggregate_list (list[tuple[str, str]]): List of tuples containing field names and aggregation functions.
        interval (tuple[int, str]): Tuple of interval magnitude and unit (e.g., (10, 'minutes')).
        tags_list (list): List of tag names to include in the query.

    Returns:
        str: SQL SELECT clause string including DATE_BIN, aggregations, time_from, time_to, and tags.
    """
    query = f"DATE_BIN(INTERVAL '{interval[0]} {interval[1]}', time, '1970-01-01T00:00:00Z') AS _time,\n \
    \tcount(*) AS record_count,\n \
    \tMIN(time) AS time_from,\n \
    \tMAX(time) AS time_to"

    for field in fields_aggregate_list:
        query += ",\n"
        query += f'\t{field[1]}("{field[0]}") as "{field[0]}_{field[1]}"'

    for tag in tags_list:
        query += f',\n\t"{tag}"'

    return query


def generate_group_by_string(tags_list):
    """
    Generates the GROUP BY clause for downsampling queries.

    Args:
        tags_list (list): List of tag names to include in the GROUP BY clause.

    Returns:
        str: SQL GROUP BY clause string including '_time' and tags.
    """
    group_by_clause = f"_time"
    for tag in tags_list:
        group_by_clause += f", {tag}"
    return group_by_clause


def generate_tag_filter_clause(tag_values):
    """
    Generates the WHERE clause for filtering by tag values.

    Args:
        tag_values (dict | None): Dictionary mapping tag names to lists of values, or None.

    Returns:
        str: SQL WHERE clause string for tag filters, or empty string if tag_values is None.
    """
    if tag_values is None:
        return ""

    influxql = ""
    for key, values in tag_values.items():
        if len(values) == 1:
            influxql += f"AND\n\t\"{key}\" = '{values[0]}'\n"
        else:
            quoted_values = ", ".join(f"'{v}'" for v in values)
            influxql += f'AND\n\t"{key}" IN ({quoted_values})\n'
    return influxql


def build_downsample_query(
    fields_list: list[tuple[str, str]],
    measurement: str,
    tags_list: list[str],
    interval: tuple[int, str],
    tag_values: dict[str, list[str]] | None,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """
    Builds a downsampling SQL query for any mode (HTTP or scheduler), given explicit start/end.

    Args:
        fields_list: [(field, aggregation), ...]
        measurement: source measurement name
        tags_list: list of tag keys to GROUP BY
        interval: (magnitude, unit) for DATE_BIN
        tag_values: optional tag filters {tag: [val1, val2]}
        start_time: UTC datetime for WHERE time > ...
        end_time:   UTC datetime for WHERE time < ...

    Returns:
        A complete SQL query string.
    """
    # SELECT clause
    fields_clause = generate_fields_string(fields_list, interval, tags_list)
    # GROUP BY clause
    group_by = generate_group_by_string(tags_list)
    # tag filters
    tag_filter = generate_tag_filter_clause(tag_values)

    # ISO timestamps
    start_iso = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    query = f"""
        SELECT
            {fields_clause}
        FROM
            '{measurement}'
        WHERE
            time >= '{start_iso}'
        AND 
            time < '{end_iso}'
        {tag_filter}
        GROUP BY
        {group_by}
    """
    return query


def write_downsampled_data(
    influxdb3_local,
    data: list,
    max_retries: int,
    target_measurement: str,
    target_database: str | None,
    task_id: str,
):
    """
    Writes downsampled data to the target measurement with retry logic.

    Args:
        influxdb3_local: InfluxDB client instance.
        data (list): List of LineBuilder objects to write.
        max_retries (int): Maximum number of retry attempts for write operations.
        target_measurement (str): Name of the target measurement.
        target_database (str | None): Target database name, or None to use the default database.
        task_id (str): The task ID.

    Returns:
        tuple[bool, str | None, int]: Tuple containing success status, error message (if any), and number of retries.
    """
    retry_count = 0
    try:
        for tries in range(max_retries):
            try:
                for row in data:
                    if target_database:
                        influxdb3_local.write_to_db(target_database, row)
                    else:
                        influxdb3_local.write(row)
                influxdb3_local.info(
                    f"[{task_id}] Successful write to {target_measurement}."
                )
                return True, None, retry_count

            except Exception as e:
                retry_count += 1
                influxdb3_local.warn(
                    f"[{task_id}] Error write attempt {tries + 1}: {str(e)}."
                )
                wait_time = (2**tries) + random.random()
                time.sleep(wait_time)

                if tries == max_retries - 1:
                    raise

    except Exception as e:
        influxdb3_local.error(f"[{task_id}] Write failed with exception {str(e)}.")
        return False, str(e), retry_count


def transform_to_influx_line(
    data: list[dict],
    measurement: str,
    fields_list: list[tuple[str, str]],
    tags_list: list,
) -> list[LineBuilder]:
    """
    Transforms data into LineBuilder objects for writing to InfluxDB.

    Args:
        data (list[dict]): List of data rows as dictionaries.
        measurement (str): Name of the target measurement.
        fields_list (list[tuple[str, str]]): List of tuples containing field names and aggregation functions.
        tags_list (list): List of tag names.

    Returns:
        list[LineBuilder]: List of LineBuilder objects ready for writing to InfluxDB.
    """
    builders = []
    fields_mapping = {
        f"{field}_{aggregate}": f"{field}_{aggregate}"
        for field, aggregate in fields_list
    }

    fields_mapping["record_count"] = "record_count"
    fields_mapping["time_from"] = "time_from"
    fields_mapping["time_to"] = "time_to"

    for row in data:
        builder = LineBuilder(measurement)
        timestamp = row["_time"]
        builder.time_ns(timestamp)
        for tag in tags_list:
            if tag in row and row[tag] is not None:
                builder.tag(tag, str(row[tag]))

        has_fields = False
        for field_key, field_name in fields_mapping.items():
            if field_key in row and row[field_key] is not None:
                value = row[field_key]
                if isinstance(value, int):
                    builder.int64_field(field_name, value)
                elif isinstance(value, float):
                    builder.float64_field(field_name, value)
                else:
                    builder.string_field(field_name, str(value))
                has_fields = True

        if has_fields:
            builders.append(builder)

    return builders


def process_scheduled_call(
    influxdb3_local, call_time: datetime, args: dict | None = None
):
    """
    Processes a scheduled downsampling call.

    Args:
        influxdb3_local: InfluxDB client instance.
        call_time (datetime): Time of the scheduled call.
        args (dict | None): Configuration parameters for downsampling.

    Raises:
        Exception: If no args are provided.
    """
    task_id = str(uuid.uuid4())
    influxdb3_local.info(
        f"[{task_id}] Starting downsampling schedule for call_time: {call_time}."
    )

    if args is None:
        influxdb3_local.error(f"[{task_id}] No args provided for plugin.")
        raise Exception(f"[{task_id}] No args provided for plugin.")

    start_time: float = time.time()
    source_measurement, target_measurement = parse_source_and_target_measurement(
        influxdb3_local, args, task_id
    )
    target_database: str | None = args.get("target_database", None)
    tag_value_filters: dict | None = parse_tag_values_for_scheduler(
        influxdb3_local, args, source_measurement, task_id
    )
    tags: list = get_tag_names(influxdb3_local, source_measurement, task_id)
    fields: list = parse_field_aggregations_for_scheduler(
        influxdb3_local, args, task_id
    )
    interval: tuple = parse_time_interval(influxdb3_local, args, "interval", task_id)
    max_retries: int = parse_max_retries(args)
    offset: timedelta = parse_offset(influxdb3_local, args, task_id)
    window: timedelta = parse_window(influxdb3_local, args, task_id)
    call_time_: datetime = call_time.replace(tzinfo=timezone.utc)

    real_now = call_time_ - offset
    real_then = real_now - window

    query: str = build_downsample_query(
        fields,
        source_measurement,
        tags,
        interval,
        tag_value_filters,
        real_then,
        real_now,
    )

    data = influxdb3_local.query(query)

    transformed_data: list = transform_to_influx_line(
        data, target_measurement, fields, tags
    )

    success, error, retries = write_downsampled_data(
        influxdb3_local,
        transformed_data,
        max_retries,
        target_measurement,
        target_database,
        task_id,
    )

    end_time = time.time()
    execution_time = end_time - start_time
    if not success:
        influxdb3_local.error(
            f"[{task_id}] Downsampling job failed with {error}, {retries} retries."
        )
        return

    influxdb3_local.info(
        f"[{task_id}] Downsampling job finished in {execution_time} seconds."
    )


def process_request(
    influxdb3_local, query_parameters, request_headers, request_body, args=None
):
    """
    Processes an HTTP request for downsampling.

    Args:
        influxdb3_local: InfluxDB client instance.
        query_parameters: Query parameters from the HTTP request (unused).
        request_headers: HTTP request headers (unused).
        request_body: JSON-encoded request body containing downsampling parameters.
        args: Optional additional arguments (unused).

    Raises:
        Exception: If no request body is provided.)
    """
    task_id = str(uuid.uuid4())

    if request_body:
        data = json.loads(request_body)
        influxdb3_local.info(f"[{task_id}] Request data: {data}.")
    else:
        influxdb3_local.error(f"[{task_id}] No request body provided.")
        raise Exception(f"[{task_id}] No request body provided.")

    influxdb3_local.info(f"[{task_id}] Starting downsampling process.")
    start_time = time.time()

    source_measurement, target_measurement = parse_source_and_target_measurement(
        influxdb3_local, data, task_id
    )
    target_database: str | None = data.get("target_database", None)
    tag_value_filters: dict | None = parse_tag_values_for_http(
        influxdb3_local, data, source_measurement, task_id
    )
    tags: list = get_tag_names(influxdb3_local, source_measurement, task_id)
    fields: list = parse_field_aggregations_for_http(influxdb3_local, data, task_id)
    interval: tuple = parse_time_interval(influxdb3_local, data, "interval", task_id)
    max_retries: int = parse_max_retries(data)

    batch_size: tuple = parse_time_interval(
        influxdb3_local, data, "batch_size", task_id
    )
    backfill_start, backfill_end = parse_backfill_window(influxdb3_local, data, task_id)

    if backfill_start is None:
        q = f"SELECT MIN(time) as _t FROM {source_measurement}"
        res = influxdb3_local.query(q)
        oldest = res[0].get("_t")

        backfill_start: datetime = datetime.fromtimestamp(oldest / 1e9, tz=timezone.utc)
        influxdb3_local.info(
            f"[{task_id}] Full mode: from {backfill_start} to {backfill_end}."
        )
    else:
        influxdb3_local.info(
            f"[{task_id}] Window mode: from {backfill_start} to {backfill_end}."
        )

    cursor = backfill_start
    total_retries = 0

    magnitude, unit = batch_size
    unit_mapping = {
        "seconds": lambda x: timedelta(seconds=x),
        "minutes": lambda x: timedelta(minutes=x),
        "hours": lambda x: timedelta(hours=x),
        "days": lambda x: timedelta(days=x),
    }
    batch_delta = unit_mapping[unit.lower()](magnitude)
    while cursor < backfill_end:
        batch_end = min(cursor + batch_delta, backfill_end)

        query = build_downsample_query(
            fields,
            source_measurement,
            tags,
            interval,
            tag_value_filters,
            cursor,
            batch_end,
        )

        data = influxdb3_local.query(query)
        transformed_data = transform_to_influx_line(
            data, target_measurement, fields, tags
        )
        success, result, retries = write_downsampled_data(
            influxdb3_local,
            transformed_data,
            max_retries,
            target_measurement,
            target_database,
            task_id,
        )
        if not success:
            influxdb3_local.warn(
                f"[{task_id}] Write failed for batch {cursor} → {batch_end}: {result} (retries={retries})."
            )
        else:
            influxdb3_local.info(
                f"[{task_id}] Batch {cursor} → {batch_end} written successfully (retries={retries})."
            )

            total_retries += retries

        cursor = batch_end

    duration = time.time() - start_time
    influxdb3_local.info(
        f"[{task_id}] Downsampling completed on '{source_measurement}' → '{target_measurement}': "
        f"{total_retries} retries, duration {duration:.2f}s."
    )
