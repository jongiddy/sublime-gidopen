import collections
import os
import re

import sublime  # type: ignore
import sublime_plugin  # type: ignore


def is_likely_path_char(c):
    # type: (str) -> bool
    if ord(c) <= 32:  # Control character or space
        return False
    if c in '<>&|\'",;:[]()*?`=#!':  # more commonly near paths than in paths
        # some explicit decisions:
        # = is in to make ENVNAME=PATH isolate PATH
        # (#) are in to make [AWS](docs/install.md#aws) isolate path
        # ${} are out to make $ENVNAME and ${ENVNAME} part of path
        return False
    return True


def find_all(pat, s):
    # (str, str) -> Iterator[int]
    i = s.find(pat)
    while i != -1:
        yield i
        i = s.find(pat, i + 1)

class Candidate:

    def __init__(self, region, path):
        # type: (sublime.Region, str) -> None
        self.region = region
        self.path = path

    def __repr__(self):
        # type: () -> str
        return '{}({!r})'.format(self.__class__.__name__, self.path)


class FileFound(Candidate):
    pass


class FolderFound(Candidate):
    pass


class FileNotFound(Candidate):
    pass


class FolderNotFound(Candidate):
    pass


class TextFound(Candidate):
    pass


def select_longest(candidates):
    # type: (...) -> Candidate|None
    result = None
    maxlen = -1
    for candidate in candidates:
        length = len(candidate.path)
        if length > maxlen:
            result = candidate
            maxlen = length
    return result


def add_folder_to_project(window, path):
    # type: (sublime.Window, str) -> None
    folder = {
        'path': path
    }
    project = window.project_data()
    if not project:
        project = {
            'folders': [
                folder
            ]
        }
    else:
        project['folders'].append(folder)
    window.set_project_data(project)


def expand_path(view, begin, end):
    # type: (sublime.View, int, int) -> tuple[int, int]
    while begin > 0 and is_likely_path_char(view.substr(begin - 1)):
        begin -= 1
    while end < view.size() and is_likely_path_char(view.substr(end)):
        end += 1
    return begin, end


def get_line_col(view, pos):
    # type: (sublime.View, int) -> tuple[int, int]|None
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
            if ord(ch) <= 32 or ch in ':':
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


CONTEXT_ACTION_FOLDER_ADD = 'Add Folder'
CONTEXT_ACTION_FOLDER_FIND = 'Find'
CONTEXT_ACTION_FILE_OPEN = 'Open'
CONTEXT_ACTION_FILE_GOTO = 'Goto'
CONTEXT_ACTION_FILE_NEW = 'New File'
CONTEXT_ACTION_FOLDER_NEW = 'Create Folder'


def is_in(descendent, ancestor):
    # type: (str, str) -> bool
    assert descendent != ancestor
    return (
        descendent.startswith(ancestor)
        and descendent[len(ancestor)] == os.sep
    )


class gidopen_context(sublime_plugin.TextCommand):

    def __init__(self, view):
        # type: (sublime.View) -> None
        super().__init__(view)
        self._home = None  # type: str|None
        self._folders = None  # type: list[str]|None
        self._pwd = None  # type: str|None
        self._labels = None  # type: dict[str, str]|None
        self._folder_excludes = self.view.settings().get(
            'folder_exclude_patterns'
        )

    def _get_home(self):
        # type: () -> str
        if self._home is None:
            self._home = os.environ.get('HOME', '/')
        assert self._home is not None
        return self._home

    def _setup_folders(self):
        # type: () -> tuple[str, list[str], dict[str, str]]
        if self._pwd is None:
            self._folder_excludes = self.view.settings().get(
                'folder_exclude_patterns'
            )
            window = self.view.window()
            winvar = window.extract_variables()
            window_folders = window.folders()
            folders = []  # type: list[str]
            labels = {}  # type: dict[str, str]
            count = collections.defaultdict(int)  # type: dict[str, int]
            for after, folder in enumerate(window_folders, start=1):
                basename = os.path.basename(folder)
                count[basename] += 1
                if any(folder == f or is_in(folder, f) for f in folders):
                    # If a parent of this folder has appeared, do not keep
                    pass
                elif any(is_in(folder, f) for f in window_folders[after:]):
                    # If a parent of this folder is yet to come, do not keep
                    pass
                else:
                    folders.append(folder)
            for folder in folders:
                basename = os.path.basename(folder)
                if count[basename] == 1:
                    labels[folder] = basename
            pwd = self.view.settings().get('gidopen_pwd')
            if pwd is None:
                file = winvar.get('file')
                if file is not None:
                    pwd = os.path.dirname(file)
                elif folders:
                    pwd = folders[0]
                else:
                    pwd = self._get_home()
            else:
                pwd = os.path.expanduser(pwd)
            self._pwd = pwd
            self._folders = folders
            self._labels = labels

        assert self._pwd is not None
        assert self._folders is not None
        assert self._labels is not None

        return self._pwd, self._folders, self._labels

    def _folder_iterate(self, yield_pwd_in_folder=True):
        # If yield_pwd_in_folder is:
        # True, yield the pwd even if it is subfolder of a project folder
        # False, do not yield the pwd if it is a subfolder of a project folder
        pwd, folders, labels = self._setup_folders()
        pwd_is_folder = False
        pwd_in_folder = False
        for folder in folders:
            yield folder
            if pwd == folder:
                pwd_is_folder = True
            elif is_in(pwd, folder):
                pwd_in_folder = True
        if pwd_in_folder:
            if yield_pwd_in_folder:
                yield pwd
        else:
            if not pwd_is_folder:
                yield pwd

    def _get_pwd(self):
        # type: () -> str
        pwd, folders, labels = self._setup_folders()
        return pwd

    def _expand_region(self, prefix_region, suffix):
        # type: (sublime.Region, str) -> sublime.Region|None
        begin = prefix_region.end()
        end = begin + len(suffix)
        if suffix == self.view.substr(sublime.Region(begin, end)):
            return sublime.Region(prefix_region.begin(), end)
        return None

    def all_matching_descendants(self, folder_path, folder_region):
        assert os.path.isdir(folder_path)
        dlen = len(folder_path)
        for dirpath, dirnames, filenames in os.walk(folder_path):
            i = 0
            while i < len(dirnames):
                dirname = dirnames[i]
                path = os.path.join(dirpath, dirname)
                if dirname in self._folder_excludes:
                    print(
                        'GidOpen: - skip',
                        self._shorten_name(path),
                    )
                    del dirnames[i]
                else:
                    region = self._expand_region(folder_region, path[dlen:])
                    if region:
                        yield FolderFound(region, path)
                        # descend into this folder
                        i += 1
                    else:
                        # don't descend into this folder
                        del dirnames[i]

            for filename in filenames:
                path = os.path.join(dirpath, filename)
                region = self._expand_region(folder_region, path[dlen:])
                if region:
                    yield FileFound(region, path)

    def all_files_prefixed_by(self, prefix, prefix_region):
        # (str, sublime.Region) -> Generator[Candidate, None, bool]
        # yield all filesystem paths that start with the
        # path `prefix`. The prefix ends at position `end`.
        found = False
        assert os.path.isabs(prefix)
        # split into dirname and basename prefix
        d, p = os.path.split(prefix)
        if os.path.isdir(d):
            for name in os.listdir(d):
                if name.startswith(p):
                    path = os.path.join(d, name)
                    suffix = path[len(prefix):]
                    region = self._expand_region(prefix_region, suffix)
                    if region:
                        if os.path.isdir(path):
                            if name in self._folder_excludes:
                                print(
                                    'GidOpen: - skip',
                                    self._shorten_name(path),
                                )
                            else:
                                found = True
                                yield FolderFound(region, path)
                                if self.view.substr(region.end()) == '/':
                                    yield from self.all_matching_descendants(
                                        path, region
                                    )
                        else:
                            found = True
                            yield FileFound(region, path)
        return found

    def check_absolute_path(self, region, path):
        # (sublime.Region, str) -> Generator[Candidate, None, bool]
        found = False
        if os.path.isabs(path):
            print('GidOpen: - absolute')
            found = yield from self.all_files_prefixed_by(path, region)
        elif path[0] == '~':
            # Looks like a tilde expanded absolute path.
            print('GidOpen: - absolute')
            expanded = os.path.expanduser(path)
            if expanded != path:
                # If path starts with '~alice' but user `alice` does not exist,
                # then `expanduser` keeps the path as '~alice', in which case
                # don't treat it as an absolute path.
                found = yield from self.all_files_prefixed_by(expanded, region)
        return found

    def _handle_click_region(self, region):
        # (Region) -> Iterator[Candidate]
        # If right-click is in a selected non-empty region, use the path
        # in the region. This allows override of the heuristic.
        selected_text = self.view.substr(region)
        yield TextFound(region, selected_text)
        path = os.path.expanduser(selected_text)
        expanded = os.path.expanduser(
            os.path.expandvars(selected_text)
        )
        if path != expanded:
            if os.path.isabs(path):
                if os.path.isfile(path):
                    yield FileFound(region, path)
                elif os.path.isdir(path):
                    yield FolderFound(region, path)
                elif os.path.isdir(os.path.dirname(path)):
                    yield FileNotFound(region, path)
                else:
                    path = os.path.dirname(path)
                    parent = os.path.dirname(path)
                    while parent != path and not os.path.isdir(parent):
                        path = parent
                        parent = os.path.dirname(path)
                    yield FolderNotFound(region, path)
            else:
                for folder in self._folder_iterate():
                    abspath = os.path.normpath(os.path.join(folder, path))
                    if os.path.isfile(abspath):
                        yield FileFound(region, abspath)
                    elif os.path.isdir(path):
                        yield FolderFound(region, path)

        if os.path.isabs(expanded):
            if os.path.isfile(expanded):
                yield FileFound(region, expanded)
            elif os.path.isdir(expanded):
                yield FolderFound(region, expanded)
            elif os.path.isdir(os.path.dirname(expanded)):
                yield FileNotFound(region, expanded)
            else:
                path = os.path.dirname(expanded)
                parent = os.path.dirname(path)
                while parent != path and not os.path.isdir(parent):
                    path = parent
                    parent = os.path.dirname(path)
                yield FolderNotFound(region, path)
        else:
            for folder in self._folder_iterate():
                abspath = os.path.normpath(os.path.join(folder, expanded))
                if os.path.isfile(abspath):
                    yield FileFound(region, abspath)
                elif os.path.isdir(abspath):
                    yield FolderFound(region, abspath)

    def _handle_click_point(self, click_point):
        # (int) -> Iterator[Candidate]

        # Look for surrounding text that is almost certainly part of the
        # path. Use that text to search for possible matches in filesystem.
        # Check each possibility for a match in further surrounding text,
        # and return longest match.
        begin, end = expand_path(self.view, click_point, click_point)
        if begin == end:
            # try adding one not-a-path character in case we've clicked in the
            # middle of ' [' in '/file [x86].txt'
            if begin != 0:
                begin, end = expand_path(self.view, begin - 1, begin)
            if end < self.view.size() and end - begin < 2:
                # didn't expand, try the other direction
                begin, end = expand_path(self.view, end, end + 1)

        region = sublime.Region(begin, end)
        path = self.view.substr(region)

        # Trailing dots and slashes are generally not useful for matching.
        path = path.rstrip('/.')
        end = region.begin() + len(path)
        region = sublime.Region(begin, end)

        if end == begin:
            return

        basename = os.path.basename(path)

        print('GidOpen: looking for %r' % path)

        found = yield from self.check_absolute_path(region, path)
        if found:
            return

        expanded = os.path.expandvars(path)
        if expanded != path:
            # e.g. ${HOME}/file
            found = yield from self.check_absolute_path(region, expanded)
            if found:
                return

        if basename == path:
            # we only have a basename, so we need to search *basename*.
            # To keep this fast, we only match in folders and pwd, only
            # descending into them if they continue to match.
            for folder in self._folder_iterate():
                print('GidOpen: - in', self._shorten_name(folder))
                for name in os.listdir(folder):
                    fullpath = os.path.join(folder, name)
                    for idx in find_all(basename, name):
                        # matched name starts `idx` chars before basename
                        text_start = begin - idx
                        text_end = text_start + len(name)
                        text_region = sublime.Region(text_start, text_end)
                        text = self.view.substr(text_region)
                        if text == name:
                            if os.path.isdir(fullpath):
                                yield FolderFound(text_region, fullpath)
                                if self.view.substr(text_end) == '/':
                                    yield from self.all_matching_descendants(
                                        fullpath, text_region
                                    )
                            elif os.path.isfile(fullpath):
                                yield FileFound(text_region, fullpath)
        else:
            # we have a / before the basename, so we can search basename*. As
            # this is faster, we do a recursive search on folders and pwd.

            # First, search in the folders and pwd
            for folder in self._folder_iterate():
                print('GidOpen: - in', self._shorten_name(folder))
                if os.path.isdir(folder):
                    prefix = os.path.join(folder, basename)
                    for name in os.listdir(folder):
                        if name.startswith(basename):
                            path = os.path.join(folder, name)
                            suffix = path[len(prefix):]
                            cregion = self._expand_region(region, suffix)
                            if cregion:
                                if os.path.isdir(path):
                                    if name in self._folder_excludes:
                                        print(
                                            'GidOpen: - skip',
                                            self._shorten_name(path),
                                        )
                                    else:
                                        yield FolderFound(cregion, path)
                                else:
                                    yield FileFound(region, path)

            # Second, search under folders
            home = self._get_home()
            pwd = self._get_pwd()
            for folder in self._folder_iterate(yield_pwd_in_folder=False):
                if folder == home or is_in(home, folder):
                    # too big to search recursively
                    continue

                print('GidOpen: - under', self._shorten_name(folder))
                for dirpath, dirnames, filenames in os.walk(folder):
                    i = 0
                    while i < len(dirnames):
                        dirname = dirnames[i]
                        path = os.path.join(dirpath, dirname)
                        if path == pwd:
                            # already searched in pwd, but still need to
                            # search below pwd, so keep in dirnames
                            i += 1
                        elif dirname in self._folder_excludes:
                            print(
                                'GidOpen: - skip',
                                self._shorten_name(path)
                            )
                            del dirnames[i]
                        else:
                            path = os.path.join(path, basename)
                            yield from self.all_files_prefixed_by(path, region)
                            i += 1

    def _best(self, options):
        return select_longest(options)

    def _folder_in_project(self, name):
        # type: (str) -> bool
        pwd, folders, labels = self._setup_folders()
        for folder in folders:
            if name == folder or is_in(name, folder):
                return True
        return False

    def _shorten_name(self, name):
        # type: (str) -> str
        pwd, folders, labels = self._setup_folders()

        for folder in folders:
            if name == folder or is_in(name, folder):
                label = labels.get(folder)
                if label is not None:
                    return '{}{}'.format(label, name[len(folder):])

        home = self._get_home()
        if home != '/' and name != home and is_in(name, home):
            return '~' + name[len(home):]

        return name

    def want_event(self):
        return True

    def description(self, event):
        try:
            self._pwd = None
            action = CONTEXT_ACTION_FILE_NEW
            files = []
            folders = []
            notfiles = []
            notfolders = []
            texts = []

            click_point = self.view.window_to_text((event['x'], event['y']))

            for selected_region in self.view.sel():
                if (
                    selected_region.contains(click_point)
                    and not selected_region.empty()
                ):
                    candidates = self._handle_click_region(selected_region)
                    break
            else:
                candidates = self._handle_click_point(click_point)

            for candidate in candidates:
                print('GidOpen:', candidate)
                if isinstance(candidate, FileFound):
                    files.append(candidate)
                elif isinstance(candidate, FolderFound):
                    folders.append(candidate)
                elif isinstance(candidate, FileNotFound):
                    notfiles.append(candidate)
                elif isinstance(candidate, FolderNotFound):
                    notfolders.append(candidate)
                else:
                    assert isinstance(candidate, TextFound)
                    texts.append(candidate)

            candidate = self._best(files)
            if candidate is not None:
                path = candidate.path
                label = self._shorten_name(path)
                linecol = get_line_col(self.view, candidate.region.end())
                if linecol:
                    line, col = linecol
                    path = '{}:{}:{}'.format(path, line, col)
                    if col == 0:
                        label = '{}:{}'.format(label, line)
                    else:
                        label = '{}:{}:{}'.format(label, line, col)
                    action = CONTEXT_ACTION_FILE_GOTO
                else:
                    action = CONTEXT_ACTION_FILE_OPEN
            else:
                candidate = self._best(folders)
                if candidate is not None:
                    path = candidate.path
                    if self._folder_in_project(path):
                        action = None
                        path = None
                        label = None
                    else:
                        action = CONTEXT_ACTION_FOLDER_ADD
                        label = self._shorten_name(path)
                else:
                    candidate = self._best(notfiles)
                    if candidate is not None:
                        action = CONTEXT_ACTION_FILE_NEW
                        path = candidate.path
                        label = self._shorten_name(path)
                    else:
                        candidate = self._best(notfolders)
                        if candidate is not None:
                            action = CONTEXT_ACTION_FOLDER_NEW
                            path = candidate.path
                            label = self._shorten_name(path)
                        else:
                            action = None
                            path = None
                            label = None

            self.view.settings().set('gidopen_context', (action, path))
            return '{} {}'.format(action, label)
        except Exception:
            import traceback
            traceback.print_exc()
            raise

    def is_visible(self, event):
        context = self.view.settings().get('gidopen_context')
        return context is not None and context[0] is not None

    def run(self, edit, event):
        context = self.view.settings().get('gidopen_context')
        if context is None:
            return
        action, path = context
        window = self.view.window()
        if action == CONTEXT_ACTION_FOLDER_ADD:
            add_folder_to_project(window, path)
        elif action == CONTEXT_ACTION_FOLDER_FIND:
            window.run_command(
                'show_overlay',
                {'overlay': 'goto', 'show_files': True, 'text': path}
            )

            # self.view.run_command('refresh_folder_list')
            # tmpfile = os.path.join(path, 'aa.')
            # with open(tmpfile, 'w'):
            #     pass
            # view = window.open_file(tmpfile, 0)
            # view.window().run_command('reveal_in_side_bar')
            # view.window().run_command("close_file")

            # for name in os.listdir(path):
            #     file = os.path.join(path, name)
            #     if os.path.isfile(file):
            #         view = window.open_file(file, 0)
            #         sublime.active_window().run_command('reveal_in_side_bar')
            #         # view.window().run_command("close_file")
            #         break

            # sublime.active_window().run_command(
            #     # 'side_bar_open_in_new_window',
            #     'side_bar_reveal',
            #     {
            #         'paths': [path],
            #     }
            # )
        elif action == CONTEXT_ACTION_FOLDER_NEW:
            os.mkdir(path)
            if not self._folder_in_project(path):
                add_folder_to_project(window, path)
        else:
            if action == CONTEXT_ACTION_FILE_GOTO:
                options = sublime.ENCODED_POSITION
            else:
                options = 0
            view = window.open_file(path, options)
            window.focus_view(view)
        self.view.settings().set('gidopen_context', None)
