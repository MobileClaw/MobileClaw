import inspect
import json
import re


def print_method_name_with_message(message='null'):
    """Print the calling method name with a message for debugging.

    This method is intended for framework developers.

    Args:
        message: Debug message to print.
    """
    func_name = inspect.stack()[1][3]
    file_name = inspect.stack()[1][1]
    print(f'[DEBUG] >> {file_name} - {func_name} called. message: {message}')


def _save_result(**kwargs):
    pass


def format_vars(vars_dict, extra_exclude_keys=None, max_value_len: int = 200, indent: int = 4):
    """Safely serialize local variables dictionary to JSON string.

    Features:
    - Filters internal variable names (starting with __) and common temporary variable names
    - Uses repr to get string representation and removes memory address fragments like " at 0x..."
    - Attempts to extract device_name from device-related objects and appends to string
    - Truncates overly long values
    - Returns JSON string with ensure_ascii=False and configurable indentation

    Args:
        vars_dict: Dictionary of variables to format.
        extra_exclude_keys: Additional keys to exclude from output.
        max_value_len: Maximum length for values before truncation.
        indent: JSON indentation level.

    Returns:
        str: JSON formatted string of variables.
    """
    default_exclude = ['agent', 'self', 'e', 'handler_call', 'handler', 'try_node', 'stmt', 'new_stmts']
    if extra_exclude_keys and isinstance(extra_exclude_keys, (list, tuple, set)):
        exclude_keys = set(default_exclude) | set(extra_exclude_keys)
    else:
        exclude_keys = set(default_exclude)

    out = {}
    try:
        items = vars_dict.items() if isinstance(vars_dict, dict) else []
    except Exception:
        items = []

    for k, v in items:
        try:
            if isinstance(k, str) and (k.startswith('__') or k in exclude_keys):
                continue

            try:
                s = repr(v)
            except Exception:
                s = f"<{type(v).__name__} object>"

            try:
                s = re.sub(r"\s+at\s+0x[0-9A-Fa-f]+", "", s)
            except Exception:
                pass

            device_name = None
            try:
                if hasattr(v, 'device_name'):
                    dn = getattr(v, 'device_name')
                    if isinstance(dn, str) and dn:
                        device_name = dn
                if device_name is None and hasattr(v, 'device'):
                    dev = getattr(v, 'device')
                    if hasattr(dev, 'device_name'):
                        dn = getattr(dev, 'device_name')
                        if isinstance(dn, str) and dn:
                            device_name = dn
            except Exception:
                device_name = None

            if device_name:
                s = f"{s} (device_name='{device_name}')"

            if isinstance(s, str) and len(s) > max_value_len:
                s = s[:max_value_len] + '...'

            out[k] = s
        except Exception:
            out[k] = f"<{type(v).__name__} object (unserializable)>"

    try:
        return json.dumps(out, indent=indent, ensure_ascii=False)
    except Exception:
        try:
            return json.dumps({"error": "unserializable"}, ensure_ascii=False)
        except Exception:
            return "{}"
