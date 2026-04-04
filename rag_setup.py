# rag_setup.py
import chromadb
from sentence_transformers import SentenceTransformer
import os

# Fully local embeddings â€” no API calls
embedder = SentenceTransformer("all-MiniLM-L6-v2")

client = chromadb.PersistentClient(path="./tpp_knowledge_base")  # saves to disk
collection = client.get_or_create_collection("tpp_proposals")

def ingest_proposals(folder_path: str):
    """Load all .txt proposal files from a folder into the vector DB."""
    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            with open(os.path.join(folder_path, filename), "r") as f:
                text = f.read()

            # Chunk into ~500 character segments
            chunks = [text[i:i+500] for i in range(0, len(text), 500)]
            embeddings = embedder.encode(chunks).tolist()

            collection.add(
                documents=chunks,
                embeddings=embeddings,
                ids=[f"{filename}_chunk_{i}" for i in range(len(chunks))]
            )
            print(f"Ingested: {filename}")

def retrieve_context(query: str, n=5) -> list[str]:
    """Find the most relevant past proposal chunks for a given query."""
    query_embedding = embedder.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=n)
    return results["documents"][0]


# Run once to load TPP's proposals:
ingest_proposals("./proposals")
