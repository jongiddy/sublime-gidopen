import glob
import os

import sublime
import sublime_plugin


def _get_package_location(winvar):
    packages = winvar['packages']
    this_package = os.path.dirname(__file__)
    assert this_package.startswith(packages)
    unwanted = os.path.dirname(packages)
    # add one to remove pathname delimiter /
    return this_package[len(unwanted) + 1:]


def is_likely_path_char(c):
    if ord(c) <= 32:  # Control character or space
        return False
    if c in '<>&|\'",;:[](){}*?`':  # more commonly near paths than in paths
        return False
    return True


def glob_escape(s):
    r = ''
    for c in s:
        if c in ('?', '*', '['):
            r += '[{}]'.format(c)
        else:
            r += c
    return r


def find_all(pat, s):
    i = s.find(pat)
    while i != -1:
        yield i
        i = s.find(pat, i + 1)

class Candidate:

    def __init__(self, region, path, score):
        print(path)
        self.region = region
        self.path = path
        self.score = score


def match_absolute_path(
    view, begin, path, score=0
):
    # Requires a path that is absolute once expanduser is run.
    # For absolute path, add wildcard to end to find files.
    # The returned paths will have the expanded user path, so we need to
    # adust the length of region to capture the (usually shorter) text.
    len0 = len(path)
    path = os.path.expanduser(path)
    len1 = len(path)
    adjust = len1 - len0
    pattern = '{}*'.format(glob_escape(path))
    print('GidOpen: glob', pattern)
    abs_paths = glob.glob(pattern)
    count = 0
    for abs_path in abs_paths:
        r = sublime.Region(begin, begin + len(abs_path) - adjust)
        text = view.substr(r)
        if os.path.expanduser(text) == abs_path:
            yield Candidate(r, abs_path, score + len(abs_path))
            count += 1
    return count


def match_relative_path(
    pwd, view, begin, path, score=0
):
    glob_pwd = glob_escape(pwd)
    extralen = len(pwd) + 1
    pattern = '{}/*{}*'.format(glob_pwd, glob_escape(path))
    print('GidOpen: glob', pattern)
    abs_paths = glob.glob(pattern)
    if path.startswith('./') or path.startswith('../'):
        # glob doesn't match . or .. so check paths like `./file` without
        # wildcard at start.
        pattern = '{}/{}*'.format(glob_pwd, glob_escape(path))
        print('glob', pattern)
        abs_paths += glob.glob(pattern)
    count = 0
    for abs_path in abs_paths:
        expected = abs_path[extralen:]
        for idx in find_all(path, expected):
            b = begin - idx
            if b >= 0:
                r = sublime.Region(b, b + len(expected))
                text = view.substr(r)
                if text == expected:
                    yield Candidate(r, abs_path, score + len(expected))
                    count += 1
    return count


def expand_path(view, begin, end):
    while begin > 0 and is_likely_path_char(view.substr(begin - 1)):
        begin -= 1
    while end < view.size() and is_likely_path_char(view.substr(end)):
        end += 1
    return begin, end


def get_menu_path(view, event):
    click_point = view.window_to_text((event['x'], event['y']))

    # If right-click is in a selected non-empty region, use the path
    # in the region. This allows override of the heuristic.
    for selected_region in view.sel():
        if (
            selected_region.contains(click_point)
            and not selected_region.empty()
        ):
            path = os.path.expanduser(view.substr(selected_region))
            if not path.startswith('/'):
                pwd = view.settings().get('gidopen_pwd')
                if pwd is None:
                    window = view.window()
                    winvar = window.extract_variables()
                    pwd = winvar.get('folder', os.environ.get('HOME', '/'))

                path = os.path.join(pwd, path)
            yield Candidate(selected_region, path, 1000)

    # Look for surrounding text that is almost certainly part of the
    # path. Use that text to search for possible matches in filesystem.
    # Check each possibility for a match in further surrounding text,
    # and return longest match.
    begin, end = expand_path(view, click_point, click_point)
    if begin == end:
        return
    region = sublime.Region(begin, end)
    path = view.substr(region)
    print('GidOpen: looking for %r' % path)
    if path[0] == '~':
        # Looks like a tilde expanded absolute path.
        # The returned paths will have the expanded user path, so we need to
        # adust the length of region to capture the (usually shorter) text.
        count = yield from match_absolute_path(view, begin, path)
        if count > 0:
            return
        # Otherwise, treat as part of an unusual filename
        # ('~1' or '[foo]~1/bar', won't find 'dir/[foo]~1/bar')
    elif path[0] == '/':
        # Looks like an absolute path.
        count = yield from match_absolute_path(view, begin, path)
        if count > 0:
            return
        # If absolute path is not found, then it may be a mounted file in a
        # container. Remove the leading `/` and treat as a relative path.
        path = path[:1]

    # Now we have a relative name

    # Check if the view has a working directory
    window = view.window()
    winvar = window.extract_variables()
    print(winvar)
    basedir = winvar.get('folder', os.environ.get('HOME', '/'))
    pwd = view.settings().get('gidopen_pwd')
    if pwd is None:
        pwd = basedir

    yield from match_relative_path(pwd, view, begin, path)
    if pwd != basedir:
        yield from match_relative_path(basedir, view, begin, path, -1000)


def get_pwd(history, region):
    pos = region.begin()
    base = '~'
    for start, pwd in history:
        if start > pos:
            break
        base = pwd
    return os.path.expanduser(base)


def get_line_col(view, pos):
    # Parse the characters following the filename to see if they match a
    # number of patterns associated with specific line and column numbers.
    ch = view.substr(pos)
    if ch == ':':
        pos += 1
        ch = view.substr(pos)
        if ch == ' ':
            pos += 1
            ch = view.substr(pos)
            if ch == 'l':
                if view.substr(sublime.Region(pos + 1, pos + 5)) == 'ine ':
                    # PATH: line LINE (bash)
                    pos += 5
                    line = view.substr(pos)
                    if line not in '0123456789':
                        return None
                    pos += 1
                    ch = view.substr(pos)
                    while ch in '0123456789':
                        line += ch
                        pos += 1
                        ch = view.substr(pos)
                    return (line, 0)
            elif ch in '0123456789':
                # PATH: LINE: (bash)
                line = ch
                pos += 1
                ch = view.substr(pos)
                while ch in '0123456789':
                    line += ch
                    pos += 1
                    ch = view.substr(pos)
                if ch == ':':
                    return (line, 0)
        elif ch in '0123456789':
            # PATH:LINE[:COL]
            line = ch
            pos += 1
            ch = view.substr(pos)
            while ch in '0123456789':
                line += ch
                pos += 1
                ch = view.substr(pos)
            if ch != ':':
                return (line, 0)
            pos += 1
            col = view.substr(pos)
            if col not in '0123456789':
                return (line, 0)
            pos += 1
            ch = view.substr(pos)
            while ch in '0123456789':
                col += ch
                pos += 1
                ch = view.substr(pos)
            if ch in ': \t\r\n':
                return (line, col)
            else:
                # avoid PATH:LINE:YEAR-MONTH-DAY (often found in logs)
                return (line, 0)
        return None
    elif ch == '"':
        if view.substr(sublime.Region(pos + 1, pos + 8)) == ', line ':
            # "PATH", line LINE (Python)
            pos += 8
            line = view.substr(pos)
            if line not in '0123456789':
                return None
            pos += 1
            ch = view.substr(pos)
            while ch in '0123456789':
                line += ch
                pos += 1
                ch = view.substr(pos)
            return (line, 0)
    return None


CONTEXT_ACTION_FILE_OPEN = 'Open File'
CONTEXT_ACTION_FILE_GOTO = 'Goto File'
CONTEXT_ACTION_FILE_NEW = 'Create File'


class gidopen_context(sublime_plugin.TextCommand):

    def run(self, edit, event):
        context = self.view.settings().get('gidopen_context')
        if context is None:
            return
        action, path = context
        window = self.view.window()
        if action == CONTEXT_ACTION_FILE_GOTO:
            options = sublime.ENCODED_POSITION
        else:
            options = 0
        view = window.open_file(path, options)
        window.focus_view(view)
        self.view.settings().set('gidopen_context', None)

    def is_visible(self, event):
        return self.view.settings().get('gidopen_context') is not None

    def description(self, event):
        action = CONTEXT_ACTION_FILE_NEW
        candidates = sorted(
            get_menu_path(self.view, event),
            key=lambda c: c.score,
            reverse=True,
        )

        for candidate in candidates:
            if os.path.isdir(candidate.path):
                continue
            else:
                path = os.path.normpath(candidate.path)
                label = path
                home = os.environ['HOME'] + '/'
                if label.startswith(home):
                    label = '~/' + label[len(home):]
                if os.path.exists(path):
                    linecol = get_line_col(self.view, candidate.region.end())
                    if linecol:
                        line, col = linecol
                        path = '{}:{}:{}'.format(candidate.path, line, col)
                        if col == 0:
                            label = '{}:{}'.format(label, line)
                        else:
                            label = '{}:{}:{}'.format(label, line, col)
                        action = CONTEXT_ACTION_FILE_GOTO
                    else:
                        action = CONTEXT_ACTION_FILE_OPEN
                else:
                    action = CONTEXT_ACTION_FILE_NEW

            self.view.settings().set('gidopen_context', (action, path))
            return '{} {}'.format(action, label)

        self.view.settings().set('gidopen_context', None)
        return 'no candidates'

    def want_event(self):
        return True
