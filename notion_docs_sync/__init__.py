import logging
import os
from random import choice
from argparse import ArgumentParser

from notion.client import NotionClient
from notion.block import Block, PageBlock, CollectionViewBlock
from emoji import EMOJI_UNICODE
import frontmatter

from .markdown import convert

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass


logger = logging.getLogger(__name__)


def random_emoji():
    # Don't allow people, hands, or fingers.
    forbidden_emoji_patterns = ['child', 'skin_tone', 'person', 'hand', 'finger']

    emoji_key = None
    while not emoji_key:
        emoji_key = choice(list(EMOJI_UNICODE.keys()))

        for pattern in forbidden_emoji_patterns:
            if pattern in emoji_key:
                emoji_key = None
                break

    return EMOJI_UNICODE[emoji_key]


def infer_block(root_block, path) -> Block:

    name, ext = os.path.splitext(path)

    if name == 'index':
        return root_block

    if ext != '.md' and ext != '':
        return None

    title = name.replace('-', ' ').replace('_', ' ').capitalize()

    for block in root_block.children:
        if block.type != 'page':
            continue

        if block.title != title:
            continue

        return block

    # Create a new page block

    return root_block.children.add_new(PageBlock, title=title)


def sync_file_to_block(filename, block):
    logger.info(f"Syncing {filename} to block {block.id}")

    with open(filename) as markdown_fd:
        contents = markdown_fd.read()

    post = frontmatter.loads(contents)

    markdown_blocks = convert(str(post))

    if block.icon is None:
        block.icon = random_emoji()

    # TODO: Don't remove blocks that match?
    # Remove non-page blocks.

    logger.info(f"Removing Children of {block.id}")
    for c in block.children:
        if c.type != 'page':
            c.remove()

    for markdown_block in reversed(markdown_blocks):
        markdown_block_class = markdown_block["type"]
        del markdown_block["type"]

        if "schema" in markdown_block:
            collection_schema = markdown_block["schema"]
            collection_rows = markdown_block["rows"]
            del markdown_block["schema"]
            del markdown_block["rows"]

        block_children = None
        if "children" in markdown_block:
            block_children = markdown_block["children"]
            del markdown_block["children"]

        new_block = block.children.add_new(markdown_block_class, **markdown_block)

        new_block.move_to(block, 'first-child')

        if isinstance(new_block, CollectionViewBlock):
                #We should have generated a schema and rows for this one
                client = block._client #Hacky internals stuff...
                new_block.collection = client.get_collection(
                    #Low-level use of the API
                    #TODO: Update when notion-py provides a better interface for this
                    client.create_record("collection", parent=new_block, schema=collection_schema)
                )

                new_block.views.add_new(view_type="table")

                for row in collection_rows:
                    newRow = new_block.collection.add_row()
                    for idx, propName in enumerate(prop["name"] for prop in collection_schema.values()):
                        # TODO: If rows aren't uploading, check to see if there's special
                        # characters that don't map to propName in notion-py
                        propName = propName.lower() #The actual prop name in notion-py is lowercase
                        propVal = row[idx]
                        setattr(newRow, propName, propVal)


def sync_directory_to_block(directory, root_block):
    touched_pages = set()

    index_path = os.path.join(directory, "index.md")

    # Do the index first to ensure the correct sort order.
    if os.path.isfile(index_path):
        touched_pages.add(root_block.id)
        sync_file_to_block(index_path, root_block)

    for path in os.listdir(directory):
        if path == 'index.md':
            # Skip because we had a special case for this above.
            continue

        block = infer_block(root_block, path)

        if not block:
            continue

        touched_pages.add(block.id)

        full_path = os.path.join(directory, path)

        if os.path.isdir(full_path):
            sync_directory_to_block(full_path, block)
        else:
            sync_file_to_block(full_path, block)

    # Any children that are pages under root_block but aren't in touched_pages should be pruned
    for child in root_block.children:
        if child.type == 'page' and child.id not in touched_pages:
            child.remove()

def main():
    parser = ArgumentParser()

    parser.add_argument('--notion-token', type=str, default=os.environ.get('NOTION_TOKEN'))
    parser.add_argument('docs_path', type=str)
    parser.add_argument('notion_url', type=str)

    args = parser.parse_args()

    token = args.notion_token
    root_url = args.notion_url
    docs_path = args.docs_path

    # add row to notion collection and add a text block with link to the new card
    client = NotionClient(token_v2=token)
    root_block = client.get_block(root_url)

    sync_directory_to_block(docs_path, root_block)
