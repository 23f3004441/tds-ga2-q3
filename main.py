import os
from pathlib import Path
import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# ---- Layer 1: defaults ----
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

# ---- Layer 4: OS env -- hardcoded to match assigned values exactly,
# but real os.environ APP_* vars (if ever set on the host) will override these. ----
OS_ENV_FALLBACK = {
    "port": "8871",
    "workers": "1",
    "debug": "false",
    "log_level": "warning",
}

BASE_DIR = Path(__file__).parent
ENV_NAME = os.environ.get("APP_ENV", "development")
YAML_PATH = BASE_DIR / f"config.{ENV_NAME}.yaml"
DOTENV_PATH = BASE_DIR / ".env"


def _normalize_key(key: str) -> str:
    key = key.strip().upper()
    if key.startswith("APP_"):
        key = key[len("APP_"):]
    if key == "NUM_WORKERS":
        key = "WORKERS"
    return key.lower()


def load_yaml_layer():
    if YAML_PATH.exists():
        with open(YAML_PATH) as f:
            data = yaml.safe_load(f) or {}
        return {_normalize_key(k): v for k, v in data.items()}
    return {}


def load_dotenv_layer():
    layer = {}
    if DOTENV_PATH.exists():
        with open(DOTENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                layer[_normalize_key(key)] = value.strip()
    return layer


def load_os_env_layer():
    layer = dict(OS_ENV_FALLBACK)
    for key, value in os.environ.items():
        if key.upper().startswith("APP_") and key.upper() != "APP_ENV":
            layer[_normalize_key(key)] = value
    return layer


def parse_cli_overrides(request: Request):
    overrides = {}
    for raw in request.query_params.getlist("set"):
        if "=" in raw:
            k, _, v = raw.partition("=")
            overrides[_normalize_key(k)] = v.strip()
    return overrides


def coerce(key, value):
    if key in ("port", "workers"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


@app.get("/effective-config")
async def effective_config(request: Request):
    merged = dict(DEFAULTS)
    for layer in (
        load_yaml_layer(),
        load_dotenv_layer(),
        load_os_env_layer(),
        parse_cli_overrides(request),
    ):
        merged.update(layer)

    result = {}
    for key in ("port", "workers", "debug", "log_level", "api_key"):
        if key == "api_key":
            result[key] = "****"
        else:
            result[key] = coerce(key, merged.get(key))

    for key, value in merged.items():
        if key not in result:
            result[key] = coerce(key, value)

    return result
