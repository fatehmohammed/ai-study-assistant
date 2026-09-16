import os
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


# ── Without streaming — waits for full response ──────────────
def summarize_normal(text: str):
    print("\n--- WITHOUT STREAMING (waits for full response) ---")
    print("Waiting...\n")

    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system="You are a study assistant. Summarize lecture content clearly.",
        messages=[{"role": "user", "content": f"Summarize this:\n\n{text[:4000]}"}]
    )

    print(message.content[0].text)
    print("\n--- END ---")


# ── With streaming — prints word by word ─────────────────────
def summarize_streaming(text: str):
    print("\n--- WITH STREAMING (prints as Claude generates) ---\n")

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=1024,
        system="You are a study assistant. Summarize lecture content clearly.",
        messages=[{"role": "user", "content": f"Summarize this:\n\n{text[:4000]}"}]
    ) as stream:
        for text_chunk in stream.text_stream:
            print(text_chunk, end="", flush=True)

    print("\n\n--- END ---")


# ── Streaming with live token counter ────────────────────────
def summarize_with_stats(text: str):
    print("\n--- STREAMING WITH STATS ---\n")

    token_count = 0

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=1024,
        system="You are a study assistant. Summarize lecture content clearly.",
        messages=[{"role": "user", "content": f"Summarize this:\n\n{text[:4000]}"}]
    ) as stream:
        for text_chunk in stream.text_stream:
            print(text_chunk, end="", flush=True)
            token_count += 1

        final = stream.get_final_message()

    print(f"\n\n--- STATS ---")
    print(f"Input tokens:  {final.usage.input_tokens}")
    print(f"Output tokens: {final.usage.output_tokens}")
    print(f"Total cost:    ~${(final.usage.input_tokens * 0.000015 + final.usage.output_tokens * 0.000075):.4f}")


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    print("\nWhich demo do you want to see?")
    print("1. Normal vs Streaming comparison")
    print("2. Streaming with token stats")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        summarize_normal(text)
        input("\nPress Enter to see streaming version...")
        summarize_streaming(text)
    else:
        summarize_with_stats(text)


if __name__ == "__main__":
    main()
