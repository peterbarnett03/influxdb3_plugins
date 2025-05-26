import asyncio
import base64
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

import httpx
import requests
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

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
                break
            if "url" in key and not validate_webhook_url(
                influxdb3_local, sender, args[key], task_id
            ):
                break
            senders_config[sender][key] = args[key]

    if not senders_config:
        influxdb3_local.error(f"[{task_id}] No valid senders configured")
        raise Exception(f"[{task_id}] No valid senders configured")
    return senders_config


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
        <field><op><value>
    where <op> is one of: >, <, >=, <=, ==, !=
    Multiple conditions are separated by semicolons ':'.

    Args:
        influxdb3_local: InfluxDB client instance.
        args (dict): Input arguments containing "field_conditions".
        task_id (str): Unique task identifier.

    Returns:
        List of tuples: (field_name (str), operator_fn (callable), compare_value)

    Example:
        >>> parse_field_conditions("temp>30:status=='ok':count<=100")
        [
            ("temp", operator.gt, 30),
            ("status", operator.eq, "ok"),
            ("count", operator.le, 100)
        ]
    """
    cond_str: str | None = args.get("field_conditions", None)
    if not cond_str:
        influxdb3_local.error(
            f"[{task_id}] Missing required argument: field_conditions"
        )
        raise Exception(f"[{task_id}] Missing required argument: field_conditions")

    conditions: list = []
    # split on semicolons
    for part in cond_str.split(":"):
        part = part.strip()
        if not part:
            continue
        # find operator
        m = re.match(r"^([A-Za-z0-9_-]+)\s*(>=|<=|==|!=|>|<)\s*(.+)$", part)
        if not m:
            influxdb3_local.error(f"[{task_id}] Invalid condition format: '{part}'")
            raise Exception(f"[{task_id}] Invalid condition format: '{part}'")
        field, op, raw_val = m.groups()
        if op not in _OP_FUNCS:
            influxdb3_local.error(
                f"[{task_id}] Unsupported operator '{op}' in condition '{part}'"
            )
            raise Exception(
                f"[{task_id}] Unsupported operator '{op}' in condition '{part}'"
            )
        val = _coerce_value(raw_val)
        conditions.append((field, _OP_FUNCS[op], val))
    return conditions


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


def parse_port_override(influxdb3_local, args: dict, task_id: str) -> int:
    """
    Parse and validate the 'port_override' argument, converting it from string to int.

    Args:
        influxdb3_local: Logger for error messages.
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
        or "influxdb3_auth_token" not in args
    ):
        influxdb3_local.error(
            f"[{task_id}] Missing required arguments: measurement, field_conditions, influxdb3_auth_token, or senders"
        )
        return

    measurement: str = args["measurement"]
    all_measurements: list = get_all_measurements(influxdb3_local)
    if measurement not in all_measurements:
        influxdb3_local.error(
            f"[{task_id}] Measurement '{measurement}' not found in database"
        )
        return

    trigger_count: int = int(args.get("trigger_count", 1))
    senders_config: dict = parse_senders(influxdb3_local, args, task_id)
    field_conditions: list = parse_field_conditions(influxdb3_local, args, task_id)
    port_override: int = parse_port_override(influxdb3_local, args, task_id)
    notification_path: str = args.get("notification_path", "notify")
    influxdb3_auth_token: str = os.getenv(
        "INFLUXDB3_AUTH_TOKEN", args.get("influxdb3_auth_token")
    )
    notification_tpl = args.get(
        "notification_text",
        "InfluxDB 3 alert triggered. Condition $field $op_sym $compare_val matched ($actual)",
    )

    for table_batch in table_batches:
        table_name: str = table_batch["table_name"]
        if table_name != measurement:
            continue

        for row in table_batch["rows"]:
            for field, compare_fn, compare_val in field_conditions:
                if field not in row:
                    influxdb3_local.warn(
                        f"[{task_id}] Field '{field}' not found in row: {row}"
                    )
                    continue

                actual = row[field]
                if compare_fn(actual, compare_val):
                    cache_value = influxdb3_local.cache.get(f"{measurement}:{field}")
                    current_count = int(cache_value) if cache_value is not None else 0

                    # reconstruct operator symbol from function
                    op_sym = next(
                        sym for sym, fn in _OP_FUNCS.items() if fn is compare_fn
                    )

                    if current_count >= (trigger_count - 1):
                        notification_text = interpolate_notification_text(
                            notification_tpl,
                            {
                                "field": field,
                                "op_sym": op_sym,
                                "compare_val": compare_val,
                                "actual": actual,
                            },
                        )

                        payload: dict = {
                            "notification_text": notification_text,
                            "senders_config": senders_config,
                        }

                        influxdb3_local.error(
                            f"[{task_id}] Condition {field} {op_sym} {compare_val!r} matched {trigger_count} times \
                            ({actual!r}), sending alert"
                        )
                        send_notification(
                            influxdb3_local,
                            port_override,
                            notification_path,
                            influxdb3_auth_token,
                            payload,
                            task_id,
                        )
                        influxdb3_local.cache.put(f"{measurement}:{field}", "0")
                    else:
                        influxdb3_local.warn(
                            f"[{task_id}] Condition {field} {op_sym} {compare_val!r} matched ({actual!r}) for \
                            the {current_count}/{trigger_count} time. Skipping alert."
                        )
                        influxdb3_local.cache.put(
                            f"{measurement}:{field}", str(current_count + 1)
                        )


def send_sms_via_twilio(influxdb3_local, params: dict, task_id: str) -> bool:
    """
    Sends an SMS via the Twilio API.

    Args:
        influxdb3_local: InfluxDB client instance.
        params (dict): A dictionary containing the following keys:
            - twilio_sid (str): Your Twilio Account SID.
            - twilio_token (str): Your Twilio Auth Token.
            - twilio_from_number (str): Twilio phone number in E.164 format (e.g., "+1234567890").
            - twilio_to_number (str): Recipient phone number in E.164 format.
            - notification_text (str): Text content of the message.
        task_id (str): Unique task identifier.

    Raises:
        Exception: If there is a network error or authentication failure.
    """

    # Extract required parameters
    account_sid: str | None = os.getenv("TWILIO_SID", params.get("twilio_sid"))
    auth_token: str | None = os.getenv("TWILIO_TOKEN", params.get("twilio_token"))
    if not account_sid or not auth_token:
        influxdb3_local.error(f"[{task_id}] Missing Twilio credentials")
        return False

    from_number: str = params["twilio_from_number"]
    to_number: str = params["twilio_to_number"]
    notification_text: str = params["notification_text"]
    max_retries: int = 3

    for attempt in range(1, max_retries + 1):
        try:
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                to=to_number, from_=from_number, body=notification_text
            )
            influxdb3_local.info(f"[{task_id}] SMS sent! SID: {message.sid}")
            return True
        except TwilioRestException as e:
            influxdb3_local.warn(f"[{task_id}] Twilio error (attempt {attempt}): {e}")
        except Exception as e:
            influxdb3_local.warn(
                f"[{task_id}] Unexpected error (attempt {attempt}): {e}"
            )

        if attempt < max_retries:
            wait = random.uniform(1, 4)
            time.sleep(wait)

    influxdb3_local.error(
        f"[{task_id}] Failed to send SMS message after {max_retries} attempts."
    )
    return False


def send_whatsapp_via_twilio(influxdb3_local, params: dict, task_id: str) -> bool:
    """
    Sends a WhatsApp message via the Twilio API.

    Args:
        influxdb3_local: InfluxDB client instance.
        params (dict): A dictionary containing the following keys:
            - twilio_sid (str): Your Twilio Account SID.
            - twilio_token (str): Your Twilio Auth Token.
            - twilio_from_number (str): Twilio sandbox or approved WhatsApp number (e.g., "+1234567890").
            - twilio_to_number (str): Recipient WhatsApp number in E.164 format.
            - notification_text (str): Text content of the message.
        task_id (str): Unique task identifier.

    Returns:
        bool: True if message was sent successfully, False otherwise.
    """

    # Extract required parameters
    account_sid: str | None = os.getenv("TWILIO_SID", params.get("twilio_sid"))
    auth_token: str | None = os.getenv("TWILIO_TOKEN", params.get("twilio_token"))
    if not account_sid or not auth_token:
        influxdb3_local.error(f"[{task_id}] Missing Twilio credentials")
        return False

    from_number: str = f"whatsapp:{params['twilio_from_number']}"
    to_number: str = f"whatsapp:{params['twilio_to_number']}"
    body: str = params["notification_text"]
    max_retries: int = 3

    for attempt in range(1, max_retries + 1):
        try:
            client = Client(account_sid, auth_token)
            message = client.messages.create(to=to_number, from_=from_number, body=body)
            influxdb3_local.info(
                f"[{task_id}] WhatsApp message sent! SID: {message.sid}"
            )
            return True
        except TwilioRestException as e:
            influxdb3_local.warn(f"[{task_id}] Twilio error (attempt {attempt}): {e}")
        except Exception as e:
            influxdb3_local.warn(
                f"[{task_id}] Unexpected error (attempt {attempt}): {e}"
            )

        if attempt < max_retries:
            wait = random.uniform(1, 4)
            time.sleep(wait)

    influxdb3_local.error(
        f"[{task_id}] Failed to send WhatsApp message after {max_retries} attempts."
    )
    return False


def build_payload(endpoint_type: str, args: dict) -> dict:
    """
    Build notification payload based on endpoint type.

    Args:
        endpoint_type: Type of endpoint ('slack', 'discord', or 'http')
        args: Additional arguments for payload construction

    Returns:
        dict: Formatted payload for the specified endpoint
    """
    if endpoint_type == "http":
        return {"message": args["notification_text"]}

    payloads: dict = {
        "slack": {"text": args["notification_text"]},
        "discord": {"content": args["notification_text"]},
    }
    return payloads.get(endpoint_type, {"message": args["notification_text"]})


async def alert_async(
    influxdb3_local, endpoint_type: str, args: dict, task_id: str
) -> bool:
    """
    Send asynchronous alerts with retry logic.

    Args:
        influxdb3_local: InfluxDB client instance
        endpoint_type (str): Type of endpoint to send alert to
        args (dict): configuration arguments
        task_id (str: Unique task identifier
    """
    influxdb3_local.info(f"[{task_id}] Sending notification via {endpoint_type}")

    payload: dict = build_payload(endpoint_type, args)
    headers: dict = parse_headers(influxdb3_local, args, endpoint_type, task_id)
    max_retries: int = 3

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    args[f"{endpoint_type}_webhook_url"],
                    json=payload,
                    headers=headers,
                    timeout=10,
                )
                if response.status_code in [200, 204]:  # Discord returns 204 on success
                    influxdb3_local.info(
                        f"[{task_id}] Notification sent successfully via {endpoint_type}"
                    )
                    return True

                try:
                    response_data = await response.json()
                except Exception:
                    response_data = response.text

                influxdb3_local.info(
                    f"[{task_id}] Failed to send notification via {endpoint_type}, \
                    attempt {attempt + 1}/{max_retries}, \
                    response status code: {response.status_code}, \
                    response_data: {response_data}"
                )
            except Exception as e:
                influxdb3_local.error(f"[{task_id}] Request error: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
        influxdb3_local.error(
            f"[{task_id}] Max retries reached. Alert via {endpoint_type} not sent."
        )
        return False


def parse_headers(influxdb3_local, args: dict, key: str, task_id: str) -> dict:
    """
    Parse and validate headers from base64 encoded string.

    Args:
        influxdb3_local: InfluxDB client instance
        args (dict): Dictionary containing base64 encoded headers
        key (str): Key in args where headers are stored
        task_id (str): Unique task identifier

    Returns:
        dict: Decoded headers or empty dict if invalid
    """
    try:
        headers_b64: str = args.get(f"{key}_headers", "")
        if not headers_b64:
            return {}
        padding = len(headers_b64) % 4
        if padding:
            headers_b64 += "=" * (4 - padding)
        headers_json = base64.b64decode(headers_b64).decode("utf-8")
        decoded_headers = json.loads(headers_json)
        return decoded_headers
    except Exception:
        influxdb3_local.warn(f"[{task_id}] Failed to parse headers for {key}")
        return {}


def process_request(
    influxdb3_local, query_parameters, request_headers, request_body, args=None
):
    """
    Process an incoming HTTP request to trigger notifications via configured senders.
    """
    task_id = str(uuid.uuid4())

    # Process the request body
    if request_body:
        data: dict = json.loads(request_body)
    else:
        influxdb3_local.error(f"[{task_id}] No request body provided.")
        return {"status": "failed", "message": "No request body provided."}

    senders_functions: dict = {
        "slack": alert_async,
        "discord": alert_async,
        "http": alert_async,
        "whatsapp": send_whatsapp_via_twilio,
        "sms": send_sms_via_twilio,
    }

    results: dict = {}
    for sender, configs in data["senders_config"].items():
        configs["notification_text"] = data["notification_text"]

        if sender in senders_functions and sender in ["slack", "discord", "http"]:
            result: bool = asyncio.run(
                senders_functions[sender](influxdb3_local, sender, configs, task_id)
            )
        elif sender in senders_functions and sender in ["whatsapp", "sms"]:
            result: bool = senders_functions[sender](influxdb3_local, configs, task_id)
        else:
            influxdb3_local.warn(f"[{task_id}] Invalid sender: {sender}")
            result: str = f"Invalid sender"

        results[sender] = result

    return {"status": "success", "message": "Request processed", "results": results}


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
        LIMIT 1
    """
    return query


def process_scheduled_call(influxdb3_local, call_time: datetime, args: dict):
    """
    Check for recent data in a specified measurement and send a notification
    if data is missing for a configured number of consecutive checks.

    Args:
        influxdb3_local: InfluxDB client instance used for querying and logging.
        call_time (datetime): The current time of the scheduled check.
        args (dict): Configuration dictionary containing keys like
            "measurement", "senders", "influxdb3_auth_token", "window", and optional alert settings.
    """
    task_id = str(uuid.uuid4())
    # Configuration
    if (
        not args
        or "measurement" not in args
        or "senders" not in args
        or "influxdb3_auth_token" not in args
        or "window" not in args
    ):
        influxdb3_local.error(
            f"[{task_id}] Missing required arguments: measurement, senders, influxdb3_auth_token, or window"
        )
        return

    measurement: str = args["measurement"]
    all_measurements: list = get_all_measurements(influxdb3_local)
    if measurement not in all_measurements:
        influxdb3_local.error(
            f"[{task_id}] Measurement '{measurement}' not found in database"
        )
        return

    trigger_count: int = int(args.get("trigger_count", 1))
    senders_config: dict = parse_senders(influxdb3_local, args, task_id)
    port_override: int = parse_port_override(influxdb3_local, args, task_id)
    notification_path: str = args.get("notification_path", "notify")
    influxdb3_auth_token: str = os.getenv(
        "INFLUXDB3_AUTH_TOKEN", args.get("influxdb3_auth_token")
    )
    notification_tpl = args.get(
        "notification_text",
        "Deadman Alert: No data received from $table from $time_from to $time_to.",
    )

    window: timedelta = parse_window(influxdb3_local, args, task_id)
    time_to: datetime = call_time.replace(tzinfo=timezone.utc)
    time_from: datetime = time_to - window

    query = build_query(measurement, time_from, time_to)
    results = influxdb3_local.query(query)

    if results:
        influxdb3_local.info(
            f"[{task_id}] Data exists in '{measurement}' from {time_from} to {time_to}."
        )
        return

    cache_value = influxdb3_local.cache.get(measurement)
    current_count = int(cache_value) if cache_value is not None else 0

    if current_count >= (trigger_count - 1):
        influxdb3_local.error(
            f"[{task_id}] No data found in '{measurement}' from {time_from} to {time_to} for \
            {trigger_count} times. Sending alert."
        )

        notification_text = interpolate_notification_text(
            notification_tpl,
            {"table": measurement, "time_from": time_from, "time_to": time_to},
        )

        payload = {
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
            f"[{task_id}] No data found in '{measurement}' from {time_from} to {time_to} for \
            {current_count + 1}/{trigger_count} times. Skipping alert."
        )
        influxdb3_local.cache.put(measurement, str(current_count + 1))
