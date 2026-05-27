"""File-based persistence for collections and requests.

Storage layout::

    $THERIDION_HOME/                 (default: ~/.theridion)
    └── collections/
        ├── <collection-uuid>.json
        └── <collection-uuid>.json

Each collection file is a single JSON document holding a tree of
CollectionItem (either folders or requests). Writes are atomic
(write-temp-then-rename) so a crash mid-save cannot corrupt an
existing file.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .models import Collection, CollectionItem, CollectionSummary

SCHEMA_VERSION = 1


def home_dir() -> Path:
    """Resolve the storage root, honoring THERIDION_HOME for tests."""
    override = os.environ.get("THERIDION_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".theridion"


def collections_dir() -> Path:
    d = home_dir() / "collections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(collection_id: str) -> Path:
    safe = uuid.UUID(collection_id)  # raises ValueError if malformed
    return collections_dir() / f"{safe}.json"


def _walk(items: list[CollectionItem]):
    """Iterate every item in a tree depth-first."""
    for item in items:
        yield item
        if item.is_folder:
            yield from _walk(item.items)


def _count_requests(items: list[CollectionItem]) -> int:
    return sum(1 for it in _walk(items) if not it.is_folder)


def list_summaries() -> list[CollectionSummary]:
    out: list[CollectionSummary] = []
    for p in sorted(collections_dir().glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        try:
            coll = Collection(**data)
        except Exception:
            # Skip files that don't validate so a malformed file doesn't
            # break the whole listing.
            continue
        out.append(
            CollectionSummary(
                id=coll.id,
                name=coll.name,
                request_count=_count_requests(coll.items),
            )
        )
    return out


def get(collection_id: str) -> Collection | None:
    p = _path_for(collection_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return Collection(**data)


def create(name: str) -> Collection:
    coll = Collection(
        id=str(uuid.uuid4()),
        name=name,
        version=SCHEMA_VERSION,
        items=[],
    )
    _atomic_write(coll)
    return coll


def add_request(
    collection_id: str,
    req: CollectionItem,
    parent_folder_id: str | None = None,
) -> Collection:
    """Insert or update a request inside a collection.

    If `parent_folder_id` is given, the request lands inside that folder.
    If a request with the same id already exists anywhere in the tree, it
    is replaced in place rather than appended.
    """
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")

    # Replace-in-place if the id is already somewhere in the tree.
    if _replace_by_id(coll.items, req):
        _atomic_write(coll)
        return coll

    target = _find_folder(coll.items, parent_folder_id) if parent_folder_id else None
    if parent_folder_id and target is None:
        raise FileNotFoundError(f"folder {parent_folder_id} not found")
    (target.items if target else coll.items).append(req)
    _atomic_write(coll)
    return coll


def add_folder(
    collection_id: str,
    folder: CollectionItem,
    parent_folder_id: str | None = None,
) -> Collection:
    if not folder.is_folder:
        raise ValueError("add_folder requires is_folder=True")
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    target = _find_folder(coll.items, parent_folder_id) if parent_folder_id else None
    if parent_folder_id and target is None:
        raise FileNotFoundError(f"folder {parent_folder_id} not found")
    (target.items if target else coll.items).append(folder)
    _atomic_write(coll)
    return coll


def delete_request(collection_id: str, request_id: str) -> Collection:
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    if not _delete_by_id(coll.items, request_id):
        raise FileNotFoundError(f"request {request_id} not found")
    _atomic_write(coll)
    return coll


def delete_folder(collection_id: str, folder_id: str) -> Collection:
    """Delete a folder and everything inside it."""
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    if not _delete_by_id(coll.items, folder_id):
        raise FileNotFoundError(f"folder {folder_id} not found")
    _atomic_write(coll)
    return coll


def rename_collection(collection_id: str, name: str) -> Collection:
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    coll.name = name
    _atomic_write(coll)
    return coll


def rename_item(collection_id: str, item_id: str, name: str) -> Collection:
    """Rename a request or folder inside a collection."""
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    if not _rename_by_id(coll.items, item_id, name):
        raise FileNotFoundError(f"item {item_id} not found")
    _atomic_write(coll)
    return coll


def move_item(
    collection_id: str, item_id: str, target_folder_id: str | None,
) -> Collection:
    """Move a request or folder to a different parent (or root if None)."""
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    item = _extract_by_id(coll.items, item_id)
    if item is None:
        raise FileNotFoundError(f"item {item_id} not found")
    target = _find_folder(coll.items, target_folder_id) if target_folder_id else None
    if target_folder_id and target is None:
        raise FileNotFoundError(f"folder {target_folder_id} not found")
    (target.items if target else coll.items).append(item)
    _atomic_write(coll)
    return coll


def reorder_items(
    collection_id: str,
    parent_folder_id: str | None,
    item_ids: list[str],
) -> Collection:
    """Reorder items within a parent (root if None) to match the given id list."""
    coll = get(collection_id)
    if coll is None:
        raise FileNotFoundError(f"collection {collection_id} not found")
    target_list = coll.items
    if parent_folder_id:
        folder = _find_folder(coll.items, parent_folder_id)
        if folder is None:
            raise FileNotFoundError(f"folder {parent_folder_id} not found")
        target_list = folder.items
    # Build a lookup of existing items by id.
    by_id = {it.id: it for it in target_list}
    # Validate that all ids refer to existing children.
    for iid in item_ids:
        if iid not in by_id:
            raise FileNotFoundError(f"item {iid} not found in target container")
    # Rebuild the list in the requested order, appending any items not in
    # item_ids at the end (defensive — shouldn't happen normally).
    reordered = [by_id[iid] for iid in item_ids]
    for it in target_list:
        if it.id not in {iid for iid in item_ids}:
            reordered.append(it)
    target_list.clear()
    target_list.extend(reordered)
    _atomic_write(coll)
    return coll


def delete_collection(collection_id: str) -> bool:
    p = _path_for(collection_id)
    if not p.exists():
        return False
    p.unlink()
    return True


# ---- tree helpers --------------------------------------------------------

def _find_folder(
    items: list[CollectionItem], folder_id: str
) -> CollectionItem | None:
    for it in items:
        if it.is_folder and it.id == folder_id:
            return it
        if it.is_folder:
            found = _find_folder(it.items, folder_id)
            if found is not None:
                return found
    return None


def _replace_by_id(
    items: list[CollectionItem], replacement: CollectionItem
) -> bool:
    """Find an item with the same id anywhere and replace it. Returns True
    if a replacement happened."""
    for i, it in enumerate(items):
        if it.id == replacement.id:
            items[i] = replacement
            return True
        if it.is_folder and _replace_by_id(it.items, replacement):
            return True
    return False


def _rename_by_id(items: list[CollectionItem], item_id: str, name: str) -> bool:
    for it in items:
        if it.id == item_id:
            it.name = name
            return True
        if it.is_folder and _rename_by_id(it.items, item_id, name):
            return True
    return False


def _extract_by_id(items: list[CollectionItem], item_id: str) -> CollectionItem | None:
    """Remove an item from the tree and return it."""
    for i, it in enumerate(items):
        if it.id == item_id:
            return items.pop(i)
        if it.is_folder:
            found = _extract_by_id(it.items, item_id)
            if found is not None:
                return found
    return None


def _delete_by_id(items: list[CollectionItem], item_id: str) -> bool:
    for i, it in enumerate(items):
        if it.id == item_id:
            del items[i]
            return True
        if it.is_folder and _delete_by_id(it.items, item_id):
            return True
    return False


# ---- atomic write --------------------------------------------------------

def _atomic_write(coll: Collection) -> None:
    p = _path_for(coll.id)
    payload: dict[str, Any] = coll.model_dump(mode="json")
    payload["version"] = SCHEMA_VERSION
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=f"{coll.id}.", suffix=".json.tmp", dir=str(p.parent)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, p)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
