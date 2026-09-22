"""GPU-free, fail-closed configuration for explicitly selected AI services."""
from dataclasses import dataclass, field
import ipaddress
import math
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit


class AIError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def provider_from(env):
    provider = env.get('LLM_PROVIDER', 'openai').strip().lower()
    if provider not in ('openai', 'gemini', 'local'):
        raise AIError('misconfigured')
    return provider


def number(env, key, default, upper):
    try:
        value = float(env.get(key, default))
        if not math.isfinite(value) or not 0 < value <= upper:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise AIError('misconfigured') from None


def integer(env, key, default, upper):
    value = number(env, key, default, upper)
    if not value.is_integer():
        raise AIError('misconfigured')
    return int(value)


def endpoint(url, allowed, path):
    """Literal IPs only in v1: no DNS rebinding, environment proxy or redirects."""
    try:
        parsed = urlsplit(url)
        address = ipaddress.ip_address(parsed.hostname or '')
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if (parsed.scheme not in ('http', 'https') or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path != path or address.is_link_local
                or address.is_unspecified or address.is_multicast
                or not (address.is_private or address.is_loopback)):
            raise ValueError()
        origin = f'{parsed.scheme}://{parsed.netloc}'
        if origin not in {item.strip() for item in allowed.split(',')}:
            raise ValueError()
        return parsed.scheme, str(address), port, path
    except (ValueError, TypeError):
        raise AIError('misconfigured') from None


def secret(env, prefix):
    """Load one API token from an env value or a private, owned file."""
    inline = env.get(prefix + '_API_KEY', '').strip()
    filename = env.get(prefix + '_API_KEY_FILE', '').strip()
    if bool(inline) == bool(filename):
        raise AIError('misconfigured')
    if inline:
        token = inline
    else:
        try:
            path = Path(filename)
            info = path.lstat()
            if (not path.is_absolute() or stat.S_ISLNK(info.st_mode)
                    or not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077
                    or not 0 < info.st_size <= 4096):
                raise ValueError()
            lines = path.read_text(encoding='utf-8').splitlines()
            if len(lines) != 1:
                raise ValueError()
            token = lines[0].strip()
        except (OSError, UnicodeError, ValueError):
            raise AIError('misconfigured') from None
    if not token or len(token) > 4096 or any(c in token for c in '\r\n'):
        raise AIError('misconfigured')
    return token


@dataclass(frozen=True)
class LocalConfig:
    scheme: str
    host: str
    port: int
    path: str
    model: str
    token: str = field(repr=False)
    connect_timeout: float = 3
    read_timeout: float = 90
    deadline: float = 120
    max_tokens: int = 512

    @classmethod
    def from_env(cls, env, prefix='LOCAL_LLM', path='/v1'):
        target = endpoint(env.get(prefix + '_BASE_URL', ''), env.get('AI_ALLOWED_ENDPOINTS', ''), path)
        model = env.get(prefix + '_MODEL', '').strip()
        token = secret(env, prefix)
        if not model or len(model) > 200:
            raise AIError('misconfigured')
        tokens = integer(env, prefix + '_MAX_TOKENS', 512, 4096)
        integer(env, prefix + '_MAX_INFLIGHT', 1, 1)
        return cls(*target, model, token,
                   number(env, prefix + '_CONNECT_TIMEOUT', 3, 30),
                   number(env, prefix + '_READ_TIMEOUT', 90, 600),
                   number(env, prefix + '_REQUEST_DEADLINE', 120, 600), tokens)


@dataclass(frozen=True)
class VLMConfig:
    scheme: str
    host: str
    port: int
    path: str
    backend: str
    model: str
    token: str = field(repr=False)
    connect_timeout: float = 3
    read_timeout: float = 120
    deadline: float = 180
    max_new_tokens: int = 512

    @classmethod
    def from_env(cls, env):
        if env.get('VLM_BACKEND', '').strip() != 'medgemma_custom_v1':
            raise AIError('misconfigured')
        target = endpoint(
            env.get('VLM_BASE_URL', ''),
            env.get('AI_ALLOWED_ENDPOINTS', ''),
            '',
        )
        model = env.get('VLM_MODEL', '').strip()
        try:
            token = secret(env, 'VLM')
        except AIError:
            raise AIError('misconfigured') from None
        if not model or len(model) > 200 or not token or len(token) > 4096:
            raise AIError('misconfigured')
        if any(c in token for c in '\r\n'):
            raise AIError('misconfigured')
        integer(env, 'VLM_MAX_INFLIGHT', 1, 1)
        return cls(
            *target,
            'medgemma_custom_v1',
            model,
            token,
            number(env, 'VLM_CONNECT_TIMEOUT', 3, 30),
            number(env, 'VLM_READ_TIMEOUT', 120, 600),
            number(env, 'VLM_REQUEST_DEADLINE', 180, 900),
            integer(env, 'VLM_MAX_NEW_TOKENS', 512, 4096),
        )


def validate_llm_settings(env):
    """Validate a complete effective environment without contacting a provider."""
    provider = provider_from(env)
    if provider == 'local':
        LocalConfig.from_env(env)
    elif provider == 'openai' and not env.get('OPENAI_API_KEY', '').strip():
        raise AIError('misconfigured')
    elif provider == 'gemini' and not env.get('GEMINI_API_KEY', '').strip():
        raise AIError('misconfigured')
    return provider
