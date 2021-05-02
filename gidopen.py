import collections
import os
import platform
import traceback

import sublime  # type: ignore
import sublime_plugin  # type: ignore

SETTING_PWD = 'current_working_directory'

CONTEXT_ACTION_ERROR = 'Error'
CONTEXT_ACTION_FOLDER_ADD = 'Add Folder'
CONTEXT_ACTION_FOLDER_REVEAL = 'Reveal'
CONTEXT_ACTION_FOLDER_FIND = 'Find'
CONTEXT_ACTION_FILE_OPEN = 'Open'
CONTEXT_ACTION_FILE_GOTO = 'Goto'
CONTEXT_ACTION_FILE_NEW = 'New File'
CONTEXT_ACTION_FOLDER_NEW = 'Create Folder'

if platform.system() == 'Windows':
    def is_path_root(s):
        # type: (str) -> bool
        if len(s) == 1:
            return s in '\\/'
        if s[1] == ':':
            return len(s) == 3 and s[2] in '\\/'
        return False

    def is_path_sep(c):
        # type: (str) -> bool
        return c in '\\/'

    def get_home():
        # type: () -> AbsolutePath
        return AbsolutePath(os.environ['HOMEDRIVE'] + os.environ['HOMEPATH'])

    def expanduser(path):
        # type: (str) -> str
        # On Linux `os.path.expanduser` only resolves tilde paths if the user
        # exists.  On Windows it returns the path that would be the user's home
        # directory even if the user and directory do not exist.  This function
        # makes it uniform: tilde directories only resolve if the directory
        # exists.
        if not path or path[0] != '~':
            return path
        idx = 1
        while idx < len(path) and not is_path_sep(path[idx]):
            idx += 1
        d = os.path.expanduser(path[:idx])
        if os.path.isdir(d):
            return os.path.expanduser(path)
        else:
            return path
else:
    assert os.sep == '/'

    def is_path_root(s):
        # type: (str) -> bool
        return s == '/'

    def is_path_sep(c):
        # type: (str) -> bool
        return c == '/'

    def get_home():
        # type: () -> AbsolutePath
        return AbsolutePath(os.environ['HOME'])

    def expanduser(path):
        # type: (str) -> str
        return os.path.expanduser(path)


# Any section of a path, to allow path-like comparison.
class PartialPath(object):

    def __init__(self, path):
        # type: (str) -> None
        self.path = path
        self.norm = self.normalize(path)
        self.canonical = os.path.normcase(self.norm)

    def normalize(self, path):
        # type: (str) -> str
        if path:
            return os.path.normpath(path)
        return path

    def __str__(self):
        # type: () -> str
        return self.path

    def __len__(self):
        # type: () -> int
        return len(self.path)

    def __hash__(self):
        # type: () -> int
        return hash(self.canonical)

    def __eq__(self, other):
        # type: (object) -> bool
        if not isinstance(other, PartialPath):
            return NotImplemented
        return self.canonical == other.canonical

    def canonical_len(self):
        # type: () -> int
        return len(self.canonical)


class AbsolutePath(PartialPath):

    def normalize(self, path):
        # type: (str) -> str
        return expanduser(super().normalize(path))

    def __lt__(self, other):
        # type: (AbsolutePath) -> bool
        # `self < other` indicates that `self` is an ancestor of `other`.
        if not isinstance(other, AbsolutePath):
            return NotImplemented
        prefix = self.canonical + os.sep
        return other.canonical.startswith(prefix)

    def __le__(self, other):
        # type: (AbsolutePath) -> bool
        return self == other or self < other

    def is_root(self):
        # type: () -> bool
        return is_path_root(self.canonical)

    def basepath(self):
        # type: () -> str
        return os.path.basename(self.norm)

    def canonical_base(self):
        # type: () -> str
        return os.path.basename(self.canonical)


def is_likely_path_char(c):
    # type: (str) -> bool
    if ord(c) <= 32:  # Control character or space
        return False
    if c in '<>&|\'",;:[]()*?`=#!':  # more commonly near paths than in paths
        # some explicit decisions:
        # = is in to make ENVNAME=PATH isolate PATH
        # (#) are in to make [AWS](docs/install.md#aws) isolate path
        # ${} are out to make $ENVNAME and ${ENVNAME} part of path
        # % is out to make %ENVNAME% part of path
        return False
    return True


def find_all(pat, s):
    # (str, str) -> Iterator[int]
    i = s.find(pat)
    while i != -1:
        yield i
        i = s.find(pat, i + 1)


access = os.access
is_file = os.path.isfile

if access in os.supports_effective_ids:
    def is_readable(path):
        return access(path, os.R_OK, effective_ids=True)
else:
    def is_readable(path):
        return access(path, os.R_OK)


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


def candidates_from_string(text, folder_iterate, region=sublime.Region(0, 0)):
    # (str, Callable[[], Iterator[str]], sublime.Region) -> Iterator[Candidate]
    path = expanduser(text)
    expanded = expanduser(os.path.expandvars(text))
    if path != expanded:
        if os.path.isabs(path):
            if is_file(path):
                if is_readable(path):
                    yield FileFound(region, path)
                else:
                    print('GidOpen: - skip {}: not readable'.format(path))
            elif os.path.isdir(path):
                yield FolderFound(region, path)
            elif os.path.isdir(os.path.dirname(path)):
                yield FileNotFound(region, path)
            else:
                path = os.path.dirname(path)
                parent = os.path.dirname(path)
                while not is_path_root(path) and not os.path.isdir(parent):
                    path = parent
                    parent = os.path.dirname(path)
                yield FolderNotFound(region, path)
        else:
            for folder in folder_iterate():
                folder = str(folder)
                abspath = os.path.normpath(os.path.join(folder, path))
                if is_file(abspath):
                    if is_readable(abspath):
                        yield FileFound(region, abspath)
                    else:
                        print('GidOpen: - skip {}: not readable'.format(abspath))
                elif os.path.isdir(path):
                    yield FolderFound(region, path)

    if os.path.isabs(expanded):
        if is_file(expanded):
            if is_readable(expanded):
                yield FileFound(region, expanded)
            else:
                print('GidOpen: - skip {}: not readable'.format(expanded))
        elif os.path.isdir(expanded):
            yield FolderFound(region, expanded)
        elif os.path.isdir(os.path.dirname(expanded)):
            yield FileNotFound(region, expanded)
        else:
            path = os.path.dirname(expanded)
            parent = os.path.dirname(path)
            while not is_path_root(path) and not os.path.isdir(parent):
                path = parent
                parent = os.path.dirname(path)
            yield FolderNotFound(region, path)
    else:
        for folder in folder_iterate():
            folder = str(folder)
            abspath = os.path.normpath(os.path.join(folder, expanded))
            if is_file(abspath):
                if is_readable(abspath):
                    yield FileFound(region, abspath)
                else:
                    print('GidOpen: - skip {}: not readable'.format(abspath))
            elif os.path.isdir(abspath):
                yield FolderFound(region, abspath)


def select_longest_path(candidates):
    # type: (...) -> Candidate|None
    result = None
    maxlen = -1
    for candidate in candidates:
        length = len(candidate.path)
        if length > maxlen:
            result = candidate
            maxlen = length
    return result


def select_longest_region(candidates):
    # type: (...) -> Candidate|None
    result = None
    maxlen = -1
    for candidate in candidates:
        length = candidate.region.size()
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


def reveal_folder(window, path):
    # type: (sublime.Window, str) -> None
    # ST does not support revealing a folder, so find a file that
    # should be close to the top of the folder's file list.
    for dirpath, dirnames, filenames in os.walk(path):
        if filenames:
            # Sort filenames so we find one near the top of the folder
            names = sorted(filenames, key=str.casefold)
            filepath = os.path.join(dirpath, names[0])
            print('GidOpen: reveal', filepath)
            view = window.find_open_file(filepath)
            if view is None:
                window.open_file(filepath, 0)
            else:
                window.focus_view(view)
            window.run_command('reveal_in_side_bar')
            break
        # If the folder does not contain any files, go into the
        # subfolders in sorted order.
        dirnames.sort(key=str.casefold)


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


class gidopen_in_view(sublime_plugin.TextCommand):

    def __init__(self, view):
        # type: (sublime.View) -> None
        super().__init__(view)
        self._home = None  # type: AbsolutePath|None
        self._folders = None  # type: list[AbsolutePath]|None
        self._pwd = None  # type: AbsolutePath|None
        self._labels = None  # type: dict[AbsolutePath, str]|None
        self._folder_excludes = self.view.settings().get(
            'folder_exclude_patterns'
        )

    def _get_home(self):
        # type: () -> AbsolutePath
        if self._home is None:
            self._home = get_home()
        assert self._home is not None
        return self._home

    def _setup_folders(self):
        # type: () -> tuple[AbsolutePath, list[AbsolutePath], dict[AbsolutePath, str]]
        if self._pwd is None:
            self._folder_excludes = self.view.settings().get(
                'folder_exclude_patterns'
            )
            window = self.view.window()
            winvar = window.extract_variables()
            window_folders = [AbsolutePath(f) for f in window.folders()]
            folders = []  # type: list[AbsolutePath]
            labels = {}  # type: dict[AbsolutePath, str]
            count = collections.defaultdict(int)  # type: dict[str, int]
            for after, folder in enumerate(window_folders, start=1):
                count[folder.canonical_base()] += 1
                if any(f <= folder for f in folders):
                    # If a parent of this folder has appeared, do not keep
                    pass
                elif any(f < folder for f in window_folders[after:]):
                    # If a parent of this folder is yet to come, do not keep
                    pass
                else:
                    folders.append(folder)
            for folder in folders:
                if count[folder.canonical_base()] == 1:
                    labels[folder] = folder.basepath()
            pwd = self.view.settings().get(SETTING_PWD)
            if pwd is not None:
                pwd = expanduser(pwd)
                if os.path.isabs(pwd) and os.path.isdir(pwd):
                    pwd = AbsolutePath(pwd)
                else:
                    pwd = None
            if pwd is None:
                file = winvar.get('file')
                if file is not None:
                    pwd = AbsolutePath(os.path.dirname(file))
                elif folders:
                    pwd = folders[0]
                else:
                    pwd = self._get_home()
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
            if folder == pwd:
                pwd_is_folder = True
            elif folder < pwd:
                pwd_in_folder = True
        if pwd_in_folder:
            if yield_pwd_in_folder:
                yield pwd
        else:
            if not pwd_is_folder:
                yield pwd

    def _get_pwd(self):
        # type: () -> AbsolutePath
        pwd, folders, labels = self._setup_folders()
        return pwd

    def _expand_right(self, prefix_region, suffix):
        # type: (sublime.Region, PartialPath) -> sublime.Region|None
        begin = prefix_region.end()
        end = begin + suffix.canonical_len()
        partial = PartialPath(self.view.substr(sublime.Region(begin, end)))
        while end < self.view.size() and partial.canonical_len() < suffix.canonical_len():
            end += 1
            partial = PartialPath(self.view.substr(sublime.Region(begin, end)))
        if partial == suffix:
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
                    print('GidOpen: - skip', self._shorten_name(path))
                    del dirnames[i]
                else:
                    region = self._expand_right(folder_region, PartialPath(path[dlen:]))
                    if region:
                        yield FolderFound(region, path)
                        # descend into this folder
                        i += 1
                    else:
                        # don't descend into this folder
                        del dirnames[i]

            for filename in filenames:
                path = os.path.join(dirpath, filename)
                region = self._expand_right(folder_region, PartialPath(path[dlen:]))
                if region:
                    if is_readable(path):
                        yield FileFound(region, path)
                    else:
                        print('GidOpen: - skip {}: not readable'.format(self._shorten_name(path)))

    def all_files_prefixed_by(self, prefix, prefix_region):
        # (str, sublime.Region) -> Generator[Candidate, None, bool]
        # yield all filesystem paths that start with the
        # path `prefix`. The prefix ends at `prefix_region.end()`.
        found = False
        assert os.path.isabs(prefix)
        # split into dirname and basename prefix
        d, p = os.path.split(prefix)
        if os.path.isdir(d):
            name_prefix = os.path.normcase(p)
            for name in os.listdir(d):
                if os.path.normcase(name).startswith(name_prefix):
                    path = os.path.join(d, name)
                    suffix = PartialPath(path[len(prefix):])
                    region = self._expand_right(prefix_region, suffix)
                    if region:
                        if os.path.isdir(path):
                            if name in self._folder_excludes:
                                print('GidOpen: - skip {}: excluded folder'.format(self._shorten_name(path)))
                            else:
                                found = True
                                yield FolderFound(region, path)
                                if is_path_sep(self.view.substr(region.end())):
                                    yield from self.all_matching_descendants(
                                        path, region
                                    )
                        else:
                            if is_readable(path):
                                found = True
                                yield FileFound(region, path)
                            else:
                                print('GidOpen: - skip {}: not readable'.format(self._shorten_name(path)))
        return found

    def check_absolute_path(self, region, path):
        # (sublime.Region, str) -> Generator[Candidate, None, bool]
        found = False
        if os.path.isabs(path):
            print('GidOpen: - absolute')
            found = yield from self.all_files_prefixed_by(
                os.path.normpath(path), region
            )
        elif path[0] == '~':
            # Looks like a tilde expanded absolute path.
            print('GidOpen: - absolute')
            expanded = expanduser(path)
            if expanded != path:
                # If path starts with '~alice' but user `alice` does not exist,
                # then `expanduser` keeps the path as '~alice', in which case
                # don't treat it as an absolute path.
                found = yield from self.all_files_prefixed_by(
                    os.path.normpath(expanded), region
                )
        return found

    def _handle_click_region(self, region):
        # (Region) -> Iterator[Candidate]
        # If right-click is in a selected non-empty region, use the path
        # in the region. This allows override of the heuristic.
        selected_text = self.view.substr(region)
        yield TextFound(region, selected_text)
        yield from candidates_from_string(selected_text, self._folder_iterate, region)

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
        if not path:
            return
        end = begin + len(path)
        region = sublime.Region(begin, end)

        basename = os.path.basename(path)

        print('GidOpen: looking for %r' % path)

        if platform.system() == 'Windows' and begin >= 2 and self.view.substr(begin - 1) == ':':
            driveregion = sublime.Region(begin - 2, region.end())
            drivepath = self.view.substr(driveregion)
            found = yield from self.check_absolute_path(driveregion, drivepath)
            if found:
                return

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
            for candidate in self._search_contains(region, basename):
                candidate.region = self._expand_left(
                    candidate.region, os.path.dirname(candidate.path)
                )
                yield candidate
        else:
            # we have a / before the basename, so we can search basename*. As
            # this is faster, we do a recursive search on folders and pwd.
            basename_start = end - len(basename)
            basename_region = sublime.Region(basename_start, end)

            for candidate in self._search_prefix(basename_region, basename):
                region = self._expand_left(
                    candidate.region, os.path.dirname(candidate.path)
                )
                if region == candidate.region:
                    # A pathname-like string that only matches the basename
                    # and no parent folders is likely to be a coincidental
                    # use of similar names.  Only yield these if they have
                    # a form like `./filename`.
                    do_yield = False
                    begin = region.begin()
                    if begin == 2:
                        if self.view.substr(0) == '.' and is_path_sep(self.view.substr(1)):
                            do_yield = True
                    elif begin > 2:
                        if (
                            not is_likely_path_char(self.view.substr(begin - 3))
                            and self.view.substr(begin - 2) == '.'
                            and is_path_sep(self.view.substr(begin - 1))
                        ):
                            do_yield = True
                else:
                    candidate.region = region
                    do_yield = True

                if do_yield:
                    # Only yield candidates that match at least one directory
                    yield candidate

    def _expand_left(self, region, dirname):
        # type: (sublime.Region, str) -> sublime.Region
        # when we have a region that matches the basename, expand left to
        # find the matching directories, updating the region.
        match_start = region.begin()
        pos = match_start - 1
        while not is_path_root(dirname) and pos >= 0 and is_path_sep(self.view.substr(pos)):
            if pos >= 1 and is_path_sep(self.view.substr(pos - 1)):
                pos -= 1
                continue
            if (
                pos >= 2
                and is_path_sep(self.view.substr(sublime.Region(pos - 2, pos - 1)))
                and self.view.substr(pos - 1) == '.'
            ):
                pos -= 2
                continue
            dirname, basename = os.path.split(dirname)
            blen = len(basename)
            if pos < blen:
                break
            if PartialPath(self.view.substr(sublime.Region(pos - blen, pos))) != PartialPath(basename):
                break
            match_start = pos - blen
            pos = match_start - 1
        return sublime.Region(match_start, region.end())

    def _search_contains(self, region, basename):
        # (sublime.Region, str) -> Iterator[Candidate]
        basename_normcase = os.path.normcase(basename)
        begin = region.begin()
        for folder in self._folder_iterate():
            folder = str(folder)
            print('GidOpen: - in', self._shorten_name(folder))
            for name in os.listdir(folder):
                fullpath = os.path.join(folder, name)
                for idx in find_all(basename_normcase, os.path.normcase(name)):
                    # matched name starts `idx` chars before basename
                    text_start = begin - idx
                    text_end = text_start + len(name)
                    text_region = sublime.Region(text_start, text_end)
                    text = self.view.substr(text_region)
                    if PartialPath(text) == PartialPath(name):
                        if os.path.isdir(fullpath):
                            yield FolderFound(text_region, fullpath)
                            if is_path_sep(self.view.substr(text_end)):
                                yield from self.all_matching_descendants(
                                    fullpath, text_region
                                )
                        elif is_file(fullpath):
                            if is_readable(fullpath):
                                yield FileFound(text_region, fullpath)
                            else:
                                print('GidOpen: - skip {}: not readable'.format(self._shorten_name(fullpath)))

    def _search_prefix(self, region, basename):
        # (sublime.Region, str) -> Iterator[Candidate]
        # First, search in the folders and pwd
        basename_normcase = os.path.normcase(basename)
        for folder in self._folder_iterate():
            folder = str(folder)
            print('GidOpen: - in', self._shorten_name(folder))
            if os.path.isdir(folder):
                prefix = os.path.join(folder, basename)
                for name in os.listdir(folder):
                    if os.path.normcase(name).startswith(basename_normcase):
                        path = os.path.join(folder, name)
                        suffix = PartialPath(path[len(prefix):])
                        cregion = self._expand_right(region, suffix)
                        if cregion:
                            if os.path.isdir(path):
                                if name in self._folder_excludes:
                                    print('GidOpen: - skip {}: excluded folder'.format(self._shorten_name(path)))
                                else:
                                    yield FolderFound(cregion, path)
                            else:
                                if is_readable(path):
                                    yield FileFound(cregion, path)
                                else:
                                    print('GidOpen: - skip {}: not readable'.format(self._shorten_name(path)))

        # Second, search under folders
        home = self._get_home()
        pwd = self._get_pwd()
        for folder in self._folder_iterate(yield_pwd_in_folder=False):
            if folder <= home:
                # too big to search recursively
                continue
            folder = str(folder)

            print('GidOpen: - under', self._shorten_name(folder))
            for dirpath, dirnames, filenames in os.walk(folder):
                i = 0
                while i < len(dirnames):
                    dirname = dirnames[i]
                    path = os.path.join(dirpath, dirname)
                    if AbsolutePath(path) == pwd:
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
        return select_longest_region(options)

    def _folder_in_project(self, name):
        # type: (str) -> bool
        path = AbsolutePath(name)
        pwd, folders, labels = self._setup_folders()
        for folder in folders:
            if folder <= path:
                return True
        return False

    def _shorten_name(self, name):
        # type: (str) -> str
        path = AbsolutePath(name)
        pwd, folders, labels = self._setup_folders()

        for folder in folders:
            if folder <= path:
                label = labels.get(folder)
                if label is not None:
                    return '{}{}'.format(label, name[len(folder):])

        if platform.system() != 'Windows':
            home = self._get_home()
            if not home.is_root() and home < path:
                return '~' + name[len(home):]

        return name

    def want_event(self):
        return True

    def description(self, event):
        try:
            self._pwd = None

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

            files = []
            folders = []
            notfiles = []
            notfolders = []
            texts = []

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
                        action = CONTEXT_ACTION_FOLDER_REVEAL
                        label = self._shorten_name(path)
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

            self.view.settings().set('gidopen_in_view', (action, path))
            return '{} {}'.format(action, label)
        except Exception as e:
            traceback.print_exc()
            self.view.settings().set('gidopen_in_view', (CONTEXT_ACTION_ERROR, None))
            return 'GidOpen: {}'.format(e.__class__.__name__)

    def is_visible(self, event):
        context = self.view.settings().get('gidopen_in_view')
        return context is not None and context[0] is not None

    def is_enabled(self, event):
        context = self.view.settings().get('gidopen_in_view')
        return context is not None and context[1] is not None

    def run(self, edit, event):
        context = self.view.settings().get('gidopen_in_view')
        if context is None:
            return
        action, path = context
        window = self.view.window()
        if action == CONTEXT_ACTION_FOLDER_ADD:
            add_folder_to_project(window, path)
        elif action == CONTEXT_ACTION_FOLDER_REVEAL:
            reveal_folder(window, path)
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
        self.view.settings().set('gidopen_in_view', None)


class gidopen_in_window(sublime_plugin.WindowCommand):

    def __init__(self, window):
        # type: (sublime.Window) -> None
        super().__init__(window)
        self.action = None  # type: str|None
        self.path = ''
        self._home = None  # type: AbsolutePath|None
        self._pwd = None  # type: AbsolutePath|None
        self._folders = None  # type: list[AbsolutePath]|None
        self._labels = None  # type: dict[AbsolutePath, str]|None

    def _get_home(self):
        # type: () -> AbsolutePath
        if self._home is None:
            self._home = get_home()
        assert self._home is not None
        return self._home

    def _setup_folders(self):
        # type: () -> tuple[AbsolutePath, list[AbsolutePath], dict[AbsolutePath, str]]
        if self._pwd is None:
            window = self.window()
            winvar = window.extract_variables()
            window_folders = [AbsolutePath(f) for f in window.folders()]
            folders = []  # type: list[AbsolutePath]
            labels = {}  # type: dict[AbsolutePath, str]
            count = collections.defaultdict(int)  # type: dict[str, int]
            for after, folder in enumerate(window_folders, start=1):
                count[folder.canonical_base()] += 1
                if any(folder >= f for f in folders):
                    # If a parent of this folder has appeared, do not keep
                    pass
                elif any(folder > f for f in window_folders[after:]):
                    # If a parent of this folder is yet to come, do not keep
                    pass
                else:
                    folders.append(folder)
            for folder in folders:
                if count[folder.canonical_base()] == 1:
                    labels[folder] = folder.basepath()
            file = winvar.get('file')
            if file is not None:
                pwd = AbsolutePath(os.path.dirname(file))
            elif folders:
                pwd = folders[0]
            else:
                pwd = self._get_home()
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
            if folder == pwd:
                pwd_is_folder = True
            elif folder < pwd:
                pwd_in_folder = True
        if pwd_in_folder:
            if yield_pwd_in_folder:
                yield pwd
        else:
            if not pwd_is_folder:
                yield pwd

    def _best(self, options):
        return select_longest_path(options)

    def _folder_in_project(self, name):
        # type: (str) -> bool
        path = AbsolutePath(name)
        pwd, folders, labels = self._setup_folders()
        for folder in folders:
            if folder <= path:
                return True
        return False

    def _shorten_name(self, name):
        # type: (str) -> str
        path = AbsolutePath(name)
        pwd, folders, labels = self._setup_folders()

        for folder in folders:
            if folder <= path:
                label = labels.get(folder)
                if label is not None:
                    return '{}{}'.format(label, name[len(folder):])

        if platform.system() != 'Windows':
            home = self._get_home()
            if not home.is_root() and home < path:
                return '~' + name[len(home):]

        return name

    def description(self):
        # type: () -> str
        try:
            self.window.run_command('copy')
            text = sublime.get_clipboard()
            candidates = candidates_from_string(text, self._folder_iterate)

            files = []
            folders = []
            notfiles = []
            notfolders = []
            texts = []

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

            action = None

            candidate = self._best(files)
            if candidate is not None:
                path = candidate.path
                label = self._shorten_name(path)
                action = CONTEXT_ACTION_FILE_OPEN
            else:
                candidate = self._best(folders)
                if candidate is not None:
                    path = candidate.path
                    if self._folder_in_project(path):
                        action = CONTEXT_ACTION_FOLDER_REVEAL
                        label = self._shorten_name(path)
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
                            path = label = ''

            if action is None:
                self.action = None
                self.path = ''
                return 'GidOpen requires path to be selected here'
            else:
                self.action = action
                self.path = path
                return '{} {}'.format(action, label)
        except Exception as e:
            traceback.print_exc()
            self.action = None
            self.path = ''
            return 'GidOpen: {}'.format(e.__class__.__name__)

    def is_visible(self):
        # type: () -> bool
        return True

    def is_enabled(self):
        # type: () -> bool
        return bool(self.path)

    def run(self):
        # type: () -> None
        action = self.action
        path = self.path
        if action is None:
            return
        window = self.window
        if action == CONTEXT_ACTION_FOLDER_ADD:
            add_folder_to_project(window, path)
        elif action == CONTEXT_ACTION_FOLDER_REVEAL:
            reveal_folder(window, path)
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
        self.action = None
        self.path = ''
