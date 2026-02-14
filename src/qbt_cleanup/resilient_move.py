"""Resilient cross-filesystem file move operations.

Handles the case where shutil.move across different filesystem mounts
(e.g., network mount to local disk) may encounter files being modified
or moved by external processes like FileFlows during the copy operation.
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MoveResult:
    """Result of a resilient move operation."""

    success: bool
    source: Path
    dest: Path
    files_copied: int = 0
    files_failed: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        """True if some files were copied but some failed."""
        return self.files_copied > 0 and self.files_failed > 0


def _is_same_filesystem(source: Path, dest_parent: Path) -> bool:
    """Check if source and dest parent are on the same filesystem."""
    try:
        return os.stat(source).st_dev == os.stat(dest_parent).st_dev
    except OSError:
        return False


def _copy_file_resilient(src: Path, dst: Path) -> Tuple[bool, str]:
    """Copy a single file, returning (success, error_message)."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return True, ""
    except FileNotFoundError:
        return False, f"File disappeared during copy (likely being processed externally): {src.name}"
    except PermissionError as e:
        return False, f"Permission denied: {src.name}: {e}"
    except OSError as e:
        return False, f"OS error copying {src.name}: {e}"


def resilient_move(source: Path, dest: Path, *, remove_source: bool = True) -> MoveResult:
    """Move source to dest with resilience to disappearing files.

    For same-filesystem moves, uses os.rename (atomic).
    For cross-filesystem moves of directories, copies file-by-file
    with per-file error handling, then removes successfully-copied
    source files.

    Args:
        source: Source file or directory path.
        dest: Destination path (must not exist).
        remove_source: Whether to remove source files after copying.
            Set to False when another process (e.g. qBittorrent) handles deletion.

    Returns:
        MoveResult with details of the operation.
    """
    result = MoveResult(success=False, source=source, dest=dest)

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Case 1: Same filesystem — os.rename is atomic
    if _is_same_filesystem(source, dest.parent):
        try:
            os.rename(str(source), str(dest))
            result.success = True
            result.files_copied = 1  # treated as single atomic op
            return result
        except OSError:
            logger.debug(f"[Resilient Move] os.rename failed, falling back to copy: {source.name}")

    # Case 2: Single file
    if source.is_file():
        ok, err = _copy_file_resilient(source, dest)
        if ok:
            result.success = True
            result.files_copied = 1
            if remove_source:
                try:
                    source.unlink()
                except OSError as e:
                    logger.warning(f"[Resilient Move] Copied but failed to remove source: {e}")
        else:
            result.files_failed = 1
            result.errors.append((str(source), err))
            logger.warning(f"[Resilient Move] {err}")
        return result

    # Case 3: Directory — file-by-file copy with per-file error handling
    dest.mkdir(parents=True, exist_ok=True)
    copied_sources: List[Path] = []

    try:
        entries = list(source.rglob("*"))
    except OSError as e:
        logger.error(f"[Resilient Move] Failed to list source directory: {e}")
        result.errors.append((str(source), str(e)))
        return result

    for item in entries:
        if not item.is_file():
            continue

        try:
            relative = item.relative_to(source)
        except ValueError:
            continue

        dst_file = dest / relative
        ok, err = _copy_file_resilient(item, dst_file)
        if ok:
            result.files_copied += 1
            copied_sources.append(item)
        else:
            result.files_failed += 1
            result.errors.append((str(relative), err))
            logger.warning(f"[Resilient Move] {err}")

    result.success = result.files_copied > 0

    # Clean up source files and empty directories
    if remove_source and result.files_copied > 0:
        for src_file in copied_sources:
            try:
                src_file.unlink()
            except OSError:
                pass

        _cleanup_empty_dirs(source)

    return result


def write_move_metadata(
    recycle_path: Path,
    dest_name: str,
    original_parent: str,
    move_result: MoveResult,
) -> None:
    """Write sidecar .meta.json for a recycled item.

    Args:
        recycle_path: The recycle bin directory.
        dest_name: The timestamped name of the recycled item.
        original_parent: The original parent directory path.
        move_result: The MoveResult from the move operation.
    """
    try:
        meta = {
            "original_path": original_parent,
            "files_copied": move_result.files_copied,
            "files_failed": move_result.files_failed,
        }
        if move_result.errors:
            meta["skipped_files"] = [
                {"path": rel, "reason": err} for rel, err in move_result.errors
            ]
        meta_file = recycle_path / f"{dest_name}.meta.json"
        meta_file.write_text(json.dumps(meta, indent=2))
    except OSError as e:
        logger.warning(f"[Recycle Bin] Failed to write metadata for {dest_name}: {e}")


def _cleanup_empty_dirs(root: Path) -> None:
    """Remove empty directories under root, bottom-up, then root itself if empty."""
    if not root.is_dir():
        return

    dirs = sorted(
        [d for d in root.rglob("*") if d.is_dir()],
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for d in dirs:
        try:
            os.rmdir(str(d))
        except OSError:
            pass

    try:
        os.rmdir(str(root))
    except OSError:
        pass
