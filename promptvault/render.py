"""Только текстовая подстановка, без eval, LLM и изменения шаблона."""
from .store import TOKEN, ValidationError


def render(template, values):
    if not isinstance(values, dict):
        raise ValidationError('Переменные должны быть JSON-объектом')
    names = set(TOKEN.findall(template))
    missing = sorted(name for name in names if name not in values or not isinstance(values[name], str) or not values[name].strip())
    if missing:
        raise ValidationError('Не заполнены переменные: ' + ', '.join(missing))
    if any(len(values[name]) > 20000 for name in names):
        raise ValidationError('Значение переменной превышает 20000 символов')
    return TOKEN.sub(lambda match: values[match.group(1)], template)
