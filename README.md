# ChaccFileManager Module

A new ChaCC API module providing chacc file manager functionality.

## Environment Variables

This module uses environment variables from the main `.env` file at project root.
Use the naming convention: `{MODULE_NAME}_{VAR_NAME}` in uppercase.

For example, if your module is named `chacc_file_manager`:
```bash
# In .env file at project root
CHACC_FILE_MANAGER_API_KEY=your_api_key_here
CHACC_FILE_MANAGER_SECRET=your_secret_here
```

In your module code:
```python
from .context_factory import get_module_context

context = get_module_context()
api_key = context.get_module_config("API_KEY", "chacc_file_manager")  # Looks for CHACC_FILE_MANAGER_API_KEY
```

## Installation

This module is automatically loaded by the ChaCC backbone when it's placed in the `plugins/` directory.

## Development

### Testing

Run tests using pytest:

```bash
pytest tests/ -v
```

## Configuration

- `CHACC_ENV`: Set to `development`, `testing`, or `production`
- `CHACC_BACKBONE`: Set to `true` when running in ChaCC backbone

## API Endpoints

- `GET /chacc_file_manager/hello` - Health check endpoint

## Dependencies

- Python 3.12+
- FastAPI
- SQLAlchemy
- Pydantic

See `requirements.txt` for full dependencies.
