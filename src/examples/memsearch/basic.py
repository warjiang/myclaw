import asyncio
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from memsearch import MemSearch


MEMORY_DIR = "./memory"


async def main():
  load_dotenv(verbose=True)
  os.environ["OPENAI_BASE_URL"] = os.environ.get("LLM_BASE_URL")
  os.environ["OPENAI_API_KEY"] = os.environ.get("LLM_API_KEY")
  mem = MemSearch(
    paths=[MEMORY_DIR],
    embedding_provider="openai",
    embedding_model="doubao-embedding-text-240715",
    milvus_uri="./milvus.db",
  )
  content = "xx\nyy"

  p = Path(MEMORY_DIR) / f"{date.today()}.md"
  p.parent.mkdir(parents=True, exist_ok=True)
  with Path.open(p, "a") as f:
    f.write(f"\n{content}\n")

  await mem.index()


if __name__ == "__main__":
  asyncio.run(main())
