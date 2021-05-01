import os
import platform
import shutil
import sys
import tempfile
from unittest import TestCase, skipIf

import sublime  # type: ignore

version = sublime.version()

gidopen = sys.modules["sublime-gidopen.gidopen"]


def shorten_name(path):
    # type: (str) -> str
    if platform.system() != 'Windows':
        home = gidopen.get_home()  # type: ignore
        if home < gidopen.AbsolutePath(path):  # type: ignore
            return '~' + path[len(home):]
    return path

class TestPartialPath(TestCase):

    def test_empty_path(self):
        p = gidopen.PartialPath('')
        self.assertEqual(str(p), '')
        self.assertEqual(len(p), 0)
        self.assertEqual(p.canonical_len(), 0)

    def test_relative_path(self):
        s = 'dir/file'
        p = gidopen.PartialPath(s)
        self.assertEqual(str(p), s)
        self.assertEqual(len(p), len(s))
        self.assertEqual(p.canonical_len(), len(s))

    def test_absolute_path(self):
        s = '/dir/file'
        p = gidopen.PartialPath(s)
        self.assertEqual(str(p), s)
        self.assertEqual(len(p), len(s))
        self.assertEqual(p.canonical_len(), len(s))

class TestExpandPath(TestCase):

    def setUp(self):
        self.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    def tearDown(self):
        if self.view:
            self.view.set_scratch(True)
            self.view.window().focus_view(self.view)
            self.view.window().run_command("close_file")

    def test_identifies_path_like_text(self):
        text = '[abc]'
        self.view.run_command('append', {'characters': text, 'force': True})
        expected = (1, len(text) - 1)
        for pos in range(expected[0], expected[1] + 1):
            self.assertEqual(
                gidopen.expand_path(self.view, pos, pos), expected
            )

    def test_expands_to_view_limits(self):
        text = 'abc'
        self.view.run_command('append', {'characters': text, 'force': True})
        expected = (0, len(text))
        for pos in range(expected[0], expected[1] + 1):
            self.assertEqual(
                gidopen.expand_path(self.view, pos, pos), expected
            )

class TestPWD(TestCase):

    def test_setting_absolute_ok(self):
        tmpdir = tempfile.gettempdir()
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, tmpdir)
            gc = gidopen.gidopen_in_view(view)
            pwd, _folders, _labels = gc._setup_folders()
            self.assertEqual(str(pwd), tmpdir)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_setting_tilde_ok(self):
        with tempfile.TemporaryDirectory(dir=os.path.expanduser('~')) as tmpdir:
            view = sublime.active_window().new_file()
            try:
                settings = view.settings()
                settings.set(gidopen.SETTING_PWD, os.path.join('~', os.path.basename(tmpdir)))
                gc = gidopen.gidopen_in_view(view)
                pwd, _folders, _labels = gc._setup_folders()
                self.assertEqual(str(pwd), tmpdir)
            finally:
                view.set_scratch(True)
                view.window().focus_view(view)
                view.window().run_command("close_file")

    def test_setting_file_fails(self):
        with tempfile.NamedTemporaryFile() as tmpfile:
            view = sublime.active_window().new_file()
            try:
                settings = view.settings()
                settings.set(gidopen.SETTING_PWD, tmpfile.name)
                gc = gidopen.gidopen_in_view(view)
                pwd, folders, _labels = gc._setup_folders()
                # setting fails, so fallback to folders[0]
                self.assertEqual(pwd, folders[0])
            finally:
                view.set_scratch(True)
                view.window().focus_view(view)
                view.window().run_command("close_file")

    def test_setting_relative_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            view = sublime.active_window().new_file()
            try:
                settings = view.settings()
                settings.set(gidopen.SETTING_PWD, os.path.basename(tmpdir))
                gc = gidopen.gidopen_in_view(view)
                pwd, folders, _labels = gc._setup_folders()
                # setting fails, so fallback to folders[0]
                self.assertEqual(pwd, folders[0])
            finally:
                view.set_scratch(True)
                view.window().focus_view(view)
                view.window().run_command("close_file")

    def test_setting_notexist_fails(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, '/nonexisting/folder')
            gc = gidopen.gidopen_in_view(view)
            pwd, folders, _labels = gc._setup_folders()
            # setting fails, so fallback to folders[0]
            self.assertEqual(pwd, folders[0])
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

class TestGidOpenPoint(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.file_absent = os.path.join(self.tmpdir, 'absent')
        self.file_present = os.path.join(self.tmpdir, 'present')
        with open(self.file_present, 'w'):
            pass
        self.also_present = os.path.join(self.tmpdir, 'also present')
        with open(self.also_present, 'w'):
            pass
        self.tilde_file = os.path.join(self.tmpdir, '~4.txt')
        with open(self.tilde_file, 'w'):
            pass
        self.atypical_file = os.path.join(self.tmpdir, 'file & ice.txt')
        with open(self.atypical_file, 'w'):
            pass

        home = os.path.expanduser('~')
        tilde_file = None
        for basename in os.listdir(home):
            if len(basename) > 2:
                path = os.path.join(home, basename)
                if os.path.isfile(path):
                    tilde_file = path
                    break
        self.assertIsNotNone(tilde_file)
        self.home_base = basename
        self.home_present = tilde_file

        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def samples_no_candidates(self):
        return (
            '   \n',              # no path characters
            self.file_absent,     # directory exists, but file does not
            '/tmp/noexist/file',  # directory does not exist
            'absent',             # relative file does not exist
            # Even though `present` does exist, the fact that even one
            # level of hierarchy doesn't match means it's more likely
            # coincidence than a real match
            'nomatch/present',
            '/tmp/nomatch/present',
        )

    def test_no_candidates(self):
        for text in self.samples_no_candidates():
            view = sublime.active_window().new_file()
            try:
                settings = view.settings()
                settings.set(gidopen.SETTING_PWD, self.tmpdir)
                gc = gidopen.gidopen_in_view(view)

                view.run_command('append', {'characters': text, 'force': True})
                for pos in range(view.size() + 1):
                    x, y = view.text_to_window(pos)
                    event = {'x': x, 'y': y}
                    gc.description(event)
                    action, path = view.settings().get('gidopen_in_view')
                    self.assertFalse(gc.is_visible(event), (text, pos))
                    self.assertEqual(action, None, (text, pos))
                    self.assertEqual(path, None, (text, pos))
            finally:
                view.set_scratch(True)
                view.window().focus_view(view)
                view.window().run_command("close_file")

    def samples_open_candidates(self):
        dirname = os.path.dirname(self.file_present)
        parent = os.path.basename(dirname)
        present = os.path.basename(self.file_present)
        return (
            (self.file_present, self.file_present),  # absolute path
            (present, self.file_present),  # basename only relative
            ('./' + present, self.file_present),  # dot-slash relative
            (parent + '/' + present, self.file_present),
            ('./' + parent + '/' + present, self.file_present),
            (parent + '/./' + present, self.file_present),
            (dirname + '/./' + present, self.file_present),
            # Can match an absolute path with different hierarchy as long as
            # basename and first parent match.  This is common:
            # - when tasks run inside containers
            # - in Go code where URL's represent the code hierarchy
            ('/notexist/' + parent + '/' + present, self.file_present),
            # A filename that starts with ~ but is not pointing to a home
            # directory can be matched
            (self.tilde_file, self.tilde_file),
            (os.path.basename(self.tilde_file), self.tilde_file),
            # Files with spaces can be matched. This also demonstrates that
            # the longer match wins (`also present` beats `present`)
            (self.also_present, self.also_present),
            (os.path.basename(self.also_present), self.also_present),
            # Files with up to three atypical characters in sequence surrounded
            # by typical characters can be matched.
            (self.atypical_file, self.atypical_file),
            (os.path.basename(self.atypical_file), self.atypical_file),
        )

    def test_open_candidates(self):
        for text, filename in self.samples_open_candidates():
            view = sublime.active_window().new_file()
            try:
                settings = view.settings()
                settings.set(gidopen.SETTING_PWD, self.tmpdir)
                gc = gidopen.gidopen_in_view(view)

                view.run_command('append', {'characters': text, 'force': True})
                if text[1] == ':':
                    # Windows path with drive
                    start = 2
                else:
                    start = 0
                for pos in range(start, view.size() + 1):
                    x, y = view.text_to_window(pos)
                    event = {'x': x, 'y': y}
                    message = gc.description(event)
                    action, path = view.settings().get('gidopen_in_view')
                    self.assertTrue(gc.is_visible(event), (text, pos))
                    self.assertEqual(
                        message, '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(filename)), (text, pos)
                    )
                    self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN, (text, pos))
                    self.assertEqual(path, filename, (text, pos))
            finally:
                view.set_scratch(True)
                view.window().focus_view(view)
                view.window().run_command("close_file")

    def test_tilde_home_existing(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)
            home_base = os.path.basename(self.home_present)

            view.run_command(
                'append', {'characters': '~/' + home_base, 'force': True}
            )
            x, y = view.text_to_window(view.size() - 2)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), '~/' + home_base)
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.home_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_unbraced_env_existing(self):
        if platform.system() == 'Windows':
            home = '$HOMEDRIVE$HOMEPATH'
        else:
            home = '$HOME'
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)
            home_base = os.path.basename(self.home_present)

            view.run_command(
                'append', {'characters': home + '/' + home_base, 'force': True}
            )
            x, y = view.text_to_window(view.size() - 2)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.home_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_braced_env_existing(self):
        if platform.system() == 'Windows':
            home = '${HOMEDRIVE}${HOMEPATH}'
        else:
            home = '${HOME}'
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)
            home_base = os.path.basename(self.home_present)

            view.run_command(
                'append', {'characters': home + '/' + home_base, 'force': True}
            )
            x, y = view.text_to_window(view.size() - 2)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.home_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    @skipIf(platform.system() != 'Windows', 'Windows-specific test')
    def test_windows_env_existing(self):
        home = '%HOMEDRIVE%%HOMEPATH%'
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)
            home_base = os.path.basename(self.home_present)

            view.run_command(
                'append', {'characters': home + '/' + home_base, 'force': True}
            )
            x, y = view.text_to_window(view.size() - 2)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.home_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_absolute_path_with_row(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)

            view.run_command(
                'append', {'characters': self.file_present + ':12', 'force': True}
            )
            x, y = view.text_to_window(view.size() - 5)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}:12'.format(
                    gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
                )
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
            self.assertEqual(path, self.file_present + ':12:0')
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_relative_path_with_row(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)

            view.run_command(
                'append', {'characters': 'present:12', 'force': True}
            )
            x, y = view.text_to_window(view.size() - 5)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}:12'.format(
                    gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
                )
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
            self.assertEqual(path, self.file_present + ':12:0')
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_absolute_path_with_row_column(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)

            view.run_command(
                'append', {
                    'characters': self.file_present + ':12:34', 'force': True
                }
            )
            x, y = view.text_to_window(view.size() - 8)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}:12:34'.format(
                    gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
                )
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
            self.assertEqual(path, self.file_present + ':12:34')
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_relative_path_with_row_column(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)

            view.run_command(
                'append', {'characters': 'present:12:34', 'force': True}
            )
            x, y = view.text_to_window(view.size() - 8)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}:12:34'.format(
                    gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
                )
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
            self.assertEqual(path, self.file_present + ':12:34')
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_file_from_set_environment_variable(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)

            view.run_command(
                'append', {
                    'characters': 'ENVNAME={}\n'.format(self.file_present),
                    'force': True
                }
            )
            x, y = view.text_to_window(view.size() - 4)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.file_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.file_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_file_at_end_of_sentence(self):
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)

            # Extra dot does not confuse matcher
            sentence = 'Open the file {}.'.format(self.file_present)
            view.run_command(
                'append', {'characters': sentence, 'force': True}
            )
            x, y = view.text_to_window(view.size() - 2)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.file_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.file_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")


class TestGidOpenRegion(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.file_absent = os.path.join(self.tmpdir, 'absent')
        self.file_present = os.path.join(self.tmpdir, 'present')
        with open(self.file_present, 'w'):
            pass
        self.also_present = os.path.join(self.tmpdir, 'also present')
        with open(self.also_present, 'w'):
            pass
        home = os.path.expanduser('~')
        tilde_file = None
        for basename in os.listdir(home):
            if len(basename) > 2:
                path = os.path.join(home, basename)
                if os.path.isfile(path):
                    tilde_file = path
                    break
        self.assertIsNotNone(tilde_file)
        self.home_base = basename
        self.home_present = tilde_file

        self.view = sublime.active_window().new_file()
        settings = self.view.settings()
        settings.set(gidopen.SETTING_PWD, self.tmpdir)
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    def tearDown(self):
        if self.view:
            self.view.set_scratch(True)
            self.view.window().focus_view(self.view)
            self.view.window().run_command("close_file")
        shutil.rmtree(self.tmpdir)

    def test_empty_area_hides_menu(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command('append', {'characters': '   \n', 'force': True})
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertEqual(action, None)
        self.assertEqual(path, None)
        self.assertFalse(gc.is_visible(event), (action, path))

    def test_absolute_path_nonexisting_file(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': self.file_absent, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_NEW)
        self.assertEqual(path, self.file_absent)
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(message, '{} {}'.format(action, shorten_name(path)))

    def test_absolute_path_nonexisting_directory(self):
        gc = gidopen.gidopen_in_view(self.view)

        tmpdir = tempfile.gettempdir()
        foldername = os.path.join(tmpdir, 'noexist')
        filename = os.path.join(foldername, 'file')

        self.view.run_command(
            'append', {'characters': filename, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FOLDER_NEW)
        self.assertEqual(path, foldername)
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(message, '{} {}'.format(action, shorten_name(path)))

    def test_relative_path_nonexisting(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': 'absent', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertFalse(gc.is_visible(event), (action, path))
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_absolute_path_existing(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': self.file_present, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)
        self.assertEqual(message, '{} {}'.format(action, shorten_name(path)))

    def test_relative_path_existing(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': 'present', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.file_present))
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_dot_slash_path_existing(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': './present', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.file_present))
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_tilde_path_existing(self):
        tilde_file = os.path.join(self.tmpdir, '~4.txt')
        with open(tilde_file, 'w'):
            pass

        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': '~4.txt', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(tilde_file))
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, tilde_file)

    def test_tilde_home_existing(self):
        gc = gidopen.gidopen_in_view(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '~' + os.sep + home_base, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_unbraced_env_existing(self):
        if platform.system() == 'Windows':
            home = '$HOMEDRIVE$HOMEPATH'
        else:
            home = '$HOME'

        gc = gidopen.gidopen_in_view(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': home + os.sep + home_base, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_braced_env_existing(self):
        if platform.system() == 'Windows':
            home = '${HOMEDRIVE}${HOMEPATH}'
        else:
            home = '${HOME}'

        gc = gidopen.gidopen_in_view(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': home + os.sep + home_base, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    @skipIf(platform.system() != 'Windows', 'Windows-specific test')
    def test_windows_env_existing(self):
        home = '%HOMEDRIVE%%HOMEPATH%'
        view = sublime.active_window().new_file()
        try:
            settings = view.settings()
            settings.set(gidopen.SETTING_PWD, self.tmpdir)
            gc = gidopen.gidopen_in_view(view)
            home_base = os.path.basename(self.home_present)

            view.run_command(
                'append', {'characters': home + '/' + home_base, 'force': True}
            )
            self.view.sel().add(sublime.Region(0, self.view.size()))

            x, y = view.text_to_window(view.size() - 2)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = view.settings().get('gidopen_in_view')
            self.assertTrue(gc.is_visible(event), (action, path))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.home_present))
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, self.home_present)
        finally:
            view.set_scratch(True)
            view.window().focus_view(view)
            view.window().run_command("close_file")

    def test_click_after_space(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': self.also_present, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.also_present)
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_click_before_space(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': self.also_present, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 12)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, shorten_name(self.also_present)
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_absolute_path_with_row(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': self.file_present + ':12', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, len(self.file_present)))

        x, y = self.view.text_to_window(self.view.size() - 5)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}:12'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:0')

    def test_relative_path_with_row(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': 'present:12', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, len('present')))

        x, y = self.view.text_to_window(self.view.size() - 5)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}:12'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:0')

    def test_absolute_path_with_row_column(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {
                'characters': self.file_present + ':12:34', 'force': True
            }
        )
        self.view.sel().add(sublime.Region(0, len(self.file_present)))
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}:12:34'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:34')

    def test_relative_path_with_row_column(self):
        gc = gidopen.gidopen_in_view(self.view)

        self.view.run_command(
            'append', {'characters': 'present:12:34', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, len('present')))

        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_in_view')
        self.assertTrue(gc.is_visible(event), (action, path))
        self.assertEqual(
            message,
            '{} {}:12:34'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, shorten_name(self.file_present)
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:34')


@skipIf(platform.system() == 'Windows', 'Cannot set non-readable file on Windows')
class TestPermissions(TestCase):

    def setUp(self):
        self.view = sublime.active_window().new_file()
        # make sure we have a window to work with
        s = sublime.load_settings("Preferences.sublime-settings")
        s.set("close_windows_when_empty", False)

    def tearDown(self):
        if self.view:
            self.view.set_scratch(True)
            self.view.window().focus_view(self.view)
            self.view.window().run_command("close_file")

    def test_file_not_readable_point(self):
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o000)
            assert not gidopen.is_readable(f.name)
            gc = gidopen.gidopen_in_view(self.view)

            self.view.run_command(
                'append', {'characters': f.name, 'force': True}
            )

            x, y = self.view.text_to_window(self.view.size() - 8)
            event = {'x': x, 'y': y}
            gc.description(event)
            action, path = self.view.settings().get('gidopen_in_view')
            self.assertFalse(gc.is_visible(event), (action, path))
            self.assertEqual(action, None)
            self.assertEqual(path, None)

    def test_file_not_readable_region(self):
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, 0o000)
            assert not gidopen.is_readable(f.name)
            gc = gidopen.gidopen_in_view(self.view)

            self.view.run_command(
                'append', {'characters': f.name, 'force': True}
            )
            self.view.sel().add(sublime.Region(0, len(f.name)))

            x, y = self.view.text_to_window(self.view.size() - 8)
            event = {'x': x, 'y': y}
            gc.description(event)
            action, path = self.view.settings().get('gidopen_in_view')
            self.assertFalse(gc.is_visible(event), (action, path))
            self.assertEqual(action, None)
            self.assertEqual(path, None)
