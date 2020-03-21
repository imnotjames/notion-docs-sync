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


def move_pages_to_end(block):
    # Move pages to the end of the document if they aren't already
    pages_to_move = []
    pages_seen = []

    for c in block.children:
        if c.type == 'page':
            pages_seen.append(c)
        else:
            pages_to_move.extend(pages_seen)
            pages_seen.clear()

    for page in pages_to_move:
        logger.info(f"Moving page {page.id} to end of {block.id}")
        page.move_to(block, 'last-child')


def block_matches_markdown_block(block, markdown_block_type, **markdown_block):
    if markdown_block_type != type(block):
        return False

    for key, value in markdown_block.items():
        if key in ['type', 'schema', 'rows']:
            continue

        block_attr = getattr(block, key)

        if block_attr != value:
            return False

    return True


def sync_collection_schema(collection, expected_schema):
    existing_schema = collection.get('schema')

    # The schemas must match!
    if existing_schema == expected_schema:
        return

    logger.info(f"Updating schema of {collection.id}")

    # If they don't, try to make them match.
    collection.set('schema', expected_schema)


def sync_collection_rows(block, collection_schema, collection_rows):
    if block.collection is None:
        logger.info(f"Creating a new collection for {block.id}")
        # We should have generated a schema and rows for this one
        client = block._client  # Hacky internals stuff...
        block.collection = client.get_collection(
            # Low-level use of the API
            # TODO: Update when notion-py provides a better interface for this
            client.create_record("collection", parent=block, schema={"title": {"text": "_", "type": "text"}})
        )

        block.views.add_new(view_type="table")

    collection_schema_ids = ['title']

    for i in range(len(collection_schema) - 1):
        collection_schema_ids.append('x' + format(i, '0>4x'))

    sync_collection_schema(block.collection, dict(zip(collection_schema_ids, collection_schema)))

    existing_rows = block.collection.get_rows()

    for extra_row in existing_rows[len(collection_rows):]:
        extra_row.remove()

    existing_rows_iter = iter(existing_rows)

    for row in collection_rows:
        try:
            row_block = next(existing_rows_iter)
        except StopIteration:
            row_block = block.collection.add_row()

        if len(row) > len(collection_schema_ids):
            row = row[:len(collection_schema_ids)]

        row = zip(collection_schema_ids, row)

        for schema_id, prop_value in row:
            if row_block.get_property(schema_id) != prop_value:
                row_block.set_property(schema_id, prop_value)


def sync_markdown_blocks_to_block(markdown_blocks, block):
    touched_blocks = set()
    children_iter = iter(block.children)

    for markdown_block in markdown_blocks:
        markdown_block_class = markdown_block["type"]
        del markdown_block["type"]

        markdown_contents = markdown_block.pop("title", None)
        collection_schema = markdown_block.pop("schema", None)
        collection_rows = markdown_block.pop("rows", None)
        block_children = markdown_block.pop("children", None)

        try:
            child_block = next(children_iter)
            while not block_matches_markdown_block(child_block, markdown_block_class, **markdown_block):
                child_block = next(children_iter)
            logger.info(f"Using existing markdown block {child_block.id} in {block.id}")
        except StopIteration:
            # If we've hit the end of the children create a new child.
            child_block = block.children.add_new(markdown_block_class, **markdown_block)
            logger.info(f"Creating new markdown block {child_block.id} in {block.id}")

        if markdown_contents:
            # Manually set the title property to bypass the `markdown_to_notion` in `notion-py`
            # This is because it chokes up on URLs and really we just don't need this 'cause
            # we're parsing the markdown ourselves.
            if child_block.get(["properties", "title"]) != markdown_contents:
                child_block.set(["properties", "title"], markdown_contents)

        touched_blocks.add(child_block.id)

        if isinstance(child_block, CollectionViewBlock):
            sync_collection_rows(child_block, collection_schema, collection_rows)

        if block_children:
            sync_markdown_blocks_to_block(block_children, child_block)

    for c in block.children:
        if c.type != 'page' and c.id not in touched_blocks:
            logger.info(f"Removing child block {c.id} from {block.id}")
            c.remove()


def sync_file_to_block(filename, block):
    logger.info(f"Syncing {filename} to block {block.id}")

    with open(filename) as markdown_fd:
        contents = markdown_fd.read()

    post = frontmatter.loads(contents)

    markdown_blocks = convert(str(post))

    sync_markdown_blocks_to_block(markdown_blocks, block)


def sync_directory_to_block(directory, root_block):
    if not root_block.get(['format', 'block_locked'], default=False):
        root_block.set(['format', 'block_locked'], True)

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

        if not block.get(['format', 'block_locked'], default=False):
            block.set(['format', 'block_locked'], True)

        touched_pages.add(block.id)

        full_path = os.path.join(directory, path)

        if block.icon is None:
            block.icon = random_emoji()

        if os.path.isdir(full_path):
            sync_directory_to_block(full_path, block)
        else:
            sync_file_to_block(full_path, block)

    # Any children that are pages under root_block but aren't in touched_pages should be pruned
    # And the pages linked within them should be moved to the tail.
    move_pages_to_end(root_block)
    for child in root_block.children:
        move_pages_to_end(child)
        if child.type == 'page' and child.id not in touched_pages:
            child.remove()


def main():
    import sys
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.setLevel(logging.INFO)

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
