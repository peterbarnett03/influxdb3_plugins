import json
import operator
import os
import random
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from string import Template
from urllib.parse import urlparse

import requests

# Supported comparison operators
_OP_FUNCS: dict = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}

# Supported sender types with their required arguments
AVAILABLE_SENDERS: dict = {
    "slack": ["slack_webhook_url", "slack_headers"],
    "discord": ["discord_webhook_url", "discord_headers"],
    "http": ["http_webhook_url", "http_headers"],
    "whatsapp": [
        "twilio_sid",
        "twilio_token",
        "twilio_to_number",
        "twilio_from_number",
    ],
    "sms": ["twilio_sid", "twilio_token", "twilio_to_number", "twilio_from_number"],
}

# List of keywords to exclude from argument validation in AVAILABLE_SENDERS
EXCLUDED_KEYWORDS = ["headers", "token", "sid"]


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


def parse_senders(influxdb3_local, args: dict, task_id: str) -> dict:
    """
    Parse and validate sender configurations from input arguments.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Input arguments containing "senders" and related configs.
        task_id (str): Unique task identifier.

    Returns:
        dict: A dictionary of validated sender configurations.

    Raises:
        Exception: If no valid senders are found.
    """
    senders_config: defaultdict = defaultdict(dict)

    senders: list = args["senders"].split(".")
    for sender in senders:
        if sender not in AVAILABLE_SENDERS:
            influxdb3_local.warn(f"[{task_id}] Invalid sender type: {sender}")
            continue
        for key in AVAILABLE_SENDERS[sender]:
            if key not in args and not any(ex in key for ex in EXCLUDED_KEYWORDS):
                influxdb3_local.warn(
                    f"[{task_id}] Missing required argument for {sender}: {key}"
                )
                senders_config.pop(sender, None)
                break
            if "url" in key and not validate_webhook_url(
                influxdb3_local, sender, args[key], task_id
            ):
                senders_config.pop(sender, None)
                break

            if key not in args:
                continue
            senders_config[sender][key] = args[key]

    if not senders_config:
        raise Exception(f"[{task_id}] No valid senders configured")
    return senders_config


def validate_webhook_url(influxdb3_local, service: str, url: str, task_id: str) -> bool:
    """
    Validate webhook URL format.

    Args:
        influxdb3_local: InfluxDB client instance.
        service (str): Type of service (e.g., "slack", "telegram", etc.).
        url (str): Webhook URL to validate.
        task_id (str): Unique task identifier.

    Returns:
        bool: True if URL is valid, False otherwise
    """
    try:
        result = urlparse(url)
        if result.scheme not in ("http", "https"):
            influxdb3_local.error(
                f"[{task_id}] {service} webhook URL must start with 'https://' or 'http://'"
            )
            return False
        return True
    except Exception as e:
        influxdb3_local.error(
            f"[{task_id}] Unable to parse {service} webhook URL: {str(e)}"
        )
        return False


def _coerce_value(raw: str) -> str | int | float | bool:
    """
    Convert a raw string value into int, float, bool, or str.
    """
    raw = raw.strip()
    # Boolean
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    # Integer
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    # Float
    if re.fullmatch(r"-?\d+\.\d*", raw):
        return float(raw)
    # Quoted string
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    # Unquoted string
    return raw


def parse_field_conditions(influxdb3_local, args: dict, task_id: str) -> list:
    """
    Parse a semicolon-separated list of field conditions into a list of triples.

    Each condition has the form:
        <field><op><value><level>
    where <op> is one of: >, <, >=, <=, ==, !=
    Multiple conditions are separated by semicolons ':'.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Input arguments containing "field_conditions".
        task_id (str): Unique task identifier.

    Returns:
        List of tuples: (field_name (str), operator_fn (callable), compare_value, level)

    Example:
        parse_field_conditions("temp>30-ERROR:status=='ok'-INFO:count<=100-WARN")
        [
            ("temp", operator.gt, 30, ERROR),
            ("status", operator.eq, "ok", INFO),
            ("count", operator.le, 100, WARN)
        ]
    """
    allowed_message_levels = {"INFO", "WARN", "ERROR"}
    cond_str: str | None = args.get("field_conditions")
    if not cond_str:
        raise Exception(f"[{task_id}] Missing required argument: field_conditions")

    conditions = []
    for part in cond_str.split(":"):
        part = part.strip()
        if not part:
            continue

        # Extract message level (optional)
        if "-" not in part:
            influxdb3_local.warn(
                f"[{task_id}] Invalid field_conditions in condition '{part}', should contain '-'"
            )
            continue

        cond_expr, level = part.rsplit("-", 1)
        level = level.strip().upper()
        if level not in allowed_message_levels:
            influxdb3_local.warn(
                f"[{task_id}] Invalid message level '{level}' in condition '{part}'"
            )
            continue

        # Parse field/operator/value
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*(>=|<=|==|!=|>|<)\s*(.+)$", cond_expr)
        if not m:
            influxdb3_local.warn(f"[{task_id}] Invalid condition format: '{part}'")
            continue
        field, op, raw_val = m.groups()

        if op not in _OP_FUNCS:
            influxdb3_local.warn(
                f"[{task_id}] Unsupported operator '{op}' in condition '{part}'"
            )
            continue

        value = _coerce_value(raw_val)
        conditions.append((field, _OP_FUNCS[op], value, level))

    if not conditions:
        raise Exception(f"[{task_id}] No valid field conditions provided.")
    return conditions


def parse_port_override(args: dict, task_id: str) -> int:
    """
    Parse and validate the 'port_override' argument, converting it from string to int.

    Args:
        args (dict): Runtime arguments containing 'port_override'.
        task_id (str): Unique task identifier for logging context.

    Returns:
        int: Parsed port number (1–65535), or 8181 if not provided.

    Raises:
        Exception: If 'port_override' is provided but is not a valid integer in the range 1–65535.
    """
    raw = args.get("port_override", 8181)

    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise Exception(f"[{task_id}] Invalid port_override, not an integer: {raw!r}")

    # Validate port range
    if not (1 <= port <= 65535):
        raise Exception(
            f"[{task_id}] Invalid port_override, must be between 1 and 65535: {port}"
        )

    return port


def interpolate_notification_text(text: str, row_data: dict) -> str:
    """
    Replace variables in notification text with actual values from row data.

    Args:
        text (str): Template string with variables
        row_data (dict): Dictionary containing values to interpolate

    Returns:
        str: Interpolated text with variables replaced
    """
    return Template(text).safe_substitute(row_data)


def send_notification(
    influxdb3_local, port: int, path: str, token: str, payload: dict, task_id: str
) -> None:
    """
    Send a JSON POST to the given InfluxDB 3 webhook endpoint, with up to
    3 retry attempts and randomized backoff delays between attempts.

    Args:
        influxdb3_local: InfluxDB client instance.
        port (int): Port number on which the HTTP API is listening (e.g. 8181).
        path (str): Path to the webhook handler (e.g. "notify" or "custom/path").
        token (str): API v3 token string (without the "Bearer " prefix).
        payload (dict): Dict to serialize as JSON in the POST body.
        task_id (str): Unique task identifier.

    Raises:
        requests.RequestException: If all retries fail or a non-2xx response is received.
    """
    url = f"http://localhost:{port}/api/v3/engine/{path}"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    data = json.dumps(payload)

    max_retries: int = 3
    timeout: float = 5.0

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=timeout)
            resp.raise_for_status()  # raises on 4xx/5xx
            influxdb3_local.info(
                f"[{task_id}] Alert sent successfully to notification plugin with results: {resp.json()['results']}"
            )
            break
        except requests.RequestException as e:
            influxdb3_local.warn(
                f"[{task_id}] [Attempt {attempt}/{max_retries}] Error sending alert to notification plugin: {e}"
            )
            if attempt < max_retries:
                wait = random.uniform(1, 4)
                influxdb3_local.info(
                    f"[{task_id}] Retrying sending alert to notification plugin in {wait:.1f} seconds."
                )
                time.sleep(wait)
            else:
                influxdb3_local.error(
                    f"[{task_id}] Failed to send alert to notification plugin after {max_retries} attempts: {e}"
                )


def process_writes(influxdb3_local, table_batches: list, args: dict):
    """
    Process incoming data writes and trigger notifications if field conditions are met
    for a specified number of times.
    """
    task_id = str(uuid.uuid4())

    if (
        not args
        or "measurement" not in args
        or "field_conditions" not in args
        or "senders" not in args
    ):
        influxdb3_local.error(
            f"[{task_id}] Missing required arguments: measurement, field_conditions, or senders"
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
        trigger_count: int = int(args.get("trigger_count", 1))
        senders_config: dict = parse_senders(influxdb3_local, args, task_id)
        field_conditions: list = parse_field_conditions(influxdb3_local, args, task_id)
        port_override: int = parse_port_override(args, task_id)
        notification_path: str = args.get("notification_path", "notify")
        influxdb3_auth_token: str = os.getenv("INFLUXDB3_AUTH_TOKEN") or args.get("influxdb3_auth_token")
        if influxdb3_auth_token is None:
            influxdb3_local.error(
                f"[{task_id}] Missing required argument: influxdb3_auth_token"
            )
            return
        notification_tpl = args.get(
            "notification_text",
            "[$level] InfluxDB 3 alert triggered. Condition $field $op_sym $compare_val matched $trigger_count times($actual) — matched in row $row.",
        )

        for table_batch in table_batches:
            table_name: str = table_batch["table_name"]
            if table_name != measurement:
                continue

            tags: list = get_tag_names(influxdb3_local, table_name, task_id)
            for row in table_batch["rows"]:
                for field, compare_fn, compare_val, level in field_conditions:
                    if field not in row:
                        influxdb3_local.warn(
                            f"[{task_id}] Field '{field}' not found in row: {row}"
                        )
                        continue

                    actual = row[field]
                    cache_key: str = generate_cache_key(table_name, field, level, row, tags)
                    if compare_fn(actual, compare_val):
                        cache_value = influxdb3_local.cache.get(cache_key)
                        current_count = (
                            int(cache_value) if cache_value is not None else 0
                        )

                        # reconstruct operator symbol from function
                        op_sym = next(
                            sym for sym, fn in _OP_FUNCS.items() if fn is compare_fn
                        )

                        if current_count >= (trigger_count - 1):
                            notification_text = interpolate_notification_text(
                                notification_tpl,
                                {
                                    "level": level,
                                    "row": cache_key,
                                    "field": field,
                                    "op_sym": op_sym,
                                    "compare_val": compare_val,
                                    "trigger_count": trigger_count,
                                    "actual": actual,
                                },
                            )

                            payload: dict = {
                                "notification_text": notification_text,
                                "senders_config": senders_config,
                            }

                            influxdb3_local.error(
                                f"[{task_id}] [{level}] Condition {field} {op_sym} {compare_val!r} matched in row {cache_key} {trigger_count} times ({actual!r}), sending alert"
                            )
                            send_notification(
                                influxdb3_local,
                                port_override,
                                notification_path,
                                influxdb3_auth_token,
                                payload,
                                task_id,
                            )
                            influxdb3_local.cache.put(
                                cache_key, "0"
                            )
                        else:
                            influxdb3_local.warn(
                                f"[{task_id}] [{level}] Condition {field} {op_sym} {compare_val!r} matched in row {cache_key} ({actual!r}) for the {current_count + 1}/{trigger_count} time. Skipping alert."
                            )
                            influxdb3_local.cache.put(
                                cache_key, str(current_count + 1)
                            )

                    else:
                        influxdb3_local.cache.put(cache_key, "0")

    except Exception as e:
        influxdb3_local.error(f"[{task_id}] Error: {str(e)}")


def parse_window(influxdb3_local, args: dict, task_id: str) -> timedelta:
    """
    Parses the 'window' argument from args and converts it into a timedelta object.
    Represents the size of the query window.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Dictionary with the 'window' key (e.g., {"window": "2h"}).
        task_id (str): Unique identifier for the current task, used for logging.

    Returns:
        timedelta: Parsed time delta for the window.

    Raises:
        Exception: If the window is missing or has an invalid format or unit.

    Example input:
        args = {"window": "3d"}  # valid units: 's', 'min', 'h', 'd', 'w'
    """
    valid_units: dict = {
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


def generate_fields_string(
    field_aggregation_values: dict,
    interval: tuple,
    tags_list: list,
):
    """
    Generates the SELECT clause.

    Args:
        field_aggregation_values: dict
        interval (tuple[int, str]): Tuple of interval magnitude and unit (e.g., (10, 'minutes')).
        tags_list (list): List of tag names to include in the query.

    Returns:
        str: SQL SELECT clause string including DATE_BIN, aggregations and tags.
    """
    query = f"DATE_BIN(INTERVAL '{interval[0]} {interval[1]}', time, '1970-01-01T00:00:00Z') AS _time"

    for field_name, aggregation_value_list in field_aggregation_values.items():
        for aggregation, op_fn, value, level in aggregation_value_list:
            if f'{aggregation}("{field_name}")' in query:
                continue
            query += ",\n"
            query += f'\t{aggregation}("{field_name}") as "{field_name}_{aggregation}"'

    for tag in tags_list:
        query += f',\n\t"{tag}"'

    return query


def generate_group_by_string(tags_list: list):
    """
    Generates the GROUP BY clause for queries.

    Args:
        tags_list (list): List of tag names to include in the GROUP BY clause.

    Returns:
        str: SQL GROUP BY clause string including '_time' and tags.
    """
    group_by_clause = f"_time"
    for tag in tags_list:
        group_by_clause += f", {tag}"
    return group_by_clause


def build_query(
    field_aggregation_values: dict,
    measurement: str,
    tags_list: list[str],
    interval: tuple,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """
    Builds an SQL query.

    Args:
        field_aggregation_values: dict for aggregation building
        measurement: source measurement name
        tags_list: list of tag keys to GROUP BY
        interval: (magnitude, unit) for DATE_BIN
        start_time: UTC datetime for WHERE time > ...
        end_time:   UTC datetime for WHERE time < ...

    Returns:
        A complete SQL query string.
    """
    # SELECT clause
    fields_clause = generate_fields_string(
        field_aggregation_values, interval, tags_list
    )
    # GROUP BY clause
    group_by = generate_group_by_string(tags_list)

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
        GROUP BY
        {group_by}
    """
    return query


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


def parse_time_interval(args: dict, task_id: str) -> tuple[int, str]:
    """
    Parses the interval string into a tuple of magnitude and unit.

    Supports time units: seconds (s), minutes (min), hours (h), days (d).

    Args:
        args (dict): Dictionary containing configuration parameters, including the 'interval' key
            with a string in the format '<number><unit>' (e.g., '10min', '2s', '1h').
        task_id (str): The task ID.

    Returns:
        tuple[int, str]: A tuple containing the magnitude (integer) and the unit (e.g., 'minutes' or 'days').
            For months, quarters, and years, the magnitude is the equivalent number of days, and the unit is 'days'.

    Raises:
        Exception: If the interval format is invalid, the unit is not supported, or the magnitude is less than 1.
    """
    unit_mapping = {"s": "seconds", "min": "minutes", "h": "hours", "d": "days"}

    valid_units = unit_mapping.keys()

    interval: str = args.get("interval", "5min")

    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", interval)
    if match:
        number_part, unit = match.groups()
        magnitude = int(number_part)
        if unit in valid_units and magnitude >= 1:
            return magnitude, unit_mapping[unit]

    raise Exception(f"[{task_id}] Invalid interval format: {interval}.")


def parse_field_aggregation_values(
    influxdb3_local, args: dict, task_id: str
) -> dict[str, list[tuple]] | None:
    """
    Parses field aggregation values with comparison operators and message levels.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Contains the 'field_aggregation_values' key with $-separated strings,
            e.g., 'field:avg@">=10-INFO"$field2:min@"<5.0-WARN"'.
        task_id (str): Task identifier (used for logging/warnings).

    Returns:
        dict[str, list[tuple[str, callable, float, str]]]: Dictionary mapping field names to a list of tuples:
            (aggregation, comparison_operator_fn, threshold_value, message_level).

    Raises:
        Exception: If no valid entries are found.
    """
    available_aggregations = {
        "avg",
        "count",
        "sum",
        "min",
        "max",
        "derivative",
        "median",
    }
    allowed_operators = {">", "<", ">=", "<=", "==", "!="}
    allowed_message_levels = {"INFO", "WARN", "ERROR"}

    raw_input: str | None = args.get("field_aggregation_values")
    if raw_input is None:
        return {}

    result: dict[str, list[tuple]] = {}

    pairs = raw_input.split("$")
    for pair in pairs:
        if not pair or ":" not in pair:
            influxdb3_local.warn(
                f"[{task_id}] Invalid format in pair '{pair}', skipping..."
            )
            continue

        field_name, agg_expr = pair.split(":", 1)
        if "@" not in agg_expr:
            influxdb3_local.warn(
                f"[{task_id}] Missing '@' in '{agg_expr}', skipping..."
            )
            continue

        aggregation, value_expr = agg_expr.split("@", 1)
        aggregation = aggregation.strip()
        if aggregation not in available_aggregations:
            influxdb3_local.warn(
                f"[{task_id}] Unsupported aggregation '{aggregation}', skipping..."
            )
            continue

        # Strip quotes around the value expression if present
        if value_expr[0] == value_expr[-1] and value_expr[0] in ('"', "'"):
            value_expr = value_expr[1:-1]

        # Extract comparison operator
        matched_op = next(
            (
                op
                for op in sorted(allowed_operators, key=len, reverse=True)
                if value_expr.startswith(op)
            ),
            None,
        )
        if not matched_op:
            influxdb3_local.warn(
                f"[{task_id}] No valid comparison operator found in '{value_expr}', skipping..."
            )
            continue

        # Separate value and message level (by '-')
        try:
            value_and_level = value_expr[len(matched_op) :].strip()
            value_str, level = value_and_level.rsplit("-", 1)
            level = level.upper()
        except ValueError:
            influxdb3_local.warn(
                f"[{task_id}] Missing or invalid message level in '{value_expr}', skipping..."
            )
            continue

        if level not in allowed_message_levels:
            influxdb3_local.warn(
                f"[{task_id}] Invalid message level '{level}', skipping..."
            )
            continue

        try:
            value = float(value_str.strip())
        except ValueError:
            influxdb3_local.warn(
                f"[{task_id}] Value '{value_str}' is not a valid float, skipping..."
            )
            continue

        entry = (aggregation, _OP_FUNCS[matched_op], value, level)
        result.setdefault(field_name.strip(), []).append(entry)

    if not result:
        raise Exception(f"[{task_id}] No valid field aggregation values provided.")

    return result


def generate_cache_key(
        measurement: str,
        field: str,
        level: str,
        row: dict,
        tags: list,
        aggregation: str | None = None
) -> str:
    """Generate cache key based on input parameters. Aggregation is optional."""
    base_parts = [measurement, field]
    if aggregation:
        base_parts.append(aggregation)
    base_parts.append(level)

    cache_key = ":".join(base_parts)

    for tag in sorted(tags):
        tag_value = row.get(tag, "None")
        cache_key += f":{tag}={tag_value}"

    return cache_key


def process_scheduled_call(influxdb3_local, call_time: datetime, args: dict):
    """
    Check for recent data in a specified measurement and send a notification
    if data is missing or matched aggregation conditions for a configured number of checks.

    Args:
        influxdb3_local: InfluxDB client instance used for querying and logging.
        call_time (datetime): The current time of the scheduled check.
        args (dict): Configuration dictionary containing keys like
            "measurement", "senders", "influxdb3_auth_token", "window", and other alert settings.
    """
    task_id = str(uuid.uuid4())
    # Configuration
    if (
        not args
        or "measurement" not in args
        or "senders" not in args
        or "window" not in args
    ):
        influxdb3_local.error(
            f"[{task_id}] Missing required arguments: measurement, senders, or window"
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
        trigger_count: int = int(args.get("trigger_count", 1))
        senders_config: dict = parse_senders(influxdb3_local, args, task_id)
        field_aggregation_values: dict = parse_field_aggregation_values(
            influxdb3_local, args, task_id
        )
        deadman_check: bool = True if args.get("deadman_check") else False
        if not field_aggregation_values and not deadman_check:
            influxdb3_local.error(
                "For the plugin to work, you must provide a valid field_aggregation_values parameter or set deadman_check to True"
            )
            return

        port_override: int = parse_port_override(args, task_id)
        notification_path: str = args.get("notification_path", "notify")
        influxdb3_auth_token: str = os.getenv("INFLUXDB3_AUTH_TOKEN") or args.get("influxdb3_auth_token")
        if influxdb3_auth_token is None:
            influxdb3_local.error(
                f"[{task_id}] Missing required environment variable: INFLUXDB3_AUTH_TOKEN"
            )
            return
        notification_tpl_deadman = args.get(
            "notification_deadman_text",
            "Deadman Alert: No data received from $table from $time_from to $time_to.",
        )
        notification_tpl_threshold = args.get(
            "notification_threshold_text",
            "[$level] Threshold Alert on table $table: $aggregation of $field $op_sym $compare_val (actual: $actual) — matched in row $row.",
        )

        tags: list = get_tag_names(influxdb3_local, measurement, task_id)
        window: timedelta = parse_window(influxdb3_local, args, task_id)
        interval: tuple = parse_time_interval(args, task_id)

        time_to: datetime = call_time.replace(tzinfo=timezone.utc)
        time_from: datetime = time_to - window

        query = build_query(
            field_aggregation_values, measurement, tags, interval, time_from, time_to
        )

        results = influxdb3_local.query(query)
        if not results and deadman_check:
            cache_value: str | None = influxdb3_local.cache.get(measurement)
            current_count = int(cache_value) if cache_value is not None else 0

            if current_count >= (trigger_count - 1):
                influxdb3_local.error(
                    f"[{task_id}] No data found in '{measurement}' from {time_from} to {time_to} for {trigger_count} times. Sending alert."
                )

                notification_text = interpolate_notification_text(
                    notification_tpl_deadman,
                    {"table": measurement, "time_from": time_from, "time_to": time_to},
                )

                payload: dict = {
                    "notification_text": notification_text,
                    "senders_config": senders_config,
                }

                send_notification(
                    influxdb3_local,
                    port_override,
                    notification_path,
                    influxdb3_auth_token,
                    payload,
                    task_id,
                )
                influxdb3_local.cache.put(measurement, "0")
            else:
                influxdb3_local.warn(
                    f"[{task_id}] No data found in '{measurement}' from {time_from} to {time_to} for {current_count + 1}/{trigger_count} times. Skipping alert."
                )
                influxdb3_local.cache.put(measurement, str(current_count + 1))
        else:
            influxdb3_local.cache.put(measurement, "0")

        for row in results:
            for field, aggregation_values in field_aggregation_values.items():
                for aggregation, compare_fn, compare_value, level in aggregation_values:
                    cache_key: str = generate_cache_key(
                        measurement, field, level, row, tags, aggregation
                    )

                    if f"{field}_{aggregation}" not in row:
                        influxdb3_local.warn(
                            f"[{task_id}] Field '{field}' not found in row: {row}"
                        )
                        continue

                    actual = row[f"{field}_{aggregation}"]
                    if compare_fn(actual, compare_value):
                        cache_value: str | None = influxdb3_local.cache.get(cache_key)
                        current_count = (
                            int(cache_value) if cache_value is not None else 0
                        )

                        # reconstruct operator symbol from function
                        op_sym = next(
                            sym for sym, fn in _OP_FUNCS.items() if fn is compare_fn
                        )

                        if current_count >= (trigger_count - 1):
                            notification_text = interpolate_notification_text(
                                notification_tpl_threshold,
                                {
                                    "level": level,
                                    "field": field,
                                    "table": measurement,
                                    "row": cache_key,
                                    "op_sym": op_sym,
                                    "aggregation": aggregation,
                                    "compare_val": compare_value,
                                    "actual": actual,
                                },
                            )

                            payload: dict = {
                                "notification_text": notification_text,
                                "senders_config": senders_config,
                            }

                            influxdb3_local.error(
                                f"[{task_id}] Condition on {measurement}: {field} {op_sym} {compare_value!r} matched {trigger_count} times in row {cache_key} ({actual!r}), sending alert"
                            )
                            send_notification(
                                influxdb3_local,
                                port_override,
                                notification_path,
                                influxdb3_auth_token,
                                payload,
                                task_id,
                            )
                            influxdb3_local.cache.put(cache_key, "0")
                        else:
                            influxdb3_local.warn(
                                f"[{task_id}] Condition for row {cache_key} ({field} {op_sym} {compare_value!r}) matched ({actual!r}) for the {current_count + 1}/{trigger_count} time. Skipping alert."
                            )
                            influxdb3_local.cache.put(cache_key, str(current_count + 1))
                    else:
                        influxdb3_local.cache.put(cache_key, "0")

    except Exception as e:
        influxdb3_local.error(f"[{task_id}] Error: {str(e)}")
