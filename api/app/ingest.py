import argparse
import asyncio
import hashlib
from pathlib import Path

from sqlalchemy import func, select, text

from app.chunking import SUPPORTED, chunk, parse
from app.database import SessionLocal, engine
from app.embeddings import embed
from app.models import Base, Chunk, Document


async def ingest_folder(folder: Path) -> dict[str, int]:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    stats = {"added": 0, "updated": 0, "unchanged": 0, "chunks": 0}
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED)

    async with SessionLocal() as db:
        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            existing = await db.scalar(select(Document).where(Document.source == path.name))
            if existing and existing.sha256 == digest:
                stats["unchanged"] += 1
                continue
            if existing:
                await db.delete(existing)
                await db.flush()
                stats["updated"] += 1
            else:
                stats["added"] += 1

            pieces = chunk(parse(path))
            vectors = embed([f"{c.heading}\n{c.text}" if c.heading else c.text for c in pieces])
            document = Document(source=path.name, sha256=digest)
            document.chunks = [
                Chunk(position=i, heading=c.heading, page=c.page, text=c.text, embedding=v)
                for i, (c, v) in enumerate(zip(pieces, vectors, strict=True))
            ]
            db.add(document)
            await db.commit()

        stats["chunks"] = await db.scalar(select(func.count(Chunk.id))) or 0
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base.")
    parser.add_argument("--path", type=Path, default=Path("/seed"))
    args = parser.parse_args()
    stats = asyncio.run(ingest_folder(args.path))
    print(
        f"Ingest done: {stats['added']} added, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged. Chunks in database: {stats['chunks']}."
    )


if __name__ == "__main__":
    main()
