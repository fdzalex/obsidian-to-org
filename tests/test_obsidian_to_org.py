"""Tests for obsidian-to-org."""

import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
import sys
import os
from collections import defaultdict

sys.path.append(os.path.abspath("src"))

from obsidian_to_org.__main__ import (
    convert_markdown_file,
    fix_links,
    fix_markdown_comments,
    fix_markdown_code_blocks,
    get_keys,
)


def convert_file(markdown_contents):
    """Wrapper function to convert markdown text to org text."""
    with tempfile.NamedTemporaryFile("w+") as markdown_file:
        markdown_file.write(markdown_contents)
        markdown_file.flush()

        with tempfile.TemporaryDirectory() as output_dir:
            org_file = Path(output_dir) / "example.org"
            convert_markdown_file(Path(markdown_file.name), org_file)
            return org_file.read_text()


def test_convert_markdown_file():
    markdown = dedent(
        """
    # Title

    This is a paragraph.

    Hello <!-- inline comment --> world.

    %%
    This is a block comment
    %%

    ---
    New hidden section.
    """
    )
    expected = dedent(
        """\
    * Title
    This is a paragraph.

    Hello world.

    # This is a block comment

    --------------

    New hidden section.
    """
    )
    org = convert_file(markdown)
    assert org == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("foo", "foo"),
        ("before %%comment%% after", "before <!--comment--> after"),
        (
            dedent(
                """
            %%
            multiline
            comment
            %%
            """
            ),
            dedent(
                """
            #!#comment:multiline
            #!#comment:comment

            """
            ),
        ),
    ],
)
def test_fix_markown_comments(input_text, expected):
    assert expected == fix_markdown_comments(input_text)


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("foo", "foo"),
        ("[[This is a file]]", "[[file:This is a file.org][This is a file]]"),
        (
            "[[This is a file|This is a description]]",
            "[[file:This is a file.org][This is a description]]",
        ),
        (
            "[[http://example.com][This is an example]]",
            "[[http://example.com][This is an example]]",
        ),
        (
            "[[example.png]]",
            "[[org-roam-images:example.png]]",
        ),
        (
            "[[attachments/example.png]]",
            "[[org-roam-images:example.png]]",
        ),
        (
            dedent(
                """
                [[This is a file]]
                [[This is a file|This is a description]]
                [[http://example.com][This is an example]]
                ![[FGF2 Levels - PCGM - No Collection - Kira 20220905__A1_D1.0.png]]
                [[example.png]]
                """
            ),
            dedent(
                """
                [[file:This is a file.org][This is a file]]
                [[file:This is a file.org][This is a description]]
                [[http://example.com][This is an example]]
                [[org-roam-images:FGF2 Levels - PCGM - No Collection - Kira 20220905__A1_D1.0.png]]
                [[org-roam-images:example.png]]
                """
            ),
        ),
    ],
)
def test_fix_links(input_text, expected):
    assert expected == fix_links(input_text)


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("foo", "foo"),
        ("`text`", "`text`"),
        (
            dedent(
                """
            ```run-python
                print('hello')
            ```
            """
            ),
            dedent(
                """
            ```python
                print('hello')
            ```
            """
            ),
        ),
        (
            dedent(
                """
            ```sh
                ls -lt
            ```
            """
            ),
            dedent(
                """
            ```shell
                ls -lt
            ```
            """
            ),
        ),
    ],
)
def test_fix_markown_code_blocks(input_text, expected):
    assert expected == fix_markdown_code_blocks(input_text)


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("foo", defaultdict(lambda: None)),
        (
            dedent(
                """\
            ---
            title: "Test Title"
            aliases: ["foo bar" bar]
            tags: [tag1 tag2]
            ---

            # Sample text here.
            """
            ),
            defaultdict(
                lambda: None,
                {
                    "title": '"Test Title"',
                    "aliases": ['"foo bar"', "bar"],
                    "tags": ["tag1", "tag2"],
                },
            ),
        ),
        (
            dedent(
                """\
            ---
            title: Test Title
            aliases: foo
            tags: tag1
            ---
            """
            ),
            defaultdict(
                lambda: None,
                {
                    "title": "Test Title",
                    "aliases": ["foo"],
                    "tags": ["tag1"],
                },
            ),
        ),
        (
            dedent(
                """\
            ---
            aliases: a1,a2
            tags: [t1,t2]
            ---
            """
            ),
            defaultdict(
                lambda: None,
                {
                    "aliases": ["a1", "a2"],
                    "tags": ["t1", "t2"],
                },
            ),
        ),
    ],
)
def test_get_keys(input_text, expected):
    print(get_keys(input_text))
    assert expected == get_keys(input_text)
