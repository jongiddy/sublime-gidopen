import os
import shutil
import sys
import tempfile
from unittest import TestCase

import sublime

version = sublime.version()

gidopen = sys.modules["sublime-gidopen.gidopen"]

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
        home = os.environ['HOME']
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
        settings.set('gidopen_pwd', self.tmpdir)
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
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command('append', {'characters': '   \n', 'force': True})
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        self.assertFalse(gc.is_visible(event))
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_absolute_path_nonexisting_file(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.file_absent, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        self.assertFalse(gc.is_visible(event))
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_absolute_path_nonexisting_directory(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': '/tmp/noexist/file', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        gc.description(event)
        self.assertFalse(gc.is_visible(event))
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_relative_path_nonexisting(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'absent', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        self.assertFalse(gc.is_visible(event))
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_absolute_path_existing(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.file_present, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_relative_path_existing(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'present', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_dot_slash_path_existing(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': './present', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_match_partial_path(self):
        gc = gidopen.gidopen_context(self.view)

        parent = os.path.basename(os.path.dirname(self.file_present))

        self.view.run_command(
            'append', {'characters': parent + '/present', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_match_partial_path_and_mismatch(self):
        # A path can start with different parents, as long as the basename and
        # its parent are present.
        gc = gidopen.gidopen_context(self.view)

        parent = os.path.basename(os.path.dirname(self.file_present))

        self.view.run_command(
            'append',
            {'characters': '/notexist/' + parent + '/present', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_match_basename_only(self):
        # If the view text is a path containing a slash, then we don't match
        # only on the basename.  We need at least one directory to match.
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'nomatch/present', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertFalse(gc.is_visible(event))
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_tilde_path_existing(self):
        tilde_file = os.path.join(self.tmpdir, '~4.txt')
        with open(tilde_file, 'w'):
            pass

        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': '~4.txt', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, tilde_file)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, tilde_file)

    def test_tilde_home_existing(self):
        gc = gidopen.gidopen_context(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '~/' + home_base, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} ~/{}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, home_base)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_unbraced_env_existing(self):
        gc = gidopen.gidopen_context(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '$HOME/' + home_base, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} ~/{}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, home_base)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_braced_env_existing(self):
        gc = gidopen.gidopen_context(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '${HOME}/' + home_base, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} ~/{}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, home_base)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_click_after_space(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.also_present, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, self.also_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_click_before_space(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.also_present, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 12)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, self.also_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_return_longer_of_two_names(self):
        # Clicking on point that matches two names returns the longer name
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'also present', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, self.also_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_absolute_path_with_row(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.file_present + ':12', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 5)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:0')

    def test_relative_path_with_row(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'present:12', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 5)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:0')

    def test_absolute_path_with_row_column(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {
                'characters': self.file_present + ':12:34', 'force': True
            }
        )
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12:34'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:34')

    def test_relative_path_with_row_column(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'present:12:34', 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12:34'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:34')

    def test_file_from_set_environment_variable(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {
                'characters': 'ENVNAME={}\n'.format(self.file_present),
                'force': True
            }
        )
        x, y = self.view.text_to_window(self.view.size() - 4)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_file_at_end_of_sentence(self):
        gc = gidopen.gidopen_context(self.view)

        # Extra dot does not confuse matcher
        sentence = 'Open the file {}.'.format(self.file_present)
        self.view.run_command(
            'append', {'characters': sentence, 'force': True}
        )
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_two_atypical_characters(self):
        # Create a file with two atypical path characters (` [`) in a row.
        # Test that a path with multiple atypical characters can be found
        # even when the click occurs between the two atypical characters
        filename = os.path.join(self.tmpdir, 'file [x86].txt')
        with open(filename, 'w'):
            pass

        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': filename, 'force': True}
        )
        for pos in range(self.view.size() + 1):
            x, y = self.view.text_to_window(pos)
            event = {'x': x, 'y': y}
            message = gc.description(event)
            action, path = self.view.settings().get('gidopen_context')
            self.assertTrue(gc.is_visible(event))
            self.assertEqual(
                message,
                '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, filename),
                (filename[:pos], filename[pos:])
            )
            self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
            self.assertEqual(path, filename)


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
        home = os.environ['HOME']
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
        settings.set('gidopen_pwd', self.tmpdir)
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
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command('append', {'characters': '   \n', 'force': True})
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, None)
        self.assertEqual(path, None)
        self.assertFalse(gc.is_visible(event))

    def test_absolute_path_nonexisting_file(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.file_absent, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_NEW)
        self.assertEqual(path, self.file_absent)
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(message, '{} {}'.format(action, path))

    def test_absolute_path_nonexisting_directory(self):
        gc = gidopen.gidopen_context(self.view)

        foldername = '/tmp/noexist'
        filename = os.path.join(foldername, 'file')

        self.view.run_command(
            'append', {'characters': filename, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FOLDER_NEW)
        self.assertEqual(path, foldername)
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(message, '{} {}'.format(action, path))

    def test_relative_path_nonexisting(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'absent', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))
        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        gc.description(event)
        self.assertFalse(gc.is_visible(event))
        action, path = self.view.settings().get('gidopen_context')
        self.assertEqual(action, None)
        self.assertEqual(path, None)

    def test_absolute_path_existing(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.file_present, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)
        self.assertEqual(message, '{} {}'.format(action, path))

    def test_relative_path_existing(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'present', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_dot_slash_path_existing(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': './present', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, self.file_present)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.file_present)

    def test_tilde_path_existing(self):
        tilde_file = os.path.join(self.tmpdir, '~4.txt')
        with open(tilde_file, 'w'):
            pass

        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': '~4.txt', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, tilde_file)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, tilde_file)

    def test_tilde_home_existing(self):
        gc = gidopen.gidopen_context(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '~/' + home_base, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} ~/{}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, home_base)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_unbraced_env_existing(self):
        gc = gidopen.gidopen_context(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '$HOME/' + home_base, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} ~/{}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, home_base)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_braced_env_existing(self):
        gc = gidopen.gidopen_context(self.view)
        home_base = os.path.basename(self.home_present)

        self.view.run_command(
            'append', {'characters': '${HOME}/' + home_base, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} ~/{}'.format(gidopen.CONTEXT_ACTION_FILE_OPEN, home_base)
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.home_present)

    def test_click_after_space(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.also_present, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 2)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, self.also_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_click_before_space(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.also_present, 'force': True}
        )
        self.view.sel().add(sublime.Region(0, self.view.size()))

        x, y = self.view.text_to_window(self.view.size() - 12)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}'.format(
                gidopen.CONTEXT_ACTION_FILE_OPEN, self.also_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_OPEN)
        self.assertEqual(path, self.also_present)

    def test_absolute_path_with_row(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': self.file_present + ':12', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, len(self.file_present)))

        x, y = self.view.text_to_window(self.view.size() - 5)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:0')

    def test_relative_path_with_row(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'present:12', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, len('present')))

        x, y = self.view.text_to_window(self.view.size() - 5)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:0')

    def test_absolute_path_with_row_column(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {
                'characters': self.file_present + ':12:34', 'force': True
            }
        )
        self.view.sel().add(sublime.Region(0, len(self.file_present)))
        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12:34'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:34')

    def test_relative_path_with_row_column(self):
        gc = gidopen.gidopen_context(self.view)

        self.view.run_command(
            'append', {'characters': 'present:12:34', 'force': True}
        )
        self.view.sel().add(sublime.Region(0, len('present')))

        x, y = self.view.text_to_window(self.view.size() - 8)
        event = {'x': x, 'y': y}
        message = gc.description(event)
        action, path = self.view.settings().get('gidopen_context')
        self.assertTrue(gc.is_visible(event))
        self.assertEqual(
            message,
            '{} {}:12:34'.format(
                gidopen.CONTEXT_ACTION_FILE_GOTO, self.file_present
            )
        )
        self.assertEqual(action, gidopen.CONTEXT_ACTION_FILE_GOTO)
        self.assertEqual(path, self.file_present + ':12:34')
