from django import template

register = template.Library()

@register.simple_tag
def set_query_param(request, key, value):
    params = request.GET.copy()
    params[key] = value
    return params.urlencode()


@register.simple_tag
def remove_query_param(request, key):
    params = request.GET.copy()
    if key in params:
        params.pop(key)
    return params.urlencode()