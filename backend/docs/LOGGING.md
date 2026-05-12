# Structured Logging Guide

## Overview

TraceWise uses structured logging to provide observability and debugging capabilities across the entire backend. Logs are formatted as JSON in production for easy parsing and aggregation, and as human-readable text during development.

## Basic Usage

### Getting a Logger

Use the `get_logger()` function to get a logger for your module:

```python
from app.logging import get_logger

logger = get_logger(__name__)
logger.info("Application started")
logger.warning("Cache not available")
logger.error("Database connection failed")
```

The logger name should typically be the module's `__name__`, which makes it easy to identify where log messages come from.

## Context Variables

Context variables allow you to attach metadata to logs that persists across async handlers. This is useful for tracking requests, cases, documents, and users throughout their lifecycle.

### Available Context Fields

| Field | Type | Usage | Example |
|-------|------|-------|---------|
| `request_id` | str | Unique identifier per HTTP request | `req-abc123` |
| `case_id` | str | Case being processed | `case-456` |
| `document_id` | str | Document being processed | `doc-789` |
| `user_id` | str | User performing the action | `user-101` |
| `session_id` | str | User session identifier | `sess-202` |

### Setting Context Variables

Use `set_context_var()` to set a context variable:

```python
from app.context import set_context_var, get_context_var

# Set the case_id when processing a case
set_context_var("case_id", "case-456")

# Later, in a different function or middleware:
case_id = get_context_var("case_id")  # Returns "case-456"
```

Context variables are automatically included in all logs:

```python
from app.logging import get_logger
from app.context import set_context_var

logger = get_logger(__name__)

set_context_var("case_id", "case-456")
logger.info("Processing case")

# Output (production JSON):
# {
#   "timestamp": "2026-05-12 10:30:45",
#   "level": "INFO",
#   "logger": "app.api.cases",
#   "message": "Processing case",
#   "case_id": "case-456"
# }
```

### Request ID Tracking (Automatic)

The `LoggingMiddleware` automatically generates or extracts a request ID for each HTTP request:

```python
# No setup needed—middleware handles this automatically
logger.info("Handling request")

# Output (production JSON):
# {
#   "timestamp": "2026-05-12 10:30:45",
#   "level": "INFO",
#   "logger": "app.api.cases",
#   "message": "Handling request",
#   "request_id": "uuid-abc-123-def"
# }
```

#### Custom Request IDs

To use a custom request ID instead of a generated UUID, include an `X-Request-ID` header in your HTTP request:

```bash
curl -H "X-Request-ID: my-custom-id-123" http://localhost:8000/api/cases
```

The middleware will use this value instead of generating a new UUID.

## Examples

### Example 1: Processing a Case with Context

```python
from app.logging import get_logger
from app.context import set_context_var

logger = get_logger(__name__)

async def process_case(case_id: str):
    set_context_var("case_id", case_id)
    
    logger.info("Processing case")
    
    # ... do work ...
    
    logger.info("Case processed successfully")
```

Both log messages will include `"case_id": "case-456"` in production.

### Example 2: Extracting Documents from a Case

```python
from app.logging import get_logger
from app.context import set_context_var, get_context_var

logger = get_logger(__name__)

async def extract_documents(case_id: str, document_id: str):
    set_context_var("case_id", case_id)
    set_context_var("document_id", document_id)
    
    logger.info("Starting extraction")
    
    try:
        # ... extraction logic ...
        logger.info("Extraction completed")
    except Exception as e:
        logger.error("Extraction failed", exc_info=True)
        raise
```

All logs will include both `case_id` and `document_id` for easy correlation.

### Example 3: Using Request ID

```python
from app.logging import get_logger
from app.context import get_context_var

logger = get_logger(__name__)

async def check_request_id():
    request_id = get_context_var("request_id")
    if request_id:
        logger.info(f"Processing request {request_id}")
```

## Environment-Specific Behavior

### Development Mode

In development, logs are formatted as human-readable text:

```
2026-05-12 10:30:45 - app.api.cases - INFO - Processing case
```

Context variables are not included in development logs for readability.

### Production Mode

In production, logs are formatted as JSON for easy parsing:

```json
{
  "timestamp": "2026-05-12 10:30:45",
  "level": "INFO",
  "logger": "app.api.cases",
  "message": "Processing case",
  "case_id": "case-456",
  "request_id": "uuid-abc-123"
}
```

Set the `ENVIRONMENT` variable to `production` to enable JSON formatting:

```bash
export ENVIRONMENT=production
python -m uvicorn app.main:app
```

## Configuration

Logging is configured in `app/config.py` via the `LOG_LEVEL` environment variable. The default is `INFO`.

```bash
# Set logging level
export LOG_LEVEL=DEBUG
export LOG_LEVEL=WARNING
```

Valid levels:
- `DEBUG`: Most verbose, includes all debug messages
- `INFO`: Normal operation
- `WARNING`: Warnings and errors only
- `ERROR`: Errors only
- `CRITICAL`: Critical errors only

## Best Practices

### 1. Use Structured Context for Correlation

Instead of embedding IDs in log messages, use context variables:

```python
# ❌ Don't do this
logger.info(f"Processing case {case_id}")

# ✅ Do this
set_context_var("case_id", case_id)
logger.info("Processing case")
```

### 2. Set Context Early in Request Lifecycle

Set context variables as early as possible, typically in route handlers or middleware:

```python
@router.post("/cases/{case_id}")
async def process_case(case_id: str):
    set_context_var("case_id", case_id)
    # ... rest of handler ...
```

### 3. Include Exception Information

When logging exceptions, use `exc_info=True` to include the full traceback:

```python
try:
    # ... code ...
except Exception:
    logger.error("Operation failed", exc_info=True)
    raise
```

### 4. Use Appropriate Log Levels

- `DEBUG`: Detailed information for diagnosing problems
- `INFO`: Confirmation that things are working as expected
- `WARNING`: Something unexpected happened (not an error)
- `ERROR`: A serious problem; something failed
- `CRITICAL`: A very serious problem; the system may not continue

### 5. Keep Messages Concise

Log messages should be short and descriptive:

```python
# ❌ Too verbose
logger.info("The system successfully processed the case with ID case-123 in 45 milliseconds")

# ✅ Concise
logger.info("Case processed")
```

The structured fields (case_id, request_id, etc.) provide context without cluttering the message.

## Accessing Logs

### Local Development

Logs are printed to stdout and can be viewed in the console:

```bash
python -m uvicorn app.main:app --reload
```

### Production

In production, logs are output as JSON. You can pipe them to a log aggregation service like:
- **CloudWatch**: Use CloudWatch Logs agent
- **ELK Stack**: Use Filebeat or Logstash
- **Datadog**: Use Datadog agent
- **Grafana Loki**: Use Promtail

### Filtering Logs

Example: Find all logs for a specific case:

```bash
cat app.log | jq 'select(.case_id == "case-456")'
```

Example: Find all errors with a request ID:

```bash
cat app.log | jq 'select(.level == "ERROR" and .request_id)'
```

## Troubleshooting

### Missing Context Fields

If context variables are not appearing in logs:

1. **In Development**: Context fields are not included in text logs by design. Switch to production mode to see them.
2. **Check the Middleware**: Ensure `LoggingMiddleware` is registered in `app/main.py`.
3. **Use `get_context_var()`**: Verify the context variable is set with `get_context_var("request_id")`.

### Context Leaking Between Requests

Context variables are automatically reset after each request. If you're seeing context from one request appear in another:

1. Ensure you're not manually setting context outside of request handlers
2. Check that exceptions in handlers are being caught properly
3. Review `app/middleware/logging_middleware.py` to ensure cleanup is happening

## API Reference

### `get_logger(name: str) -> logging.Logger`

Get a logger instance for a module.

**Parameters:**
- `name`: The logger name (typically `__name__`)

**Returns:** A `logging.Logger` instance

**Example:**
```python
logger = get_logger(__name__)
```

### `set_context_var(name: str, value: Any) -> None`

Set a context variable that will be included in all logs.

**Parameters:**
- `name`: The variable name (`request_id`, `case_id`, `document_id`, `user_id`, `session_id`)
- `value`: The value to set

**Raises:** `ValueError` if the variable name is unknown

**Example:**
```python
set_context_var("case_id", "case-456")
```

### `get_context_var(name: str) -> Optional[Any]`

Get a context variable value.

**Parameters:**
- `name`: The variable name

**Returns:** The value, or `None` if not set

**Raises:** `ValueError` if the variable name is unknown

**Example:**
```python
case_id = get_context_var("case_id")
```

### `reset_context() -> None`

Reset all context variables. This is called automatically by the middleware after each request.

**Example:**
```python
from app.context import reset_context
reset_context()
```

## See Also

- `app/logging.py`: Logging configuration
- `app/context.py`: Context variable management
- `app/middleware/logging_middleware.py`: Request logging middleware
- `app/config.py`: Application settings
