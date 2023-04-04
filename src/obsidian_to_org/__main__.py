#!/usr/bin/env python3

import argparse
import pathlib
import re
import subprocess
import tempfile
import uuid
import shutil
from collections import defaultdict


COMMENT_MARKER = "#!#comment:"
RULER_RE = re.compile(r"^---\n(.+)", re.MULTILINE)
LINK_RE = re.compile(r"\[\[([^|\[\.]*?)\]\]")
LINK_DESCRIPTION_RE = re.compile(r"\[\[([^\.]*?)\|(.*?)\]\]")
# E.g., ![[myimage.png]]
IMAGE_RE = re.compile(r"!?\[\[(?:[^|\[\]\.]*/)?([^/\]]+\.(png|jpe?g|svg|gif))\]\]")
PDF_RE = re.compile(r"!?\[\[(?:[^|\[\]\.]*/)?([^/\]]+\.(pdf|PDF))\]\]")

# See https://help.obsidian.md/How+to/Working+with+tags#Allowed+characters
TAGS_RE = re.compile(r"#([A-Za-z][A-Za-z0-9/_-]*)")

# For example, [[file:foo.org][The Title is Foo]]
FILE_LINK_RE = re.compile(r"\[\[file:(.*?)\]\[(.*?)\]\]")


def fix_markdown_code_blocks(markdown_contents):
    """Convert special Obsidian code blocks."""
    # Replace blocks of the form run-<language> from Execute Code plugin
    # with normal <language> blocks
    markdown_contents = re.sub(r"```run-(.*)", r"```\1", markdown_contents)
    # Convert sh to shell blocks
    markdown_contents = markdown_contents.replace("```sh", "```shell")

    return markdown_contents


def fix_markdown_comments(markdown_contents):
    """Turn Obsidian comments into HTML comments."""
    chunks = markdown_contents.split("%%")
    inside_comment = False
    output = []
    for i, chunk in enumerate(chunks):
        if not inside_comment:
            output.append(chunk)
            inside_comment = True
        else:
            if "\n" in chunk:
                lines = chunk.splitlines(True)
                if len(lines) > 0 and lines[0].strip() == "":
                    lines = lines[1:]
                output.extend(f"{COMMENT_MARKER}{line}" for line in lines)
            else:
                output.extend(["<!--", chunk, "-->"])
            inside_comment = False
    return "".join(output)


def restore_comments(org_contents):
    """Restore the comments in org format."""
    return "".join(
        line.replace(COMMENT_MARKER, "# ") for line in org_contents.splitlines(True)
    )


def prepare_markdown_text(markdown_contents):
    markdown_contents = fix_markdown_comments(markdown_contents)
    markdown_contents = fix_markdown_code_blocks(markdown_contents)
    return markdown_contents


def fix_links(org_contents):
    """Convert all kinds of links."""
    org_contents = LINK_RE.sub(r"[[file:\1.org][\1]]", org_contents)
    org_contents = LINK_DESCRIPTION_RE.sub(r"[[file:\1.org][\2]]", org_contents)
    # I have org-roam-images set in org-link-abbrev-alist to point to where
    # all org roam images are stored. Similar for pdfs.
    org_contents = IMAGE_RE.sub(r"[[org-roam-images:\1]]", org_contents)
    org_contents = PDF_RE.sub(r"[[org-roam-attachments:\1]]", org_contents)
    org_contents = org_contents.replace("%20", " ")
    return org_contents


def convert_file_links_to_id_links(org_contents, nodes):
    def replace_with_id(match):
        file_name = match.group(1).replace("%20", " ")  # Handle spaces in filenames
        node_id = nodes.get(pathlib.Path(file_name).stem)
        if not node_id:
            return match.group(0)
        return f"[[id:{node_id}][{match.group(2)}]]"


def convert_markdown_file(md_file, org_file):
    markdown_contents = prepare_markdown_text(md_file.read_text())

    # Convert from md to org
    with tempfile.NamedTemporaryFile("w+") as fp:
        fp.write(markdown_contents)
        fp.flush()
        subprocess.run(
            [
                "pandoc",
                "--from=markdown-tex_math_dollars-auto_identifiers",
                "--to=org",
                "--wrap=preserve",
                "--output",
                org_file,
                fp.name,
            ],
            check=True,
        )

    org_contents = org_file.read_text()
    org_contents = restore_comments(org_contents)
    org_contents = fix_links(org_contents)
    org_file.write_text(org_contents)


def walk_directory(path):
    # From https://stackoverflow.com/questions/6639394/what-is-the-python-way-to-walk-a-directory-tree
    for p in path.iterdir():
        if p.is_dir():
            yield from walk_directory(p)
            continue
        yield p.resolve()


def maybeSplitList(s):
    """If the string s represents a list, create a list. Otherwise return as is"""
    if len(s) > 0 and (s.startswith("[") or "," in s):
        if s.startswith("["):
            s = s[1:-1]
        # Split at whitespace or commas, respecting quotes
        s = re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', s)
        return s
    return s


def get_keys(content):
    """Return a dictionary of all the YAML keys and values"""
    lines = content.split("\n")
    frontmatter = defaultdict(lambda: "")
    if not lines or lines[0] != "---":
        return frontmatter
    for i in range(1, len(lines)):
        if lines[i] == "---\n":
            break
        key = lines[i].split(":")[0]
        val = ":".join(lines[i].split(":")[1:]).strip()
        if not val:
            continue
        if key != "title":
            val = maybeSplitList(val)
        if key in ["tags", "aliases"] and not isinstance(val, list):
            val = [val]  # always use a list for tags / aliases
        frontmatter[key] = val
    return frontmatter


def single_file():
    parser = argparse.ArgumentParser(
        description="Convert an Obsidian Markdown file into org-mode"
    )
    parser.add_argument(
        "markdown_file", type=pathlib.Path, help="The Markdown file to convert"
    )
    args = parser.parse_args()
    md_file = args.markdown_file

    # TODO: Make this an argument.
    output_dir = pathlib.Path("out")
    if not output_dir.is_dir():
        output_dir.mkdir()

    org_file = (output_dir / md_file.stem).with_suffix(".org")
    convert_markdown_file(md_file, org_file)
    print(f"Converted {md_file} to {org_file}")


def add_node_id(org_file, node_id, frontmatter):
    contents = org_file.read_text()
    basename = org_file.stem
    tags = ":".join(frontmatter["tags"])
    aliases = " ".join(frontmatter["aliases"])
    title = basename
    if "title" in frontmatter and not basename.startswith("@"):
        title = frontmatter["title"]
        if title.startswith('"'):
            title = title[1:-1]
    with org_file.open("w") as fp:
        fp.write(":PROPERTIES:\n")
        fp.write(f":ID: {node_id}\n")

        if aliases:
            fp.write(f":ROAM_ALIASES: {aliases}\n")

        if basename.startswith("@"):  # reference notes
            fp.write(f":ROAM_REFS: [cite:{basename}]\n")

        fp.write(":END:\n")

        fp.write(f"#+title: {title}\n")

        if "date-created" in frontmatter:
            fp.write(f'#+created: [{frontmatter["date-created"]}]\n')

        if tags:
            fp.write(f"#+filetags: :{tags}:\n")

        fp.write("\n\n")
        fp.write(contents)


def find_tags_in_markdown(contents):
    return TAGS_RE.findall(contents)


def convert_directory():
    parser = argparse.ArgumentParser(
        description="Convert a directory of Obsidian markdown files into org-mode"
    )
    parser.add_argument(
        "markdown_directory",
        type=pathlib.Path,
        help="The directory of Markdown files to convert",
    )
    parser.add_argument(
        "output_directory",
        type=pathlib.Path,
        help="The directory to put the org files in",
    )
    parser.add_argument(
        "--skip_dirs",
        type=str,
        help="regex of directories to ignore",
        default="",
    )
    parser.add_argument(
        "--image_dir",
        type=pathlib.Path,
        help="path to output image files",
        default=None,
    )
    parser.add_argument(
        "--pdf_dir",
        type=pathlib.Path,
        help="path to output linked pdf files",
        default=None,
    )
    args = parser.parse_args()

    markdown_directory = args.markdown_directory.resolve()
    skip_dirs = re.compile(args.skip_dirs)
    image_dir = args.image_dir
    pdf_dir = args.pdf_dir

    if not args.output_directory.is_dir():
        args.output_directory.mkdir()

    nodes = {}

    for path in walk_directory(markdown_directory):
        if path.name == ".DS_Store" or re.search(skip_dirs, str(path)):
            continue

        if path.suffix != ".md":
            if path.suffix in [".png", ".jpg", ".jpeg", ".svg", ".gif"] and image_dir:
                copy_path = (
                    image_dir / path.name
                )  # args.output_directory / os.path.join("images", path.name)
            elif path.suffix in [".pdf", ".PDF"] and pdf_dir:
                copy_path = pdf_dir / path.name
            else:
                copy_to = path.relative_to(markdown_directory)
                copy_path = args.output_directory / copy_to
            print(f"Copying from {path} to {copy_path}")
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(path), str(copy_path))
            continue
        org_filename = path.relative_to(markdown_directory).with_suffix(".org")
        org_path = args.output_directory / org_filename
        org_path.parent.mkdir(parents=True, exist_ok=True)
        convert_markdown_file(path, org_path)
        frontmatter = get_keys(path.read_text())
        nodes[org_filename.stem] = node_id = str(uuid.uuid4()).upper()
        add_node_id(org_path, node_id, frontmatter)
        print(f"Converted {path} to {org_filename}")

    for org_path in walk_directory(args.output_directory):
        if org_path.name == ".DS_Store" or org_path.suffix != ".org":
            continue

        contents = org_path.read_text()
        org_path.write_text(convert_file_links_to_id_links(contents, nodes))
        print(f"Converted links in {org_path}")

    # TODO: What about tags (e.g. #literature). See https://www.orgroam.com/manual.html#Tags


if __name__ == "__main__":
    convert_directory()
