import argparse
import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import SUPPORTED, chunk, parse
from app.database import SessionLocal, engine
from app.embeddings import embed
from app.models import Base, Chunk, Document

logger = logging.getLogger(__name__)


def _clean(value: str) -> str:
    return value.replace("\x00", "")  # PostgreSQL rejects NUL bytes, which some PDFs contain


async def _ingest_file(db: AsyncSession, path: Path, stats: dict[str, int]) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = await db.scalar(select(Document).where(Document.source == path.name))
    if existing and existing.sha256 == digest:
        stats["unchanged"] += 1
        return

    pieces = chunk(parse(path))
    texts = [_clean(f"{c.heading}\n{c.text}" if c.heading else c.text) for c in pieces]
    vectors = await asyncio.to_thread(embed, texts)  # CPU-bound; keep the event loop free
    document = Document(source=path.name, sha256=digest)
    document.chunks = [
        Chunk(
            position=i,
            heading=_clean(c.heading)[:255] if c.heading else None,
            page=c.page,
            text=_clean(c.text),
            embedding=v,
        )
        for i, (c, v) in enumerate(zip(pieces, vectors, strict=True))
    ]
    if existing:
        await db.delete(existing)
        await db.flush()
        stats["updated"] += 1
    else:
        stats["added"] += 1
    db.add(document)
    await db.commit()


async def ingest_folder(folder: Path) -> dict[str, int]:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0, "failed": 0, "chunks": 0}
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED)

    async with SessionLocal() as db:
        # A document whose file is gone must stop being answered from.
        names = {p.name for p in files}
        for document in (await db.scalars(select(Document))).all():
            if document.source not in names:
                await db.delete(document)
                stats["removed"] += 1
        await db.commit()

        for path in files:
            try:
                await _ingest_file(db, path, stats)
            except Exception:  # one unreadable file must not stop the others, or API startup
                await db.rollback()
                stats["failed"] += 1
                logger.exception("Skipped %s: could not be ingested", path.name)

        stats["chunks"] = await db.scalar(select(func.count(Chunk.id))) or 0
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base.")
    parser.add_argument("--path", type=Path, default=Path("/seed"))
    args = parser.parse_args()
    stats = asyncio.run(ingest_folder(args.path))
    print(
        f"Ingest done: {stats['added']} added, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged, {stats['removed']} removed, {stats['failed']} failed. "
        f"Chunks in database: {stats['chunks']}."
    )


if __name__ == "__main__":
    main()
