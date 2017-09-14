def deep_get(obj, path, default=None):
    """Get a deeply nested path, with fallback if it can't be found

    >>> deep_get({'a': {'b': 5}}, 'a.b')
    5
    >>> deep_get({'a': {'b': 5}}, 'foo')
    None
    >>> deep_get({'a': {'b': 5}}, 'foo', 0)
    0
    >>> deep_get({'a': {'b': 5}}, 'foo', 0)
    0
    >>> deep_get(None, 'foo', 0)
    0
    >>> deep_get({'a': None}, 'a.b', 0)
    0
    """
    try:
        sub_obj = obj
        keys = path.split('.')
        for key in keys:
            sub_obj = sub_obj[key]
        return sub_obj
    except (KeyError, TypeError):
        return default


if __name__ == '__main__':
    assert deep_get({'a': {'b': 5}}, 'a.b') == 5
    assert deep_get({'a': {'b': 5}}, 'foo') is None
    assert deep_get({'a': {'b': 5}}, 'foo', 0) == 0
    assert deep_get({'a': {'b': 5}}, 'foo', 0) == 0
    assert deep_get(None, 'foo', 0) == 0
    assert deep_get({'a': None}, 'a.b', 0) == 0
