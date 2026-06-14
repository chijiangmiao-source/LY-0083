import json

from bottle import response


def dict_to_json(data):
    if data is None:
        return None
    if isinstance(data, list):
        return [dict(row) for row in data]
    return dict(data)


def json_response(data, success=True, message=''):
    response.content_type = 'application/json'
    return json.dumps({
        'success': success,
        'message': message,
        'data': dict_to_json(data) if data else None
    }, default=str, ensure_ascii=False)


def to_template_json(data):
    if data is None:
        return 'null'
    return json.dumps(dict_to_json(data) if not isinstance(data, (dict, list)) else data, default=str, ensure_ascii=False)
