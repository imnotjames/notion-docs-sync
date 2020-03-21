import logging
import re
import collections
from notion.block import CodeBlock, DividerBlock, HeaderBlock, SubheaderBlock, \
    SubsubheaderBlock, QuoteBlock, TextBlock, NumberedListBlock, \
    BulletedListBlock, ImageBlock, CollectionViewBlock
import mistletoe
from mistletoe.base_renderer import BaseRenderer


NOTION_CODE_LANGUAGES = [
    "ABAP",
    "Arduino",
    "Bash",
    "BASIC",
    "C",
    "Clojure",
    "CoffeeScript",
    "C++",
    "C#",
    "CSS",
    "Dart",
    "Diff",
    "Docker",
    "Elixir",
    "Elm",
    "Erlang",
    "Flow",
    "Fortran",
    "F#",
    "Gherkin",
    "GLSL",
    "Go",
    "GraphQL",
    "Groovy",
    "Haskell",
    "HTML",
    "Java",
    "JavaScript",
    "JSON",
    "Kotlin",
    "LaTeX",
    "Less",
    "Lisp",
    "LiveScript",
    "Lua",
    "Makefile",
    "Markdown",
    "Markup",
    "MATLAB",
    "Nix",
    "Objective-C",
    "OCaml",
    "Pascal",
    "Perl",
    "PHP",
    "Plain Text",
    "PowerShell",
    "Prolog",
    "Python",
    "R",
    "Reason",
    "Ruby",
    "Rust",
    "Sass",
    "Scala",
    "Scheme",
    "Scss",
    "Shell",
    "SQL",
    "Swift",
    "TypeScript",
    "VB.Net",
    "Verilog",
    "VHDL",
    "Visual Basic",
    "WebAssembly",
    "XML",
    "YAML"
]
NOTION_CODE_LANGUAGES_MAPPING = {
    l.lower(): l for l in NOTION_CODE_LANGUAGES
}


logger = logging.getLogger(__name__)

NOTION_STYLE_STRIKETHROUGH = "s"
NOTION_STYLE_EMPHASIS = "i"
NOTION_STYLE_STRONG = "b"
NOTION_STYLE_CODE = "c"
NOTION_STYLE_ANCHOR = "a"


def flatten(iterable):
    return [item for sublist in iterable for item in sublist]


def merge_adjacent_textblocks(blocks):
    if not blocks:
        return

    previous = blocks.pop(0)

    for block in blocks:
        if previous["type"] == TextBlock and block["type"] == TextBlock:
            previous["title"] += block["title"]
            continue

        yield previous

        previous = block

    yield previous


def merge_adjacent_tokens(tokens):
    if not tokens:
        return

    previous = tokens.pop(0)

    for token in tokens:
        if token[1] == previous[1]:
            previous[0] += token[0]
            continue

        yield previous

        previous = token

    yield previous


def without_notion_text(blocks):
    return [block for block in blocks if block['type'] != TextBlock]


def only_notion_text(blocks):
    notion_tokens = flatten([ block['title'] or [] for block in blocks if block['type'] == TextBlock ])

    # Combine similar adjacent tokens
    return list(merge_adjacent_tokens(notion_tokens))


def collect_notion_text(tokens, block_type, **kwargs):
    new_block = {
        'type': block_type,
        'title': only_notion_text(tokens),
        **kwargs
    }

    return [new_block, *without_notion_text(tokens)]


def notion_as_plain_text(tokens):
    return "".join([t[0] for t in tokens])


def apply_style(notion_tokens, style, *style_args):
    return [
        [literal, existing_styles + [[style, *style_args]]]
        for literal, existing_styles in notion_tokens
    ]


def as_inline_block(title):
    return {
        "type": TextBlock,
        "title": title
    }


def as_inline_style_block(tokens, style, *style_args):
    return as_inline_block(apply_style(only_notion_text(tokens), style, *style_args))


class NotionRenderer(BaseRenderer):
    def __render_multiple(self, tokens):
        return flatten([self.render(t) for t in tokens])

    def render(self, token):
        blocks = self.render_map[token.__class__.__name__](token)

        if blocks is None:
            blocks = []

        if isinstance(blocks, collections.Iterable) and not isinstance(blocks, (str, bytes, dict)):
            blocks = list(blocks)

        if not isinstance(blocks, list):
            blocks = [blocks]

        return blocks

    def render_document(self, token):
        return self.__render_multiple(token.children)

    def render_block_code(self, token):
        match_lang = NOTION_CODE_LANGUAGES_MAPPING.get(token.language.lower(), "Plain Text")

        children = self.__render_multiple(token.children)

        code_block = {
            "type": CodeBlock,
            "language": match_lang,
            "title_plaintext": notion_as_plain_text(only_notion_text(children))
        }

        return [code_block, *without_notion_text(children)]

    def render_thematic_break(self, token):
        return {
            'type': DividerBlock
        }

    def render_heading(self, token):
        level = token.level
        if level > 3:
            logger.debug(f"h{level} not supported in notion.so, converting to h3")
            level = 3

        block_type = [HeaderBlock, SubheaderBlock, SubsubheaderBlock][level - 1]

        return collect_notion_text(self.__render_multiple(token.children), block_type)

    def render_quote(self, token):
        return collect_notion_text(self.__render_multiple(token.children), QuoteBlock)

    def render_paragraph(self, token):
        # Collapse adjacent text blocks
        return list(merge_adjacent_textblocks(self.__render_multiple(token.children)))

    def render_list(self, token):
        return self.__render_multiple(token.children)

    def render_list_item(self, token):
        leaderContainsNumber = re.match(r'\d', token.leader)  # Contains a number

        children = self.__render_multiple(token.children)

        return {
            'type': NumberedListBlock if leaderContainsNumber else BulletedListBlock,
            'title': only_notion_text(children),
            'children': without_notion_text(children),
        }

    def render_table(self, token):
        header_row = [notion_as_plain_text(h["title"]) for h in self.render(token.header)]
        rows = [
            [
                notion_as_plain_text(c["title"])
                for c in self.render(r)
            ]
            for r in token.children
        ]

        return {
            'type': CollectionViewBlock,
            'rows': rows,
            'schema': [{"name": h, "type": "text"} for h in header_row]
        }

    def render_table_row(self, token):
        return self.__render_multiple(token.children)

    def render_table_cell(self, token):
        return as_inline_block(only_notion_text(self.__render_multiple(token.children)))

    def render_strong(self, token):
        return as_inline_style_block(self.__render_multiple(token.children), NOTION_STYLE_STRONG)

    def render_emphasis(self, token):
        return as_inline_style_block(self.__render_multiple(token.children), NOTION_STYLE_EMPHASIS)

    def render_inline_code(self, token):
        return as_inline_style_block(self.__render_multiple(token.children), NOTION_STYLE_CODE)

    def render_raw_text(self, token):
        return as_inline_block([[token.content, []]])

    def render_strikethrough(self, token):
        return as_inline_style_block(self.__render_multiple(token.children), NOTION_STYLE_STRIKETHROUGH)

    def render_link(self, token):
        return as_inline_style_block(self.__render_multiple(token.children), NOTION_STYLE_ANCHOR, token.target)

    def render_escape_sequence(self, token):
        return self.__render_multiple(token.children)

    def render_line_break(self, token):
        return as_inline_block([[' ', []]])

    def render_image(self, token):
        if token.title:
            alt = [[ token.title, [] ]]
        else:
            alt = notion_as_plain_text(only_notion_text(self.__render_multiple(token.children)))

        return {
            'type': ImageBlock,
            'display_source': token.src,
            'source': token.src,
            'caption': alt
        }


def convert(markdown):
    return mistletoe.markdown(markdown, renderer=NotionRenderer)
