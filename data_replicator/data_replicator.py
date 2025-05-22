import gzip
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from influxdb_client_3 import InfluxDBClient3, InfluxDBError


def ensure_queue_file(queue_file: Path) -> None:
    """Ensure the queue file directory exists."""
    if not queue_file.parent.exists():
        queue_file.parent.mkdir(parents=True)


def append_to_queue(
    influxdb3_local, queue_file: Path, entries: list, max_size: int, task_id: str
) -> None:
    """
    Append serialized entries to a compressed JSONL queue file.

    Args:
        influxdb3_local: Logger or client object for error reporting.
        queue_file (Path): Path to the queue file.
        entries (list): List of dictionaries to append to the queue.
        max_size (int): Maximum size in MB for the queue file.
        task_id (str): Unique task identifier for logging.

    Raises:
        Exception: If the queue file exceeds the defined max_size.
    """
    ensure_queue_file(queue_file)
    max_size_bytes: int = max_size * 1024 * 1024  # Convert MB to bytes
    if os.path.exists(queue_file) and os.path.getsize(queue_file) >= max_size_bytes:
        influxdb3_local.error(
            f"[{task_id}] Queue file size exceeds the maximum limit of {max_size}MB."
        )
        raise Exception(
            f"[{task_id}] Queue file size exceeds the maximum limit of {max_size}MB."
        )
    with gzip.open(queue_file, "at", encoding="utf-8") as f:
        for entry in entries:
            # Only store serializable fields (table, line)
            queue_entry = {"table": entry["table"], "line": entry["line"]}
            f.write(json.dumps(queue_entry) + "\n")


def read_queue(queue_file: Path) -> list:
    """Read all lines from the queue file."""
    ensure_queue_file(queue_file)
    if not queue_file.exists():
        return []
    with gzip.open(queue_file, "rt", encoding="utf-8") as f:
        return [json.loads(line.strip()) for line in f if line.strip()]


def truncate_queue(successful_entries: list, queue_file: Path) -> None:
    """Remove successfully replicated entries from the queue."""
    all_entries = read_queue(queue_file)
    remaining_entries: list = [
        entry for entry in all_entries if entry not in successful_entries
    ]
    with gzip.open(queue_file, "wt", encoding="utf-8") as f:
        for entry in remaining_entries:
            f.write(json.dumps(entry) + "\n")


def row_to_line_protocol(
    influxdb3_local,
    old_table_name: str,
    new_table_name: str,
    row: dict,
    task_id: str,
    excluded_fields: list,
    tables_fields_renames: dict,
    all_tags: list,
):
    """
    Convert a row dictionary into InfluxDB line protocol format.

    Args:
        influxdb3_local: Logger or cache client for info logging.
        old_table_name (str): Original table name in the local database.
        new_table_name (str): Mapped table name for remote DB.
        row (dict): Row data to convert.
        task_id (str): Unique ID used for logging.
        excluded_fields (list): Fields to exclude from replication.
        tables_fields_renames (dict, optional): Mapping of field renames for this table.
        all_tags (list, optional): List of tags.

    Returns:
        str | None: Line protocol string or None if row is invalid.
    """
    if not row:
        influxdb3_local.info(
            f"[{task_id}] Skipping row in table {old_table_name}: row is empty"
        )
        return None

    # Separate tags and fields
    tags = {
        tables_fields_renames.get(k, k): str(v)
        for k, v in row.items()
        if k != "time"
        and v is not None
        and not isinstance(v, (int, float, bool))
        and k not in excluded_fields
        and k in all_tags
    }
    fields = {
        tables_fields_renames.get(k, k): v
        for k, v in row.items()
        if k != "time"
        and v is not None
        and isinstance(v, (int, float, bool))
        and k not in excluded_fields
    }
    string_fields = {
        tables_fields_renames.get(k, k): str(v)
        for k, v in row.items()
        if k != "time"
        and v is not None
        and isinstance(v, str)
        and k not in tags
        and k not in fields
        and k not in excluded_fields
        and k not in all_tags
    }

    # Format tags
    tag_str: str = ""
    if tags:
        tag_pairs = [f"{k}={v}" for k, v in sorted(tags.items())]
        tag_str = "," + ",".join(tag_pairs)

    # Format fields
    field_pairs = []
    for k, v in sorted(fields.items()):
        if isinstance(v, bool):
            field_pairs.append(f"{k}={str(v).lower()}")
        elif isinstance(v, int):
            field_pairs.append(f"{k}={v}i")  # Explicitly mark integers
        else:
            field_pairs.append(f"{k}={v}")
    for k, v in sorted(string_fields.items()):
        field_pairs.append(f'{k}="{v}"')

    if not field_pairs:
        influxdb3_local.info(
            f"[{task_id}] Skipping row in table {old_table_name}: no fields provided - row: {row}"
        )
        return None

    field_str = ",".join(field_pairs)

    # Construct line protocol with the custom timestamp
    return f"{new_table_name}{tag_str} {field_str} {row['time']}"


def parse_exclusions(influxdb3_local, args: dict, task_id: str) -> dict[str, list[str]]:
    """
    Parse a string defining fields to exclude or fields with str type from replication per table.

    Args:
        influxdb3_local: Logger for error messages.
        args (dict): Dictionary of runtime arguments. Should contain the 'excluded_fields' key
                     in the format "<table1>:<field1>@<field2>.<table2>:<field3>..."
        task_id (str): Task identifier for logging.

    Returns:
        dict[str, list[str]]: Mapping of table names to lists.

    Raises:
        Exception: If the string format or identifier names are invalid.
    """
    string_input: str | None = args.get("excluded_fields", None)
    pattern: re.Pattern = re.compile(r"^[A-Za-z0-9_-]+$")
    exclusions: dict = {}

    if not string_input:
        return exclusions

    for block in string_input.split("."):
        block = block.strip()
        if not block:
            continue

        if ":" not in block:
            influxdb3_local.error(f"[{task_id}] Invalid segment '{block}': missing ':'")
            raise Exception(f"[{task_id}] Invalid segment '{block}': missing ':'")

        table, fields_raw = block.split(":", 1)

        if not pattern.fullmatch(table):
            influxdb3_local.error(f"[{task_id}] Invalid table name '{table}'")
            raise Exception(f"[{task_id}] Invalid table name '{table}'")

        if not fields_raw:
            exclusions[table] = []
            continue

        fields: list = []
        for field in fields_raw.split("@"):
            if not pattern.fullmatch(field):
                influxdb3_local.error(
                    f"[{task_id}] Invalid field name '{field}' in table '{table}'"
                )
                raise Exception(
                    f"[{task_id}] Invalid field name '{field}' in table '{table}'"
                )
            fields.append(field)

        exclusions[table] = fields

    return exclusions


def parse_table_renames(influxdb3_local, args: dict, task_id: str) -> dict[str, str]:
    """
    Parse table renaming rules from a dot-separated string.

    Args:
        influxdb3_local: Logger instance for logging errors.
        args (dict): Dictionary of runtime arguments. Must contain the 'tables_rename' key with format:
                     "<old_table1>:<new_table1>.<old_table2>:<new_table2>..."
        task_id (str): Task identifier used for log messages.

    Returns:
        dict[str, str]: Mapping of old table names to new names.

    Raises:
        Exception: If format is invalid or table names are malformed.
    """
    mapping_str: str | None = args.get("tables_rename", None)
    if mapping_str is None:
        return {}

    valid_name: re.Pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
    renames = {}

    pairs: list = mapping_str.split(".")
    for pair in pairs:
        if ":" not in pair:
            influxdb3_local.error(
                f"[{task_id}] Invalid mapping pair: '{pair}' (missing ':')"
            )
            raise Exception(f"[{task_id}] Invalid mapping pair: '{pair}' (missing ':')")

        old, new = pair.split(":", 1)

        if not valid_name.match(old):
            influxdb3_local.error(f"[{task_id}] Invalid table name: '{old}'")
            raise Exception(f"[{task_id}] Invalid table name: '{old}'")
        if not valid_name.match(new):
            influxdb3_local.error(f"[{task_id}] Invalid table name: '{new}'")
            raise Exception(f"[{task_id}] Invalid table name: '{new}'")

        renames[old] = new

    return renames


def parse_field_renames(
    influxdb3_local, args: dict, task_id: str
) -> dict[str, dict[str, str]]:
    """
    Parse a complex mapping string for renaming fields in specific tables.

    Format example:
        "table1:oldA@newA oldB@newB.table2:oldX@newX oldY@newY"

    Args:
        influxdb3_local: Logger for error messages.
        args (dict): Arguments containing the 'field_renames' key.
        task_id (str): Task identifier for logs.

    Returns:
        dict[str, dict[str, str]]: Nested dict mapping table names to old-new field name pairs.

    Raises:
        Exception: If mappings are malformed or contain invalid names.
    """
    mapping_str: str | None = args.get("field_renames", None)
    pattern: re.Pattern = re.compile(r"^[A-Za-z0-9_-]+$")
    if not mapping_str:
        return {}

    table_renames = {}
    for table_block in mapping_str.split("."):
        table_block = table_block.strip()
        if not table_block:
            continue  # skip empty blocks

        if ":" not in table_block:
            influxdb3_local.error(
                f"[{task_id}] Invalid segment '{table_block}': missing ':'"
            )
            raise Exception(f"[{task_id}] Invalid segment '{table_block}': missing ':'")

        table, fields_part = table_block.split(":", 1)
        if not pattern.fullmatch(table):
            influxdb3_local.error(f"[{task_id}] Invalid table name '{table}'")
            raise Exception(f"[{task_id}] Invalid table name '{table}'")

        # initialize inner mapping
        renames: dict = {}

        if fields_part:
            # split individual old@new mappings
            for mapping in fields_part.split(" "):
                if "@" not in mapping:
                    influxdb3_local.error(
                        f"[{task_id}] Invalid field mapping '{mapping}' in table '{table}': missing '@'"
                    )
                    raise Exception(
                        f"[{task_id}] Invalid field mapping '{mapping}' in table '{table}': missing '@'"
                    )
                old_field, new_field = mapping.split("@", 1)
                if not pattern.fullmatch(old_field):
                    influxdb3_local.error(
                        f"[{task_id}] Invalid old field name '{old_field}' in table '{table}'"
                    )
                    raise Exception(
                        f"[{task_id}] Invalid old field name '{old_field}' in table '{table}'"
                    )
                if not pattern.fullmatch(new_field):
                    influxdb3_local.error(
                        f"[{task_id}] Invalid new field name '{new_field}' in table '{table}'"
                    )
                    raise Exception(
                        f"[{task_id}] Invalid new field name '{new_field}' in table '{table}'"
                    )
                renames[old_field] = new_field

        table_renames[table] = renames

    return table_renames


def parse_max_retries(influxdb3_local, args: dict, task_id: str) -> int:
    """
    Parse and validate the 'max_retries' argument, converting it from string to int.

    Args:
        influxdb3_local: Logger for error messages.
        args (dict): Runtime arguments containing 'max_retries'.
        task_id (str): Unique task identifier for logging context.

    Returns:
        int: Parsed number of retries (>= 1).

    Raises:
        Exception: If 'max_retries' is missing, not an integer, or less than 1.
    """
    raw = args.get("max_retries", 3)
    try:
        max_retries = int(raw)
    except (TypeError, ValueError):
        influxdb3_local.error(
            f"[{task_id}] Invalid max_retries, not an integer: {raw!r}"
        )
        raise Exception(f"[{task_id}] Invalid max_retries, not an integer: {raw!r}")

    if max_retries < 1:
        influxdb3_local.error(
            f"[{task_id}] Invalid max_retries, must be >= 1: {max_retries}"
        )
        raise Exception(f"[{task_id}] Invalid max_retries, must be >= 1: {max_retries}")

    return max_retries


def parse_port_override(influxdb3_local, args: dict, task_id: str) -> int:
    """
    Parse and validate the 'port_override' argument, converting it from string to int.

    Args:
        influxdb3_local: Logger for error messages.
        args (dict): Runtime arguments containing 'port_override'.
        task_id (str): Unique task identifier for logging context.

    Returns:
        int | None: Parsed port number (1–65535), or 443 if not provided.

    Raises:
        Exception: If 'port_override' is provided but is not a valid integer in the range 1–65535.
    """
    raw = args.get("port_override", 443)

    try:
        port = int(raw)
    except (TypeError, ValueError):
        influxdb3_local.error(
            f"[{task_id}] Invalid port_override, not an integer: {raw!r}"
        )
        raise Exception(f"[{task_id}] Invalid port_override, not an integer: {raw!r}")

    # Validate port range
    if not (1 <= port <= 65535):
        influxdb3_local.error(
            f"[{task_id}] Invalid port_override, must be between 1 and 65535: {port}"
        )
        raise Exception(
            f"[{task_id}] Invalid port_override, must be between 1 and 65535: {port}"
        )

    return port


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


def process_writes(influxdb3_local, table_batches: list, args: dict | None = None):
    """
    Replicate incoming data rows to a remote InfluxDB 3 instance.

    Performs table filtering, field renaming, timestamp handling and manages a local queue to ensure reliable delivery.

    Args:
        influxdb3_local: Local InfluxDB 3-compatible client or logger.
        table_batches (list): List of dictionaries containing rows from WAL flush.
        args (dict, optional): Runtime config including remote host, token, database and options.

    Raises:
        Exception: Only internally, caught and logged; this method handles its own fault tolerance.
    """
    # Configuration
    try:
        plugin_dir = Path(__file__).parent
    except NameError:
        plugin_dir = Path(os.getenv("PLUGIN_DIR", os.path.expanduser("~/.plugins")))
    queue_file = plugin_dir / "edr_queue_writes.jsonl.gz"

    task_id = str(uuid.uuid4())
    influxdb3_local.info(
        f"[{task_id}] Starting data replication process, PLUGIN_DIR={plugin_dir}"
    )

    if not args or "host" not in args or "token" not in args or "database" not in args:
        influxdb3_local.error(
            f"[{task_id}] Missing required arguments: host, token, or database"
        )
        return

    remote_host: str = args["host"]
    if remote_host[0] == remote_host[-1] and remote_host[0] in ('"', "'"):
        remote_host = remote_host[1:-1]

    remote_token: str = args["token"]
    remote_db: str = args["database"]
    verify_ssl: bool = args.get("verify_ssl", "true").lower() == "true"
    port_override: int = parse_port_override(influxdb3_local, args, task_id)
    max_retries: int = parse_max_retries(influxdb3_local, args, task_id)

    tables_to_replicate: list | None = (
        args.get("tables").split(".") if args.get("tables") else None
    )
    max_size: int = args.get("max_size", 1024)
    excluded_fields: dict = parse_exclusions(influxdb3_local, args, task_id)
    tables_renames: dict = parse_table_renames(influxdb3_local, args, task_id)
    field_renames: dict = parse_field_renames(influxdb3_local, args, task_id)

    try:
        client = InfluxDBClient3(
            write_port_overwrite=port_override,
            host=remote_host,
            token=remote_token,
            database=remote_db,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        influxdb3_local.error(
            f"[{task_id}] Failed to initialize remote client: {str(e)}"
        )
        return

    lines_to_replicate: list = []

    for table_batch in table_batches:
        table_name: str = table_batch["table_name"]
        table_excluded_fields: list = excluded_fields.get(table_name, [])
        all_tags: list = get_tag_names(influxdb3_local, table_name, task_id)
        tables_fields_renames: dict = field_renames.get(table_name, {})
        table_name_: str = tables_renames.get(table_name, table_name)

        if tables_to_replicate and table_name not in tables_to_replicate:
            continue

        for row in table_batch["rows"]:
            line: str = row_to_line_protocol(
                influxdb3_local,
                table_name,
                table_name_,
                row,
                task_id,
                table_excluded_fields,
                tables_fields_renames,
                all_tags,
            )
            if line:
                lines_to_replicate.append({"table": table_name, "line": line})

    if lines_to_replicate:
        append_to_queue(
            influxdb3_local, queue_file, lines_to_replicate, max_size, task_id
        )
        influxdb3_local.info(
            f"[{task_id}] Queued {len(lines_to_replicate)} lines from {', '.join(set(p['table'] for p in lines_to_replicate))}"
        )

    queued_entries: list = read_queue(queue_file)
    if not queued_entries:
        influxdb3_local.info(f"[{task_id}] No data to replicate")
        return

    _flush_queue_with_retries(
        influxdb3_local, client, queue_file, queued_entries, task_id, max_retries
    )


def get_all_tables(influxdb3_local) -> list[str]:
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


def parse_offset(influxdb3_local, args: dict, task_id: str) -> timedelta:
    """
    Parses the 'offset' argument from args and converts it into a timedelta object.
    Used to shift the query time window backwards.

    Args:
        influxdb3_local: InfluxDB client instance for logging.
        args (dict): Dictionary with the 'offset' key (e.g., {"offset": "1h"}).
        task_id (str): Unique identifier for the current task, used for logging.

    Returns:
        timedelta: Parsed time delta. Returns zero if no offset is provided.

    Raises:
        Exception: If the format is invalid or the unit is unsupported.

    Example input:
        args = {"offset": "15min"}  # valid units: 's', 'min', 'h', 'd', 'w'
    """
    valid_units = {"s": "seconds", "min": "minutes", "h": "hours", "d": "days", "w": "weeks"}

    offset: str | None = args.get("offset", None)

    if offset is None:
        return timedelta(0)

    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", offset)
    if match:
        number, unit = match.groups()
        number = int(number)

        if number >= 1 and unit in valid_units:
            return timedelta(**{valid_units[unit]: number})

    influxdb3_local.error(f"[{task_id}] Invalid offset format: {offset}.")
    raise Exception(f"[{task_id}] Invalid offset format: {offset}.")


def parse_window(influxdb3_local, args: dict, task_id: str) -> timedelta:
    """
    Parses the 'window' argument from args and converts it into a timedelta object.
    Represents the size of the query window.

    Args:
        influxdb3_local: InfluxDB client instance for logging.
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


def build_query(measurement: str, time_from: datetime, time_to: datetime) -> str:
    """
    Builds a SQL query to select all data from a measurement between two timestamps.

    Args:
        measurement (str): Name of the measurement/table.
        time_from (datetime): Start time (inclusive).
        time_to (datetime): End time (exclusive).

    Returns:
        str: SQL query string selecting data between time_from and time_to.

    Example output:
        SELECT * FROM "cpu" WHERE time >= '2025-05-16T12:00:00Z' AND time < '2025-05-16T13:00:00Z'
    """
    # ISO timestamps
    start_iso = time_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = time_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    query = f"""
        SELECT
            *
        FROM
            "{measurement}"
        WHERE
            time >= '{start_iso}'
        AND 
            time < '{end_iso}'
    """
    return query


def process_scheduled_call(
    influxdb3_local, call_time: datetime, args: dict | None = None
):
    """
    Orchestrates a scheduled data replication from a local InfluxDB instance to a remote one.
    Fetches data using a time window and offset, applies renaming,
    and then writes to a remote InfluxDB3 instance via line protocol.

    Args:
        influxdb3_local: InfluxDB client instance (local).
        call_time (datetime): Time when the scheduled call was triggered.
        args (dict | None): Configuration parameters including:
            - host (str): Remote InfluxDB host.
            - token (str): Remote InfluxDB token.
            - database (str): Remote database name.
            - source_measurement (str): Measurement to replicate.
            - offset (str, optional): Time offset before call_time (e.g., '1h').
            - window (str): Size of the time window to replicate (e.g., '5min').
            - max_size (int, optional): Max batch size for queue.
            - field_renames / table_renames / exclusions (dicts): Transformation rules.
    """
    # Configuration
    try:
        plugin_dir = Path(__file__).parent
    except NameError:
        plugin_dir = Path(os.getenv("PLUGIN_DIR", os.path.expanduser("~/.plugins")))
    queue_file = plugin_dir / "edr_queue_schedule.jsonl.gz"

    task_id: str = str(uuid.uuid4())

    influxdb3_local.info(
        f"[{task_id}] Starting data replication process, PLUGIN_DIR={plugin_dir}"
    )

    if (
        not args
        or "host" not in args
        or "token" not in args
        or "database" not in args
        or "source_measurement" not in args
    ):
        influxdb3_local.error(
            f"[{task_id}] Missing required arguments: host, token, measurement, or database"
        )
        return

    remote_host: str = args["host"]
    if remote_host[0] == remote_host[-1] and remote_host[0] in ('"', "'"):
        remote_host = remote_host[1:-1]

    remote_token: str = args["token"]
    remote_db: str = args["database"]
    measurement: str = args["source_measurement"]
    verify_ssl: bool = args.get("verify_ssl", "true").lower() == "true"
    port_override: int = parse_port_override(influxdb3_local, args, task_id)
    max_retries: int = parse_max_retries(influxdb3_local, args, task_id)

    if measurement not in get_all_tables(influxdb3_local):
        influxdb3_local.error(
            f"[{task_id}] Measurement {measurement} not found in current database"
        )
        return

    max_size: int = args.get("max_size", 1024)
    excluded_fields: dict = parse_exclusions(influxdb3_local, args, task_id)
    tables_renames: dict = parse_table_renames(influxdb3_local, args, task_id)
    field_renames: dict = parse_field_renames(influxdb3_local, args, task_id)
    offset: timedelta = parse_offset(influxdb3_local, args, task_id)
    window: timedelta = parse_window(influxdb3_local, args, task_id)
    call_time_: datetime = call_time.replace(tzinfo=timezone.utc)

    time_to: datetime = call_time_ - offset
    time_from: datetime = time_to - window

    query: str = build_query(measurement, time_from, time_to)
    data: list = influxdb3_local.query(query)

    table_excluded_fields: list = excluded_fields.get(measurement, [])
    table_fields_renames: dict = field_renames.get(measurement, {})
    all_tags: list = get_tag_names(influxdb3_local, measurement, task_id)
    table_name_: str = tables_renames.get(measurement, measurement)

    lines_to_replicate: list = []
    for row in data:
        line: str = row_to_line_protocol(
            influxdb3_local,
            measurement,
            table_name_,
            row,
            task_id,
            table_excluded_fields,
            table_fields_renames,
            all_tags,
        )
        if line:
            lines_to_replicate.append({"table": measurement, "line": line})

    try:
        client = InfluxDBClient3(
            write_port_overwrite=port_override,
            host=remote_host,
            token=remote_token,
            database=remote_db,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        influxdb3_local.error(
            f"[{task_id}] Failed to initialize remote client: {str(e)}"
        )
        return

    if lines_to_replicate:
        append_to_queue(
            influxdb3_local, queue_file, lines_to_replicate, max_size, task_id
        )
        influxdb3_local.info(
            f"[{task_id}] Queued {len(lines_to_replicate)} lines from {', '.join(set(p['table'] for p in lines_to_replicate))}"
        )

    queued_entries: list = read_queue(queue_file)

    if not queued_entries:
        influxdb3_local.info(f"[{task_id}] No data to replicate")
        return

    _flush_queue_with_retries(
        influxdb3_local, client, queue_file, queued_entries, task_id, max_retries
    )


def _flush_queue_with_retries(
    influxdb3_local,
    client,
    queue_file: Path,
    queued_entries: list,
    task_id: str,
    max_retries: int,
) -> None:
    """
    Attempt to write queued line‑protocol entries to remote InfluxDB with retries and queue truncation upon success.
    """
    for attempt in range(max_retries):
        try:
            lines: list = [entry["line"] for entry in queued_entries]
            client.write(lines)
            successful_entries: list = queued_entries
            influxdb3_local.info(
                f"[{task_id}] Replicated {len(successful_entries)} lines to remote instance"
            )

            truncate_queue(successful_entries, queue_file)
            break

        except InfluxDBError as e:
            if e.response and e.response.status == 429:
                retry_after = int(e.response.headers.get("retry-after", 2**attempt))
                influxdb3_local.info(
                    f"[{task_id}] Rate limit hit, retrying after {retry_after}s"
                )
                time.sleep(retry_after)
            else:
                influxdb3_local.error(
                    f"[{task_id}] Replication attempt {attempt + 1} failed: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                else:
                    influxdb3_local.error(
                        f"[{task_id}] Max retries reached; data remains in queue"
                    )
                    break

        except Exception as e:
            influxdb3_local.error(
                f"[{task_id}] Replication attempt {attempt + 1} failed: {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
            else:
                influxdb3_local.error(
                    f"[{task_id}] Max retries reached; data remains in queue"
                )
                break
