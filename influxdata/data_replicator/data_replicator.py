"""
{
    "plugin_name": "Data Replicator",
    "plugin_type": ["scheduled", "onwrite"],
    "dependencies": ["influxdb3-python"],
    "required_plugins": [],
    "category": "Data Replication",
    "description": "This plugin replicates data from a local InfluxDB 3 instance to a remote InfluxDB 3 instance, supporting filtering, renaming, and reliable delivery via scheduler or data write triggers.",
    "docs_file_link": "https://github.com/influxdata/influxdb3_plugins/blob/main/influxdata/data_replicator/README.md",
    "scheduled_args_config": [
        {
            "name": "host",
            "example": "https://remote-influxdb.com:8181",
            "description": "Remote InfluxDB host URL.",
            "required": true
        },
        {
            "name": "token",
            "example": "remote_api_token",
            "description": "Remote InfluxDB API token.",
            "required": true
        },
        {
            "name": "database",
            "example": "remote_db",
            "description": "Remote database name.",
            "required": true
        },
        {
            "name": "source_measurement",
            "example": "table1",
            "description": "The name of the measurement to replicate.",
            "required": true
        },
        {
            "name": "window",
            "example": "10s",
            "description": "Time window for each replication job (e.g., '1h', '1d'). Units: 's', 'min', 'h', 'd', 'w'.",
            "required": true
        },
        {
            "name": "unique_file_suffix",
            "example": "suffix123",
            "description": "Unique suffix for the queue file to avoid conflicts.",
            "required": true
        },
        {
            "name": "max_size",
            "example": "1024",
            "description": "Maximum size for the queue file in MB.",
            "required": false
        },
        {
            "name": "verify_ssl",
            "example": "true",
            "description": "Whether to verify SSL certificates when connecting via HTTPS.",
            "required": false
        },
        {
            "name": "max_retries",
            "example": "3",
            "description": "Maximum number of retries for write operations.",
            "required": false
        },
        {
            "name": "excluded_fields",
            "example": "field1.field2",
            "description": "Dot-separated list of fields to exclude from the source measurement (e.g., 'field1.field2').",
            "required": false
        },
        {
            "name": "target_table",
            "example": "new_table_name",
            "description": "New name for the measurement in the remote database. Defaults to source_measurement.",
            "required": false
        },
        {
            "name": "field_renames",
            "example": "hum:humidity.temp:temperature",
            "description": "Field renames for the source measurement in the format 'old1:new1.old2:new2'.",
            "required": false
        },
        {
            "name": "offset",
            "example": "10min",
            "description": "Time offset to apply to the window (e.g., '10min', '1h'). Units: 's', 'min', 'h', 'd', 'w'.",
            "required": false
        }
    ],
    "onwrite_args_config": [
        {
            "name": "host",
            "example": "https://remote-influxdb.com:8181",
            "description": "Remote InfluxDB host URL.",
            "required": true
        },
        {
            "name": "token",
            "example": "remote_api_token",
            "description": "Remote InfluxDB API token.",
            "required": true
        },
        {
            "name": "database",
            "example": "remote_db",
            "description": "Remote database name.",
            "required": true
        },
        {
            "name": "unique_file_suffix",
            "example": "suffix123",
            "description": "Unique suffix for the queue file to avoid conflicts.",
            "required": true
        },
        {
            "name": "tables",
            "example": "table1 table2",
            "description": "Space-separated list of tables to replicate. If not provided, all tables are replicated.",
            "required": false
        },
        {
            "name": "verify_ssl",
            "example": "true",
            "description": "Whether to verify SSL certificates when connecting via HTTPS.",
            "required": false
        },
        {
            "name": "port_override",
            "example": "8181",
            "description": "Override the default write port.",
            "required": false
        },
        {
            "name": "max_retries",
            "example": "3",
            "description": "Maximum number of retries for write operations.",
            "required": false
        },
        {
            "name": "max_size",
            "example": "1024",
            "description": "Maximum size for the queue file in MB.",
            "required": false
        },
        {
            "name": "excluded_fields",
            "example": "table1:field1@field2.table2:field3",
            "description": "String defining fields to exclude per table (e.g., '<table1>:<field1>@<field2>.<table2>:<field3>').",
            "required": false
        },
        {
            "name": "tables_rename",
            "example": "table1:new_table1.table2:new_table2",
            "description": "String defining table renames (e.g., '<old_table1>:<new_table1>.<old_table2>:<new_table2>').",
            "required": false
        },
        {
            "name": "field_renames",
            "example": "table1:hum@humidity temp@temperature.table2:oldX@newX",
            "description": "String defining field renames per table (e.g., 'table1:oldA@newA oldB@newB.table2:oldX@newX').",
            "required": false
        }
    ]
}
"""

import gzip
import json
import os
import re
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from influxdb_client_3 import InfluxDBClient3, InfluxDBError


def ensure_queue_file(queue_file: Path) -> None:
    """Ensure the queue file directory exists."""
    if not queue_file.parent.exists():
        queue_file.parent.mkdir(parents=True)


def append_to_queue(
    queue_file: Path, entries: list, max_size: int, task_id: str
) -> None:
    """
    Append serialized entries to a compressed JSONL queue file.

    Args:
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
    all_entries: list = read_queue(queue_file)
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
    table_fields_renames: dict,
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
        table_fields_renames (dict, optional): Mapping of field renames for this table.
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
    tags: dict = {
        table_fields_renames.get(k, k): str(v)
        for k, v in row.items()
        if k != "time"
        and v is not None
        and not isinstance(v, (int, float, bool))
        and k not in excluded_fields
        and k in all_tags
    }
    fields: dict = {
        table_fields_renames.get(k, k): v
        for k, v in row.items()
        if k != "time"
        and v is not None
        and isinstance(v, (int, float, bool))
        and k not in excluded_fields
    }
    string_fields: dict = {
        table_fields_renames.get(k, k): str(v)
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
    field_pairs: list = []
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

    field_str: str = ",".join(field_pairs)

    # Construct line protocol with the custom timestamp
    return f"{new_table_name}{tag_str} {field_str} {row['time']}"


def parse_exclusions_for_data_writes(args: dict, task_id: str) -> dict[str, list[str]]:
    """
    Parse a string defining fields to exclude or fields with str type from replication per table.

    Args:
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
            raise Exception(f"[{task_id}] Invalid segment '{block}': missing ':'")

        table, fields_raw = block.split(":", 1)

        if not pattern.fullmatch(table):
            raise Exception(f"[{task_id}] Invalid table name '{table}'")

        if not fields_raw:
            exclusions[table] = []
            continue

        fields: list = []
        for field in fields_raw.split("@"):
            if not pattern.fullmatch(field):
                raise Exception(
                    f"[{task_id}] Invalid field name '{field}' in table '{table}'"
                )
            fields.append(field)

        exclusions[table] = fields

    return exclusions


def parse_exclusions_for_schedule(args: dict) -> list[str]:
    """
    Parse a string defining fields to exclude.

    Args:
        args (dict): Dictionary of runtime arguments. Should contain the 'excluded_fields' key
                     in the format <field1>.<field2>.<field3>..."

    Returns:
        list[str]: list of field names to exclude.
    """
    return [field for field in args.get("excluded_fields", "").split(".") if field]


def parse_table_renames(args: dict, task_id: str) -> dict[str, str]:
    """
    Parse table renaming rules from a dot-separated string.

    Args:
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
    renames: dict = {}

    pairs: list = mapping_str.split(".")
    for pair in pairs:
        if ":" not in pair:
            raise Exception(f"[{task_id}] Invalid mapping pair: '{pair}' (missing ':')")

        old, new = pair.split(":", 1)

        if not valid_name.match(old):
            raise Exception(f"[{task_id}] Invalid table name: '{old}'")
        if not valid_name.match(new):
            raise Exception(f"[{task_id}] Invalid table name: '{new}'")

        renames[old] = new

    return renames


def parse_field_renames_for_data_writes(
    args: dict, task_id: str
) -> dict[str, dict[str, str]]:
    """
    Parse a complex mapping string for renaming fields in specific tables.

    Format example:
        "table1:oldA@newA oldB@newB.table2:oldX@newX oldY@newY"

    Args:
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

    table_renames: dict = {}
    for table_block in mapping_str.split("."):
        table_block = table_block.strip()
        if not table_block:
            continue  # skip empty blocks

        if ":" not in table_block:
            raise Exception(f"[{task_id}] Invalid segment '{table_block}': missing ':'")

        table, fields_part = table_block.split(":", 1)
        if not pattern.fullmatch(table):
            raise Exception(f"[{task_id}] Invalid table name '{table}'")

        # initialize inner mapping
        renames: dict = {}

        if fields_part:
            # split individual old@new mappings
            for mapping in fields_part.split(" "):
                if "@" not in mapping:
                    raise Exception(
                        f"[{task_id}] Invalid field mapping '{mapping}' in table '{table}': missing '@'"
                    )
                old_field, new_field = mapping.split("@", 1)
                if not pattern.fullmatch(old_field):
                    raise Exception(
                        f"[{task_id}] Invalid old field name '{old_field}' in table '{table}'"
                    )
                if not pattern.fullmatch(new_field):
                    raise Exception(
                        f"[{task_id}] Invalid new field name '{new_field}' in table '{table}'"
                    )
                renames[old_field] = new_field

        table_renames[table] = renames

    return table_renames


def parse_field_renames_for_schedule(args: dict, task_id: str) -> dict[str, str]:
    """
    Parse a complex mapping string for renaming fields.

    Format example:
        "oldA:newA.oldB:newB"

    Args:
        args (dict): Arguments containing the 'field_renames' key.
        task_id (str): Task identifier for logs.

    Returns:
        dict[str, str]: Dict mapping old to new name.
    """
    mapping_str: str = args.get("field_renames", "")
    pattern: re.Pattern = re.compile(r"^[A-Za-z0-9_-]+$")
    field_renames: dict = {}

    for table_block in mapping_str.split("."):
        if not table_block:
            continue  # skip empty blocks

        if ":" not in table_block:
            raise Exception(f"[{task_id}] Invalid segment '{table_block}': missing ':'")

        old_field, new_field = table_block.split(":", 1)
        if not pattern.fullmatch(new_field):
            raise Exception(f"[{task_id}] Invalid new field name '{new_field}'")

        field_renames[old_field] = new_field

    return field_renames


def parse_max_retries(args: dict, task_id: str) -> int:
    """
    Parse and validate the 'max_retries' argument, converting it from string to int.

    Args:
        args (dict): Runtime arguments containing 'max_retries'.
        task_id (str): Unique task identifier for logging context.

    Returns:
        int: Parsed number of retries (>= 1).

    Raises:
        Exception: If 'max_retries' is missing, not an integer, or less than 1.
    """
    raw: str | int = args.get("max_retries", 3)
    try:
        max_retries = int(raw)
    except (TypeError, ValueError):
        raise Exception(f"[{task_id}] Invalid max_retries, not an integer: {raw!r}")

    if max_retries < 1:
        raise Exception(f"[{task_id}] Invalid max_retries, must be >= 1: {max_retries}")

    return max_retries


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


def parse_host(raw: str, task_id: str) -> tuple[str, int]:
    """
    Parses a host string and returns a tuple (base_url, port).

    Args:
        raw (str): The host string, potentially quoted or missing scheme/port.
        task_id (str): Unique task identifier for logging context.

    Returns:
        tuple[str, int]: A tuple where the first element is the base URL
                         (e.g., "http://123.12.12.1" or "https://example.com")
                         and the second element is the port as an integer.

    Behavior:
        - Strips surrounding quotes (single or double) if present.
        - If no scheme (http or https) is specified, defaults to "http".
        - If no port is specified, defaults to 8181.
        - Supports IPv4, domain names, and IPv6 (with or without brackets).
    Raises:
        ValueError: If the hostname cannot be determined.
    """
    host = raw.strip()
    # Remove surrounding quotes if present
    if len(host) >= 2 and host[0] == host[-1] and host[0] in ('"', "'"):
        host = host[1:-1].strip()

    # Prepend default scheme if missing
    if not host.startswith(("http://", "https://")):
        host_with_scheme: str = "http://" + host
    else:
        host_with_scheme = host

    parsed = urllib.parse.urlparse(host_with_scheme)
    scheme: str = parsed.scheme or "http"
    hostname: str = parsed.hostname
    if not hostname:
        raise ValueError(
            f"[{task_id}] Invalid host string: '{raw}'. No hostname found."
        )

    # Determine port, defaulting to 8181 if not specified
    port: int = parsed.port or 8181

    # Reconstruct base URL, handling IPv6 hostnames with brackets if needed
    if ":" in hostname:  # crude check for IPv6
        base = f"{scheme}://[{hostname}]"
    else:
        base = f"{scheme}://{hostname}"

    return base, port


def _flush_queue_with_retries(
    influxdb3_local,
    client,
    queue_file: Path,
    queued_entries: list,
    task_id: str,
    max_retries: int,
    remote_host: str,
    remote_port: int,
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
                    f"[{task_id}] Replication attempt {attempt + 1}  to {remote_host}:{remote_port} failed: {e}"
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
                f"[{task_id}] Replication attempt {attempt + 1} to {remote_host}:{remote_port} failed: {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
            else:
                influxdb3_local.error(
                    f"[{task_id}] Max retries reached; data remains in queue"
                )
                break


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
    task_id = str(uuid.uuid4())

    # Validate required arguments
    required_keys: list = [
        "host",
        "token",
        "database",
        "unique_file_suffix",
    ]
    if not args or any(key not in args for key in required_keys):
        influxdb3_local.error(
            f"[{task_id}] Missing some of the required arguments: {', '.join(required_keys)}"
        )
        return

    try:
        # Configuration
        try:
            plugin_dir = Path(__file__).parent
        except NameError:
            plugin_dir = Path(os.getenv("PLUGIN_DIR", os.path.expanduser("~/.plugins")))
        unique_file_suffix: str = args["unique_file_suffix"]
        queue_file = plugin_dir / f"edr_queue_writes_{unique_file_suffix}.jsonl.gz"
        influxdb3_local.info(
            f"[{task_id}] Starting data replication process, PLUGIN_DIR={plugin_dir}"
        )

        remote_host, remote_port = parse_host(args["host"], task_id)
        remote_token: str = args["token"]
        remote_db: str = args["database"]
        verify_ssl: bool = args.get("verify_ssl", "true").lower() == "true"
        max_retries: int = parse_max_retries(args, task_id)

        tables_to_replicate: list | None = (
            args.get("tables").split(" ") if args.get("tables") else None
        )
        max_size: int = args.get("max_size", 1024)
        excluded_fields: dict = parse_exclusions_for_data_writes(args, task_id)
        tables_renames: dict = parse_table_renames(args, task_id)
        field_renames: dict = parse_field_renames_for_data_writes(args, task_id)

        try:
            client = InfluxDBClient3(
                write_port_overwrite=remote_port,
                host=remote_host,
                token=remote_token,
                database=remote_db,
                verify_ssl=verify_ssl,
            )
        except Exception as e:
            influxdb3_local.error(
                f"[{task_id}] Failed to initialize remote client to {remote_host}:{remote_port} with error: {str(e)}"
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
            append_to_queue(queue_file, lines_to_replicate, max_size, task_id)
            influxdb3_local.info(
                f"[{task_id}] Queued {len(lines_to_replicate)} lines from {', '.join(set(p['table'] for p in lines_to_replicate))}"
            )

        queued_entries: list = read_queue(queue_file)
        if not queued_entries:
            influxdb3_local.info(f"[{task_id}] No data to replicate")
            return

        _flush_queue_with_retries(
            influxdb3_local,
            client,
            queue_file,
            queued_entries,
            task_id,
            max_retries,
            remote_host,
            remote_port,
        )

    except Exception as e:
        influxdb3_local.error(str(e))


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


def parse_offset(args: dict, task_id: str) -> timedelta:
    """
    Parses the 'offset' argument from args and converts it into a timedelta object.
    Used to shift the query time window backwards.

    Args:
        args (dict): Dictionary with the 'offset' key (e.g., {"offset": "1h"}).
        task_id (str): Unique identifier for the current task, used for logging.

    Returns:
        timedelta: Parsed time delta. Returns zero if no offset is provided.

    Raises:
        Exception: If the format is invalid or the unit is unsupported.

    Example input:
        args = {"offset": "15min"}  # valid units: 's', 'min', 'h', 'd', 'w'
    """
    valid_units = {
        "s": "seconds",
        "min": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }

    offset: str | None = args.get("offset", None)

    if offset is None:
        return timedelta(0)

    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", offset)
    if match:
        number, unit = match.groups()
        number = int(number)

        if number >= 1 and unit in valid_units:
            return timedelta(**{valid_units[unit]: number})

    raise Exception(f"[{task_id}] Invalid offset format: {offset}.")


def parse_window(args: dict, task_id: str) -> timedelta:
    """
    Parses the 'window' argument from args and converts it into a timedelta object.
    Represents the size of the query window.

    Args:
        args (dict): Dictionary with the 'window' key (e.g., {"window": "2h"}).
        task_id (str): Unique identifier for the current task, used for logging.

    Returns:
        timedelta: Parsed time delta for the window.

    Raises:
        Exception: If the window has an invalid format or unit.

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

    window: str = args["window"]
    match = re.fullmatch(r"(\d+)([a-zA-Z]+)", window)

    if match:
        number, unit = match.groups()
        number = int(number)

        if number >= 1 and unit in valid_units:
            return timedelta(**{valid_units[unit]: number})

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
    Handles a scheduled data replication process from a local InfluxDB database
    to a remote InfluxDB3-compatible instance using parameters provided via `args`.

    Args:
        influxdb3_local: An object providing logging and querying capabilities to the local InfluxDB.
        call_time (datetime): The scheduled time of execution (UTC-aware will be enforced).
        args (dict | None): A dictionary of required and optional parameters, including:
            Required:
                - host (str): Remote host address, possibly with port (e.g., "example.com:8086").
                - token (str): Authorization token for remote InfluxDB.
                - database (str): Remote database name.
                - window (str or int): Duration of time window to pull data for (e.g., "5m", 300).
                - source_measurement (str): Measurement name in local DB to replicate from.
                - unique_file_suffix (str): Unique suffix used to construct the queue file name.
            Optional:
                - verify_ssl (str): "true" or "false", whether to verify SSL certificates (default: "true").
                - max_retries (int): Maximum number of retry attempts when flushing queue (default handled separately).
                - max_size (int): Maximum size of queue file before flushing (default: 1024).
                - excluded_fields (list): List of fields to exclude during replication.
                - target_table (str): Target measurement name in remote DB (defaults to `source_measurement`).
                - field_renames (dict): Mapping of field names to rename during replication.
                - offset (str or int): How far back from `call_time` the window should end (e.g., "1m", 60).

    Raises:
        No exceptions are propagated; all exceptions are caught and logged internally.

    Notes:
        - The function uses a queueing mechanism to ensure data durability in case of temporary failures.
        - The data is only flushed from the queue once a threshold is reached or retries are exhausted.
        - Queue is stored as a compressed JSONL file using the `unique_file_suffix` to differentiate tasks.
    """
    task_id: str = str(uuid.uuid4())

    # Validate required arguments
    required_keys: list = [
        "host",
        "token",
        "database",
        "window",
        "source_measurement",
        "unique_file_suffix",
    ]
    if not args or any(key not in args for key in required_keys):
        influxdb3_local.error(
            f"[{task_id}] Missing some of the required arguments: {', '.join(required_keys)}"
        )
        return

    try:
        # Configuration
        try:
            plugin_dir = Path(__file__).parent
        except NameError:
            plugin_dir = Path(os.getenv("PLUGIN_DIR", os.path.expanduser("~/.plugins")))
        unique_file_suffix: str = args["unique_file_suffix"]
        queue_file = plugin_dir / f"edr_queue_schedule_{unique_file_suffix}.jsonl.gz"
        influxdb3_local.info(
            f"[{task_id}] Starting data replication process, PLUGIN_DIR={plugin_dir}"
        )

        remote_host, remote_port = parse_host(args["host"], task_id)
        remote_token: str = args["token"]
        remote_db: str = args["database"]
        measurement: str = args["source_measurement"]
        verify_ssl: bool = args.get("verify_ssl", "true").lower() == "true"
        max_retries: int = parse_max_retries(args, task_id)

        if measurement not in get_all_tables(influxdb3_local):
            influxdb3_local.error(
                f"[{task_id}] Measurement {measurement} not found in current database"
            )
            return

        max_size: int = args.get("max_size", 1024)
        excluded_fields: list = parse_exclusions_for_schedule(args)
        target_table: str = args.get("target_table", measurement)
        field_renames: dict = parse_field_renames_for_schedule(args, task_id)
        offset: timedelta = parse_offset(args, task_id)
        window: timedelta = parse_window(args, task_id)
        call_time_: datetime = call_time.replace(tzinfo=timezone.utc)

        time_to: datetime = call_time_ - offset
        time_from: datetime = time_to - window

        query: str = build_query(measurement, time_from, time_to)
        data: list = influxdb3_local.query(query)

        all_tags: list = get_tag_names(influxdb3_local, measurement, task_id)

        lines_to_replicate: list = []
        for row in data:
            line: str = row_to_line_protocol(
                influxdb3_local,
                measurement,
                target_table,
                row,
                task_id,
                excluded_fields,
                field_renames,
                all_tags,
            )
            if line:
                lines_to_replicate.append({"table": measurement, "line": line})

        try:
            client = InfluxDBClient3(
                write_port_overwrite=remote_port,
                host=remote_host,
                token=remote_token,
                database=remote_db,
                verify_ssl=verify_ssl,
            )
        except Exception as e:
            influxdb3_local.error(
                f"[{task_id}] Failed to initialize remote client to {remote_host}:{remote_port} with error: {str(e)}"
            )
            return

        if lines_to_replicate:
            append_to_queue(queue_file, lines_to_replicate, max_size, task_id)
            influxdb3_local.info(
                f"[{task_id}] Queued {len(lines_to_replicate)} lines from {', '.join(set(p['table'] for p in lines_to_replicate))}"
            )

        queued_entries: list = read_queue(queue_file)

        if not queued_entries:
            influxdb3_local.info(f"[{task_id}] No data to replicate")
            return

        _flush_queue_with_retries(
            influxdb3_local,
            client,
            queue_file,
            queued_entries,
            task_id,
            max_retries,
            remote_host,
            remote_port,
        )

    except Exception as e:
        influxdb3_local.error(str(e))
