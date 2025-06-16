# Notification Sender Plugin for InfluxDB 3

This plugin is designed to send notifications through various channels (Slack, Discord, HTTP, SMS, WhatsApp) based on incoming HTTP requests. A standalone notification dispatcher, receiving data from other plugins or external systems and sending notifications accordingly.

## Prerequisites
- **InfluxDB v3 Core/Enterprise**: Latest version.
- **Python**: Version 3.10 or higher.

## Files
- `notifier_plugin.py`: The main plugin code for handling notification requests.

## Features
- **Multi-Channel Notifications**: Supports Slack, Discord, HTTP (POST), SMS, and WhatsApp.
- **Asynchronous Sending**: Slack, Discord, and HTTP notifications are sent with retry logic.
- **Synchronous Sending**: SMS and WhatsApp notifications are sent via Twilio with retry logic.
- **Retry Logic**: Retries failed notifications with exponential backoff (up to 3 attempts).
- **Environment Variable Support**: Uses environment variables for sensitive data like Twilio credentials.

## Setup & Run

### 1. Install & Run InfluxDB v3 Core/Enterprise
- Download and install InfluxDB v3 Core/Enterprise.
- Ensure the `plugins` directory exists; if not, create it:
  ```bash
  mkdir ~/.plugins
  ```
- Place `notifier_plugin.py` in `~/.plugins/`.
- Start InfluxDB 3 with the correct paths:
  ```bash
  influxdb3 serve --node-id node0 --object-store file --data-dir ~/.influxdb3 --plugin-dir ~/.plugins
  ```

### 2. Install Required Python Packages
The plugin requires the following Python packages:
- `httpx`: For asynchronous HTTP requests.
- `twilio`: For SMS and WhatsApp notifications.

Install them using:
```bash
influxdb3 install package httpx
influxdb3 install package twilio
```

## Configuration & Usage

### HTTP Plugin
The plugin processes incoming HTTP POST requests to send notifications. It is triggered by requests to a specified endpoint, which must be registered in InfluxDB.

#### Trigger Creation
Create an HTTP trigger using the `influxdb3 create trigger` command:
```bash
influxdb3 create trigger \
  --database mydb \
  --plugin-filename notifier_plugin.py \
  --trigger-spec "request:notify" \
  notification_trigger
```
This registers an HTTP endpoint at `/api/v3/engine/notify`.

#### Enable Trigger
Enable the trigger to start processing requests:
```bash
influxdb3 enable trigger --database mydb notification_trigger
```

#### Request Body Arguments
The plugin expects a JSON body with the following structure:

| Argument              | Description                                                                 | Required | Example                           |
|-----------------------|-----------------------------------------------------------------------------|----------|-----------------------------------|
| `notification_text`   | The text of the notification message.                                       | Yes      | `"Test alert"`                    |
| `senders_config`      | Configuration for each sender, including sender-specific arguments.         | Yes      | See below                         |

- **senders_config**: A dictionary where keys are sender names (`slack`, `discord`, `http`, `sms`, `whatsapp`), and values are their configurations.

#### Sender-Specific Configurations in `senders_config`
- **Slack**:
  - `slack_webhook_url` (string): Webhook URL for Slack.
  - `slack_headers` (string, optional): Base64-encoded headers (e.g., `{"Authorization": "Bearer ..."}` encoded in base64).
- **Discord**:
  - `discord_webhook_url` (string): Webhook URL for Discord.
  - `discord_headers` (string, optional): Base64-encoded headers.
- **HTTP**:
  - `http_webhook_url` (string): Custom webhook URL for HTTP POST requests.
  - `http_headers` (string, optional): Base64-encoded headers.
  - Note: Sends a POST request with `{"message": "notification_text"}` as the body.
- **SMS** (via Twilio):
  - `twilio_sid` (string): Twilio Account SID (or use `TWILIO_SID` env variable).
  - `twilio_token` (string): Twilio Auth Token (or use `TWILIO_TOKEN` env variable).
  - `twilio_from_number` (string): Sender phone number (e.g., `+1234567890`).
  - `twilio_to_number` (string): Recipient phone number (e.g., `+0987654321`).
- **WhatsApp** (via Twilio):
  - `twilio_sid` (string): Twilio Account SID (or use `TWILIO_SID` env variable).
  - `twilio_token` (string): Twilio Auth Token (or use `TWILIO_TOKEN` env variable).
  - `twilio_from_number` (string): Sender WhatsApp number (e.g., `+1234567890`).
  - `twilio_to_number` (string): Recipient WhatsApp number (e.g., `+0987654321`).

#### Example HTTP Requests
- **Sending a Slack Notification**:
  ```bash
  curl -X POST http://localhost:8181/api/v3/engine/notify \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -d '{
      "notification_text": "Test alert",
      "senders_config": {
        "slack": {
          "slack_webhook_url": "https://hooks.slack.com/services/..."
        }
      }
    }'
  ```

- **Sending an SMS via Twilio**:
  ```bash
  curl -X POST http://localhost:8181/api/v3/engine/notify \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -d '{
      "notification_text": "Test SMS",
      "senders_config": {
        "sms": {
          "twilio_sid": "your_sid",
          "twilio_token": "your_token",
          "twilio_from_number": "+1234567890",
          "twilio_to_number": "+0987654321"
        }
      }
    }'
  ```

- **Sending Multiple Notifications (Slack + WhatsApp)**:
  ```bash
  curl -X POST http://localhost:8181/api/v3/engine/notify \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -d '{
      "notification_text": "Multi-channel alert",
      "senders_config": {
        "slack": {
          "slack_webhook_url": "https://hooks.slack.com/services/..."
        },
        "whatsapp": {
          "twilio_sid": "your_sid",
          "twilio_token": "your_token",
          "twilio_from_number": "+1234567890",
          "twilio_to_number": "+0987654321"
        }
      }
    }'
  ```

## Important Notes
- **Environment Variables**: For security, Twilio credentials can be set via environment variables (`TWILIO_SID`, `TWILIO_TOKEN`), which take precedence over request parameters.
- **Retries**: The plugin retries failed notifications up to 3 times with exponential backoff for asynchronous senders (Slack, Discord, HTTP) and random delays for synchronous senders (SMS, WhatsApp).
- **Logging**: Logs are stored in the `_internal` database (or the database where the trigger is created) in the `system.processing_engine_logs` table. To view logs, use the following query::
  ```bash
  influxdb3 query --database _internal "SELECT * FROM system.processing_engine_logs"
  ```
- **Error Handling**: Invalid senders or missing configurations are logged as warnings or errors, and the plugin returns a result dictionary indicating success or failure for each sender.

## Questions/Comments
For support, open a GitHub issue or contact us via [Discord](https://discord.com/invite/vZe2w2Ds8B) in the `#influxdb3_core` channel, [Slack](https://influxcommunity.slack.com/) in the `#influxdb3_core` channel, or the [Community Forums](https://community.influxdata.com/).