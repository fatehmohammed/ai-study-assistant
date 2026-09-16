import os
import voyageai
from dotenv import load_dotenv

load_dotenv()

client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))


def get_embedding(text: str) -> list[float]:
    result = client.embed([text], model="voyage-2")
    return result.embeddings[0]


def main():
    print("=" * 60)
    print("DAY 11 — YOUR FIRST EMBEDDING")
    print("=" * 60)

    # Step 1 — embed a single sentence
    sentence = "The cell cycle has four phases: G1, S, G2, and M phase."
    print(f"\nSentence: {sentence}")

    print("\nGenerating embedding...")
    embedding = get_embedding(sentence)

    print(f"\nEmbedding stats:")
    print(f"  Type:       {type(embedding)}")
    print(f"  Dimensions: {len(embedding)}")
    print(f"  First 5 numbers: {embedding[:5]}")
    print(f"  Min value: {min(embedding):.4f}")
    print(f"  Max value: {max(embedding):.4f}")

    # Step 2 — embed multiple sentences and compare
    sentences = [
        "The cell cycle has four phases: G1, S, G2, and M phase.",  # original
        "Mitosis is the phase where cell division occurs.",           # related
        "Protein synthesis stops during M phase.",                    # related
        "I love eating pizza on Friday nights.",                      # unrelated
        "The Eiffel Tower is located in Paris, France.",              # unrelated
    ]

    print(f"\n{'=' * 60}")
    print("EMBEDDING 5 SENTENCES")
    print("=" * 60)

    result = client.embed(sentences, model="voyage-2")
    embeddings = result.embeddings

    for i, (sent, emb) in enumerate(zip(sentences, embeddings)):
        print(f"\n{i + 1}. \"{sent[:60]}...\"" if len(sent) > 60 else f"\n{i + 1}. \"{sent}\"")
        print(f"   Dimensions: {len(emb)}")
        print(f"   First 3 numbers: [{emb[0]:.4f}, {emb[1]:.4f}, {emb[2]:.4f}]")

    print(f"\n{'=' * 60}")
    print("NOTICE: Biology sentences have similar first numbers.")
    print("Unrelated sentences have very different numbers.")
    print("That's semantic meaning captured in numbers.")
    print("=" * 60)

    print(f"\nTotal tokens used: {result.total_tokens}")
    print(f"Approximate cost: ~${result.total_tokens * 0.0000001:.6f}")


if __name__ == "__main__":
    main()
