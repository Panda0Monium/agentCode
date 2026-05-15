"""
Converts a raw list[Action] into a UI-ready dict for the trajectory viewer.
Diffs are computed here at save-time so the view is cheap.
"""

import difflib


def process(actions: list) -> dict:
    steps = []
    prev_content: dict[str, str] = {}

    for action in actions:
        tool = action.tool
        args = action.args or {}
        result = action.result
        ts = round(action.timestamp, 2)

        if tool == 'llm_invoke':
            response = result or {}
            tool_calls = response.get('tool_calls') or []
            text = response.get('content') or ''
            if isinstance(text, list):
                text = ' '.join(p.get('text', '') for p in text if isinstance(p, dict))
            steps.append({
                'tool':       'llm_invoke',
                'timestamp':  ts,
                'tool_calls': [{'name': tc.get('name'), 'args': tc.get('args', {})} for tc in tool_calls],
                'text':       text[:2000] if text else '',
            })

        elif tool == 'write_file':
            path = args.get('path', '')
            new_content = args.get('content', '')
            before = prev_content.get(path, '')
            diff = ''.join(difflib.unified_diff(
                before.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f'a/{path}',
                tofile=f'b/{path}',
            ))
            prev_content[path] = new_content
            steps.append({
                'tool':      'write_file',
                'timestamp': ts,
                'path':      path,
                'diff':      diff,
            })

        elif tool == 'read_file':
            path = args.get('path', '')
            content = result if isinstance(result, str) else ''
            prev_content[path] = content
            steps.append({
                'tool':      'read_file',
                'timestamp': ts,
                'path':      path,
                'content':   content[:3000],
            })

        elif tool == 'run_tests':
            if hasattr(result, 'cases'):
                passed = result.passed
                total  = result.total
                cases  = [
                    {
                        'name':   c.name,
                        'passed': c.passed,
                        'error':  (c.error or '')[:500] if c.error else None,
                    }
                    for c in result.cases
                ]
            elif isinstance(result, dict):
                passed = result.get('passed', 0)
                total  = result.get('total', 0)
                cases  = result.get('cases', [])
            else:
                passed, total, cases = 0, 0, []
            steps.append({
                'tool':      'run_tests',
                'timestamp': ts,
                'passed':    passed,
                'total':     total,
                'cases':     cases,
            })

        elif tool == 'run_lint':
            if hasattr(result, 'errors'):
                errors = [
                    {'path': e.path, 'line': e.line, 'code': e.code, 'message': e.message}
                    for e in result.errors
                ]
            elif isinstance(result, dict):
                errors = result.get('errors', [])
            else:
                errors = []
            steps.append({
                'tool':      'run_lint',
                'timestamp': ts,
                'errors':    errors,
            })

        elif tool == 'list_files':
            files = result if isinstance(result, list) else []
            steps.append({'tool': 'list_files', 'timestamp': ts, 'files': files})

    return {'steps': steps}
