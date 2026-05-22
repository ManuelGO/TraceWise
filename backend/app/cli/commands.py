"""Management commands for knowledge base operations."""

import logging
import sys
from pathlib import Path

from app.services.kb_loader import KBLoader

# FIX #9: Use standard logger acquisition pattern
logger = logging.getLogger(__name__)


def load_kb(path: str | None = None, dry_run: bool = False, verbose: bool = False) -> int:
    """Load knowledge base documents from filesystem.

    Args:
        path: Optional path to a category directory. Can be an absolute path to any KB directory.
            The parent of this path becomes the KB base, and the final path segment is treated
            as the category name. For example: /custom/kb/eudr_summaries → uses /custom/kb as KB
            base and loads eudr_summaries category. If None, loads all categories from default.
        dry_run: If True, validate without persisting changes.
        verbose: If True, log debug-level messages.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    if verbose:
        logging.getLogger("app").setLevel(logging.DEBUG)

    try:
        loader = KBLoader()

        # Load documents
        logger.info("Starting knowledge base load...")
        if path:
            # FIX #5: Use supplied path as KB base directory
            category_path = Path(path).resolve()
            if not category_path.exists():
                logger.error(f"Path not found: {path}")
                return 1

            kb_base = category_path.parent
            loader = KBLoader(str(kb_base))
            logger.info(f"Loading category: {category_path.name} from {kb_base}")
            loader.load_category(category_path.name)
        else:
            # Load all categories from default
            logger.info("Loading all categories...")
            loader.load_all()

        stats = loader.get_statistics()

        # Log results
        logger.info(
            f"Load complete: {stats['loaded']} loaded, {stats['skipped']} skipped, {stats['errors']} errors"
        )

        if stats["errors"] > 0:
            logger.warning("Errors during load:")
            for error_msg in stats["error_messages"]:
                logger.warning(f"  - {error_msg}")

        # In dry-run mode, don't persist
        if dry_run:
            logger.info("[DRY RUN] Changes not persisted")
            return 0

        # Validate index before saving
        if not loader.validate_index():
            logger.error("Index validation failed")
            return 1

        # Save index
        if not loader.save_index():
            logger.error("Failed to save index")
            return 1

        logger.info(f"Index saved: {loader.index_path}")
        logger.info(
            f"Successfully loaded {stats['loaded']} documents "
            f"({stats['skipped']} already present)"
        )
        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid data: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


def main() -> None:
    """CLI entry point for load_kb command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Knowledge base management commands",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # load_kb subcommand
    load_parser = subparsers.add_parser("load_kb", help="Load knowledge base documents")
    load_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Optional path to specific category to load",
    )
    load_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without persisting changes",
    )
    load_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.command == "load_kb":
        exit_code = load_kb(
            path=args.path,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
