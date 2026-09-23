"""Bounded local HTTP transport; never invokes a cloud provider or follows redirects."""
import http.client
import hashlib
import json
import socket
import threading
import time
from utils.ai_config import AIError, LocalConfig, provider_from
from utils.ai_generation import GenerationSettings, settings_from_env
from utils.runtime_receipt import validate_runtime_expectation, validate_runtime_receipt

# Process-local admission, deliberately single-flight. Unknown remote completion
# quarantines this client until an operator verifies remote idle and restarts A.
_slot = threading.Lock()
_recovering = threading.Event()


def post_json(config, suffix, payload):
    if _recovering.is_set() or not _slot.acquire(blocking=False):
        raise AIError('busy')
    connection = None
    timer = None
    expired = threading.Event()
    sent = False
    started = time.monotonic()
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(body) > 8 * 1024 * 1024:
            raise AIError('context_too_long')
        connection_cls = http.client.HTTPSConnection if config.scheme == 'https' else http.client.HTTPConnection
        connection = connection_cls(config.host, config.port, timeout=min(config.connect_timeout, config.deadline))
        connection.connect()
        sock = connection.sock
        remaining = config.deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise AIError('request_timeout')
        sock.settimeout(min(config.read_timeout, remaining))

        def expire():
            expired.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

        # A real socket shutdown enforces wall-clock deadline, including trickled
        # headers/body; this does NOT imply cancellation of remote GPU generation.
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        sent = True
        connection.request('POST', config.path + suffix, body, {
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + config.token,
        })
        response = connection.getresponse()
        errors = {401: 'unauthorized', 403: 'unauthorized', 404: 'model_not_found',
                  409: 'configuration_drift',
                  413: 'context_too_long', 429: 'busy', 503: 'loading'}
        if response.status != 200:
            raise AIError(errors.get(response.status, 'backend_unavailable'))
        raw = response.read(1024 * 1024 + 1)
        if expired.is_set():
            raise AIError('request_timeout')
        if len(raw) > 1024 * 1024:
            raise AIError('output_truncated')
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise AIError('invalid_json') from None
        if not isinstance(result, dict):
            raise AIError('invalid_json')
        return result
    except AIError as exc:
        if exc.code == 'request_timeout' and sent:
            _recovering.set()
        raise
    except (socket.timeout, TimeoutError):
        if sent:
            _recovering.set()
        raise AIError('request_timeout') from None
    except (OSError, http.client.HTTPException):
        if sent:
            _recovering.set()
        raise AIError('request_timeout' if expired.is_set() else 'connection_failed') from None
    finally:
        if timer:
            timer.cancel()
        if connection:
            connection.close()
        _slot.release()


def local_chat_with_receipt(
    config, system_prompt, user_message, generation=None, *, runtime_expectation=None,
):
    if len((system_prompt + user_message).encode('utf-8')) > 24000:
        raise AIError('context_too_long')
    if generation is None:
        generation = GenerationSettings(0, None, None, config.max_tokens, 'legacy_effective')
    if generation.max_tokens > config.max_tokens:
        raise AIError('invalid_generation_config')
    payload = {
        'model': config.model, 'stream': False,
        'messages': [{'role': 'system', 'content': system_prompt},
                     {'role': 'user', 'content': user_message}],
    }
    payload.update(generation.request_values())
    prompt_digest = hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()
    if runtime_expectation is not None:
        payload['expected_runtime'] = validate_runtime_expectation(runtime_expectation)
        payload['prompt_digest'] = prompt_digest
    data = post_json(config, '/chat/completions', payload)
    try:
        choice = data['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise AIError('output_truncated')
        reply = choice['message']['content']
        if not isinstance(reply, str) or not reply.strip():
            raise AIError('empty_response')
        receipt = None
        if runtime_expectation is not None:
            receipt = validate_runtime_receipt(
                data.get('runtime_receipt'), runtime_expectation,
                prompt_digest=prompt_digest,
            )
        return reply.strip(), receipt
    except (KeyError, IndexError, TypeError):
        raise AIError('empty_response') from None


def local_chat(config, system_prompt, user_message, generation=None):
    reply, _receipt = local_chat_with_receipt(
        config, system_prompt, user_message, generation,
    )
    return reply


def generate_chat(env, system_prompt, user_message, openai_call, gemini_call):
    """Dispatch once to the explicitly selected provider, without fallback."""
    provider = provider_from(env)
    if provider == 'local':
        if env.get('AI_DEPLOYMENT_PROFILE', 'chat_only') == 'vlm_only':
            raise AIError('backend_unavailable')
        # Snapshot once at request admission. A concurrent admin save affects only
        # later requests and cannot alter this payload in flight.
        generation = settings_from_env(env)
        reply = local_chat(LocalConfig.from_env(env), system_prompt, user_message, generation)
    elif provider == 'gemini':
        reply = gemini_call(system_prompt, user_message, env)
    else:
        reply = openai_call(system_prompt, user_message, env)
    return reply, provider


def _reset_state_for_tests():
    """Reset process state for isolated tests; production recovery uses restart."""
    _recovering.clear()
