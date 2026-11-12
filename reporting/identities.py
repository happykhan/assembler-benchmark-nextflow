"""Shared stable execution identities and result routes."""
import re

def result_slug(record):
    values = [record['scenario_id'], record['tool']]
    if record.get('run_id'):
        values.append(record['run_id'])
    if any((not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', value) for value in values)):
        raise ValueError('Result URL components must be simple identifiers')
    return '--'.join(values)

def result_href(record, prefix=''):
    return prefix + 'results/' + result_slug(record) + '.html'
