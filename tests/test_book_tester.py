from lxml import html
from mock import Mock
import os
import shutil
import tempfile
from textwrap import dedent
import unittest

from book_tester import (
    ChapterTest,
    CodeListing,
    Command,
    Output,
    get_commands,
    parse_listing,
    wrap_long_lines,
    write_to_file,
)
from examples import CODE_LISTING_WITH_CAPTION

class WrapLongLineTest(unittest.TestCase):

    def test_wrap_long_lines_with_words(self):
        self.assertEqual(wrap_long_lines('normal line'), 'normal line')
        text = (
            "This is a short line\n"
            "This is a long line which should wrap just before the word that "
            "takes it over 79 chars in length\n"
            "This line is fine though."
        )
        expected_text = (
            "This is a short line\n"
            "This is a long line which should wrap just before the word that "
            "takes it over\n"
            "79 chars in length\n"
            "This line is fine though."
        )
        self.assertMultiLineEqual(wrap_long_lines(text), expected_text)


    def test_wrap_long_lines_with_unbroken_chars(self):
        text = "." * 479
        expected_text = (
                "." * 79 + "\n" +
                "." * 79 + "\n" +
                "." * 79 + "\n" +
                "." * 79 + "\n" +
                "." * 79 + "\n" +
                "." * 79 + "\n" +
                "....."
        )

        self.assertMultiLineEqual(wrap_long_lines(text), expected_text)


    def test_wrap_long_lines_with_indent(self):
        text = (
            "This is a short line\n"
            "   This is a long line with an indent which should wrap just "
            "before the word that takes it over 79 chars in length\n"
            "   This is a short indented line\n"
            "This is a long line which should wrap just before the word that "
            "takes it over 79 chars in length\n"
        )
        expected_text = (
            "This is a short line\n"
            "   This is a long line with an indent which should wrap just "
            "before the word\n"
            "that takes it over 79 chars in length\n"
            "   This is a short indented line\n"
            "This is a long line which should wrap just before the word that "
            "takes it over\n"
            "79 chars in length"
        )
        self.assertMultiLineEqual(wrap_long_lines(text), expected_text)


class ParseListingTest(unittest.TestCase):

    def test_recognises_code_listings(self):
        code_listing = CODE_LISTING_WITH_CAPTION.replace('\n', '\r\n')
        listing_only = html.fromstring(code_listing).cssselect('div.listingblock')[0]
        listings = parse_listing(listing_only)
        self.assertEqual(len(listings), 1)
        listing = listings[0]
        self.assertEqual(type(listing), CodeListing)
        self.assertEqual(listing.filename, 'functional_tests.py')
        self.assertEqual(
            listing.contents,
            dedent(
                """
                from selenium import webdriver

                browser = webdriver.Firefox()
                browser.get('http://localhost:8000')

                assert 'Django' in browser.title
                """
            ).strip()
        )
        self.assertFalse('\r' in listing.contents)


    def test_can_extract_one_command_and_its_output(self):
        listing = html.fromstring(
            '<div class="listingblock">\r\n'
            '<div class="content">\r\n'
            '<pre><code>$ <strong>python functional_tests.py</strong>\r\n'
            'Traceback (most recent call last):\r\n'
            '  File "functional_tests.py", line 6, in &lt;module&gt;\r\n'
            '    assert \'Django\' in browser.title\r\n'
            'AssertionError</code></pre>\r\n'
            '</div></div>&#13;\n'
        )
        listing.getnext = Mock()
        parsed_listings = parse_listing(listing)
        self.assertEqual(
            parsed_listings,
            [
                'python functional_tests.py',
                'Traceback (most recent call last):\n'
                '  File "functional_tests.py", line 6, in <module>\n'
                '    assert \'Django\' in browser.title\n'
                'AssertionError'
            ]
        )
        self.assertEqual(type(parsed_listings[0]), Command)
        self.assertEqual(type(parsed_listings[1]), Output)


    def test_extracting_multiple(self):
        listing = html.fromstring(
            '<div class="listingblock">\r\n'
            '<div class="content">\r\n'
            '<pre><code>$ <strong>ls</strong>\r\n'
            'superlists          functional_tests.py\r\n'
            '$ <strong>mv functional_tests.py superlists/</strong>\r\n'
            '$ <strong>cd superlists</strong>\r\n'
            '$ <strong>git init .</strong>\r\n'
            'Initialized empty Git repository in /chapter_1/superlists/.git/</code></pre>\r\n'
            '</div></div>&#13;\n'
        )
        listing.getnext = Mock()
        parsed_listings = parse_listing(listing)
        self.assertEqual(
            parsed_listings,
            [
                'ls',
                'superlists          functional_tests.py',
                'mv functional_tests.py superlists/',
                'cd superlists',
                'git init .',
                'Initialized empty Git repository in /chapter_1/superlists/.git/'
            ]
        )
        self.assertEqual(type(parsed_listings[0]), Command)
        self.assertEqual(type(parsed_listings[1]), Output)
        self.assertEqual(type(parsed_listings[2]), Command)
        self.assertEqual(type(parsed_listings[3]), Command)
        self.assertEqual(type(parsed_listings[4]), Command)
        self.assertEqual(type(parsed_listings[5]), Output)


    def test_post_command_comment_with_multiple_spaces(self):
        listing = html.fromstring(
            '<div class="listingblock">'
            '<div class="content">'
            '<pre><code>$ <strong>git diff</strong>  # should show changes to functional_tests.py\n'
            '$ <strong>git commit -am "Functional test now checks we can input a to-do item"</strong></code></pre>'
            '</div></div>&#13;'
        )
        listing.getnext = Mock()
        commands = get_commands(listing)
        self.assertEqual(
            commands,
            [
                'git diff',
                'git commit -am "Functional test now checks we can input a to-do item"',
            ]
        )

        parsed_listings = parse_listing(listing)
        self.assertEqual(
            parsed_listings,
            [
                'git diff',
                '# should show changes to functional_tests.py',
                'git commit -am "Functional test now checks we can input a to-do item"',
            ]
        )
        self.assertEqual(type(parsed_listings[0]), Command)
        self.assertEqual(type(parsed_listings[1]), Output)
        self.assertEqual(type(parsed_listings[2]), Command)



    def test_specialcase_for_asterisk(self):
        listing = html.fromstring(
            '<div class="listingblock">\r\n<div class="content">\r\n<pre><code>$ <strong>git rm --cached superlists/</strong>*<strong>.pyc</strong>\r\nrm <em>superlists/__init__.pyc</em>\r\nrm <em>superlists/settings.pyc</em>\r\nrm <em>superlists/urls.pyc</em>\r\nrm <em>superlists/wsgi.pyc</em>\r\n\r\n$ <strong>echo "*.pyc" &gt; .gitignore</strong></code></pre>\r\n</div></div>&#13;\n'
        )
        self.assertEqual(
            get_commands(listing),
            [
                'git rm --cached superlists/*.pyc',
                'echo "*.pyc" > .gitignore',
            ]
        )


    def test_catches_command_with_trailing_comment(self):
        listing = html.fromstring(
            dedent("""
                <div class="listingblock">
                    <div class="content">
                        <pre><code>$ <strong>git diff --staged</strong> # will show you the diff that you're about to commit
                </code></pre>
                </div></div>
                """)
        )
        listing.getnext = Mock()
        parsed_listings = parse_listing(listing)
        self.assertEqual(
            parsed_listings,
            [
                "git diff --staged",
                "# will show you the diff that you're about to commit",
            ]
        )
        self.assertEqual(type(parsed_listings[0]), Command)
        self.assertEqual(type(parsed_listings[1]), Output)


class GetCommandsTest(unittest.TestCase):

    def test_extracting_one_command(self):
        listing = html.fromstring(
            '<div class="listingblock">\r\n<div class="content">\r\n<pre><code>$ <strong>python functional_tests.py</strong>\r\nTraceback (most recent call last):\r\n  File "functional_tests.py", line 6, in &lt;module&gt;\r\n    assert \'Django\' in browser.title\r\nAssertionError</code></pre>\r\n</div></div>&#13;\n'
        )
        self.assertEqual(
            get_commands(listing),
            ['python functional_tests.py']
        )

    def test_extracting_multiple(self):
        listing = html.fromstring(
            '<div class="listingblock">\r\n<div class="content">\r\n<pre><code>$ <strong>ls</strong>\r\nsuperlists          functional_tests.py\r\n$ <strong>mv functional_tests.py superlists/</strong>\r\n$ <strong>cd superlists</strong>\r\n$ <strong>git init .</strong>\r\nInitialized empty Git repository in /chapter_1/superlists/.git/</code></pre>\r\n</div></div>&#13;\n'
        )
        self.assertEqual(
            get_commands(listing),
            [
                'ls',
                'mv functional_tests.py superlists/',
                'cd superlists',
                'git init .',
            ]
        )


    def test_specialcase_for_asterisk(self):
        listing = html.fromstring(
            '<div class="listingblock">\r\n<div class="content">\r\n<pre><code>$ <strong>git rm --cached superlists/</strong>*<strong>.pyc</strong>\r\nrm <em>superlists/__init__.pyc</em>\r\nrm <em>superlists/settings.pyc</em>\r\nrm <em>superlists/urls.pyc</em>\r\nrm <em>superlists/wsgi.pyc</em>\r\n\r\n$ <strong>echo "*.pyc" &gt; .gitignore</strong></code></pre>\r\n</div></div>&#13;\n'
        )
        self.assertEqual(
            get_commands(listing),
            [
                'git rm --cached superlists/*.pyc',
                'echo "*.pyc" > .gitignore',
            ]
        )



class WriteToFileTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_simple_case(self):
        listing = CodeListing(filename='foo.py', contents='abc\ndef')
        write_to_file(listing, self.tempdir)
        with open(os.path.join(self.tempdir, listing.filename)) as f:
            self.assertEqual(f.read(), listing.contents + '\n')
        self.assertTrue(listing.was_written)


    def test_strips_line_callouts(self):
        listing = CodeListing(
            filename='foo.py',
            contents= 'hello\nbla bla #\n'
        )
        write_to_file(listing, self.tempdir)
        with open(os.path.join(self.tempdir, listing.filename)) as f:
            self.assertEqual(f.read(), 'hello\nbla bla\n')


    def assert_write_to_file_gives(
        self, old_contents, new_contents, expected_contents
    ):
        listing = CodeListing(filename='foo.py', contents=new_contents)
        with open(os.path.join(self.tempdir, 'foo.py'), 'w') as f:
            f.write(old_contents)

        write_to_file(listing, self.tempdir)

        with open(os.path.join(self.tempdir, listing.filename)) as f:
            self.assertMultiLineEqual(f.read(), expected_contents)


    def test_existing_file_bears_no_relation_means_replaced(self):
        old = '#abc\n#def\n#ghi\n#jkl\n'
        new = '#mno\n#pqr\n#stu\n#vvv\n'
        expected = new
        self.assert_write_to_file_gives(old, new, expected)


    def test_with_new_contents_then_indented_elipsis_then_appendix(self):
        old = '#abc\n#def\n#ghi\n#jkl\n'
        new = (
            '#abc\n'
            'def foo(v):\n'
            '    return v + 1\n'
            '    #def\n'
            '    [... old stuff as before]\n'
            '# then add this'
        )
        expected = (
            '#abc\n'
            'def foo(v):\n'
            '    return v + 1\n'
            '    #def\n'
            '    #ghi\n'
            '    #jkl\n'
            '# then add this\n'
        )
        self.assert_write_to_file_gives(old, new, expected)


    def test_for_existing_file_replaces_matching_lines(self):
        old = dedent("""
            class Foo(object):
                def method_1(self):
                    return 1

                def method_2(self):
                    # two
                    return 2
            """
        ).lstrip()
        new = dedent("""
                def method_2(self):
                    # two
                    return 'two'
                """
        ).strip()
        expected = dedent("""
            class Foo(object):
                def method_1(self):
                    return 1

                def method_2(self):
                    # two
                    return 'two'
            """
        ).lstrip()
        self.assert_write_to_file_gives(old, new, expected)


    def test_for_existing_file_doesnt_swallow_whitespace(self):
        old = dedent("""
            one = (
                1,
            )

            two = (
                2,
            )

            three = (
                3,
            )
            """).lstrip()
        new = dedent("""
            two = (
                2,
                #two
            )
            """
        ).strip()


        expected = dedent("""
            one = (
                1,
            )

            two = (
                2,
                #two
            )

            three = (
                3,
            )
            """
        ).lstrip()
        self.assert_write_to_file_gives(old, new, expected)


    def test_longer_new_file_starts_replacing_from_first_different_line(self):
        old = dedent("""
            # line 1
            # line 2
            # line 3

            """
        ).lstrip()
        new = dedent("""
            # line 1
            # line 2

            # line 3

            # line 4
            """
        ).strip()
        expected = dedent("""
            # line 1
            # line 2

            # line 3

            # line 4
            """
        ).lstrip()
        self.assert_write_to_file_gives(old, new, expected)


    def test_for_existing_file_inserting_new_lines_between_comments(self):
        old = dedent("""
            # test 1
            a = foo()
            assert  a == 1

            if a:
                # test 2
                self.fail('finish me')

                # test 3

                # the end
            # is here
            """).lstrip()
        new = dedent("""
            # test 2
            b = bar()
            assert b == 2

            # test 3
            assert True
            self.fail('finish me')

            # the end
            [...]
            """
        ).lstrip()

        expected = dedent("""
            # test 1
            a = foo()
            assert  a == 1

            if a:
                # test 2
                b = bar()
                assert b == 2

                # test 3
                assert True
                self.fail('finish me')

                # the end
            # is here
            """
        ).lstrip()
        self.assert_write_to_file_gives(old, new, expected)


    def test_with_single_line_assertion_replacement(self):
        old = dedent("""
            class Wibble(unittest.TestCase):

                def test_number_1(self):
                    self.assertEqual(1 + 1, 2)
            """
        ).lstrip()

        new = dedent("""
                self.assertEqual(1 + 1, 3)
                """
        ).strip()

        expected = dedent("""
            class Wibble(unittest.TestCase):

                def test_number_1(self):
                    self.assertEqual(1 + 1, 3)
            """
        ).lstrip()
        self.assert_write_to_file_gives(old, new, expected)


    def test_changing_function_signature_and_stripping_comment(self):
        old = dedent(
            """
            # stuff

            def foo():
                pass
            """
        ).lstrip()

        new = dedent(
            """
            def foo(bar):
                pass
            """
        ).strip()

        expected = new + '\n'
        self.assert_write_to_file_gives(old, new, expected)


    def test_with_two_elipsis_dedented_change(self):
        old = dedent("""
            class Wibble(object):

                def foo(self):
                    return 2

                def bar(self):
                    return 3
            """).lstrip()

        new = dedent("""
                [...]
                def foo(self):
                    return 4

                def bar(self):
                [...]
                """
        ).strip()

        expected = dedent("""
            class Wibble(object):

                def foo(self):
                    return 4

                def bar(self):
                    return 3
            """
        ).lstrip()
        self.assert_write_to_file_gives(old, new, expected)



class ChapterTestTest(ChapterTest):

    def test_assert_console_output_correct_simple_case(self):
        actual = 'foo'
        expected = Output('foo')
        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_ignores_test_run_times_and_test_dashes(self):
        actual =dedent("""
            bla bla bla

            ----------------------------------------------------------------------
            Ran 1 test in 1.343s
            """).strip()
        expected = Output(dedent("""
            bla bla bla

             ---------------------------------------------------------------------
            Ran 1 test in 1.456s
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_handles_elipsis(self):
        actual =dedent("""
            bla
            bla bla
            loads more stuff
            """).strip()
        expected = Output(dedent("""
            bla
            bla bla
            [...]
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_with_start_elipsis_and_OK(self):
        actual =dedent("""
            bla

            OK

            and some epilogue
            """).strip()
        expected = Output(dedent("""
            [...]
            OK
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)

    def test_assert_console_output_correct_with_start_elipsis_and_end_longline_elipsis(self):
        actual =dedent("""
            bla
            bla bla
            loads more stuff
                raise MyException('eek')
            MyException: a really long exception, which will eventually wrap into multiple lines, so much so that it gets boring after a while...

            and then there's some stuff afterwards we don't care about
            """).strip()
        expected = Output(dedent("""
            [...]
            MyException: a really long exception, which will eventually wrap into multiple
            lines, so much so that [...]
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_ignores_diff_indexes(self):
        actual =dedent("""
            diff --git a/functional_tests.py b/functional_tests.py
            index d333591..1f55409 100644
            --- a/functional_tests.py
            """).strip()
        expected = Output(dedent("""
            diff --git a/functional_tests.py b/functional_tests.py
            index d333591..b0f22dc 100644
            --- a/functional_tests.py
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_ignores_git_commit_numers_in_logs(self):
        actual =dedent("""
            ea82222 Basic view now returns minimal HTML
            7159049 First unit test and url mapping, dummy view
            edba758 Add app for lists, with deliberately failing unit test
            """).strip()
        expected = Output(dedent("""
            a6e6cc9 Basic view now returns minimal HTML
            450c0f3 First unit test and url mapping, dummy view
            ea2b037 Add app for lists, with deliberately failing unit test
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)

        actual =dedent("""
            abc Basic view now returns minimal HTML
            123 First unit test and url mapping, dummy view
            """).strip()
        expected = Output(dedent("""
            bad Basic view now returns minimal HTML
            456 First unit test and url mapping, dummy view
            """).strip()
        )

        with self.assertRaises(AssertionError):
            self.assert_console_output_correct(actual, expected)


    def test_assert_console_output_correct_fixes_stdout_stderr_for_creating_db(self):
        actual = dedent("""
            ======================================================================
            FAIL: test_basic_addition (lists.tests.SimpleTest)
            ----------------------------------------------------------------------
            Traceback etc

            ----------------------------------------------------------------------
            Ran 1 tests in X.Xs

            FAILED (failures=1)
            Creating test database for alias 'default'...
            Destroying test database for alias 'default'
            """).strip()

        expected = Output(dedent("""
            Creating test database for alias 'default'...
            ======================================================================
            FAIL: test_basic_addition (lists.tests.SimpleTest)
            ----------------------------------------------------------------------
            Traceback etc

            ----------------------------------------------------------------------
            Ran 1 tests in X.Xs

            FAILED (failures=1)
            Destroying test database for alias 'default'
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)

    def test_assert_console_output_correct_handles_long_lines(self):
        actual = dedent("""
            A normal line
                An indented line, that's longer than 80 chars. it goes on for a while you see.
                a normal indented line
            """).strip()

        expected = Output(dedent("""
            A normal line
                An indented line, that's longer than 80 chars. it goes on for a while you
            see.
                a normal indented line
            """).strip()
        )

        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_for_minimal_expected(self):
        actual = dedent("""
            Creating test database for alias 'default'...
            E
            ======================================================================
            ERROR: test_root_url_resolves_to_home_page_view (lists.tests.HomePageTest)
            ----------------------------------------------------------------------
            Traceback (most recent call last):
              File "/workspace/superlists/lists/tests.py", line 8, in test_root_url_resolves_to_home_page_view
                found = resolve('/')
              File "/usr/local/lib/python2.7/dist-packages/django/core/urlresolvers.py", line 440, in resolve
                return get_resolver(urlconf).resolve(path)
              File "/usr/local/lib/python2.7/dist-packages/django/core/urlresolvers.py", line 104, in get_callable
                (lookup_view, mod_name))
            ViewDoesNotExist: Could not import superlists.views.home. Parent module superlists.views does not exist.
            ----------------------------------------------------------------------
            Ran 1 tests in X.Xs

            FAILED (errors=1)
            Destroying test database for alias 'default'...
            """.strip()
        )

        expected = Output(dedent(
            """
            ViewDoesNotExist: Could not import superlists.views.home. Parent module
            superlists.views does not exist.
            """).strip()
        )
        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)


    def test_assert_console_output_correct_for_long_traceback(self):
        with open(os.path.join(os.path.dirname(__file__), "actual_manage_py_test.output")) as f:
            actual = f.read().strip()
        expected = Output(dedent("""
            [... lots and lots of traceback]

            Traceback (most recent call last):
              File "/usr/local/lib/python2.7/dist-packages/django/test/testcases.py",
             line 259, in __call__
                self._pre_setup()
              File "/usr/local/lib/python2.7/dist-packages/django/test/testcases.py",
             line 479, in _pre_setup
                self._fixture_setup()
              File "/usr/local/lib/python2.7/dist-packages/django/test/testcases.py",
             line 829, in _fixture_setup
                if not connections_support_transactions():
              File "/usr/local/lib/python2.7/dist-packages/django/test/testcases.py",
             line 816, in connections_support_transactions
                for conn in connections.all())
              File "/usr/local/lib/python2.7/dist-packages/django/test/testcases.py",
             line 816, in <genexpr>
                for conn in connections.all())
              File "/usr/local/lib/python2.7/dist-packages/django/utils/functional.py",
             line 43, in __get__
                res = instance.__dict__[self.func.__name__] = self.func(instance)
              File "/usr/local/lib/python2.7/dist-packages/django/db/backends/__init__.py",
             line 442, in supports_transactions
                self.connection.enter_transaction_management()
              File "/usr/local/lib/python2.7/dist-packages/django/db/backends/dummy/base.py",
             line 15, in complain
                raise ImproperlyConfigured("settings.DATABASES is improperly configured. "
            ImproperlyConfigured: settings.DATABASES is improperly configured. Please
            supply the ENGINE value. Check settings documentation for more details.

             ---------------------------------------------------------------------
            Ran 85 tests in 0.788s

            FAILED (errors=404, skipped=1)
            AttributeError: _original_allowed_hosts
            """).strip()
        )
        self.assert_console_output_correct(actual, expected)
        self.assertTrue(expected.was_checked)

if __name__ == '__main__':
    unittest.main()
