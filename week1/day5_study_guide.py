import os
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


# ── Day 1: Summary ──────────────────────────────────────────
def generate_summary(text: str) -> str:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system="You are a study assistant. Produce a clear concise summary a student can use to review before an exam.",
        messages=[{"role": "user", "content": f"Summarize this lecture:\n\n{text[:8000]}"}]
    )
    return message.content[0].text


# ── Day 4: Key Concepts ─────────────────────────────────────
def generate_concepts(text: str) -> str:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system="You are a professor. Be clear, precise and factual.",
        messages=[
            {
                "role": "user",
                "content": f"""Identify the 5 most important concepts. Use EXACTLY this format:

CONCEPT: React
EXPLANATION: A JavaScript library for building UIs.
WHY IT MATTERS: It is the most used frontend framework today.

Content:
{text[:8000]}"""
            }
        ]
    )
    return message.content[0].text


# ── Day 3: Flashcards ───────────────────────────────────────
def generate_flashcards(text: str) -> str:
    # Step 1 — extract terms
    terms_msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        system="You are a study assistant.",
        messages=[
            {
                "role": "user",
                "content": f"List the 5 most important terms from this content. Return a numbered list only:\n\n{text[:8000]}"
            }
        ]
    )
    terms_raw = terms_msg.content[0].text
    terms = [line.split(". ", 1)[-1].strip() for line in terms_raw.strip().split("\n") if line.strip()]

    # Step 2 — generate a card per term
    cards = []
    for term in terms:
        card_msg = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=256,
            system="You are a study assistant that creates flashcards.",
            messages=[
                {
                    "role": "user",
                    "content": f'Create a flashcard for "{term}" using this context:\n{text[:3000]}\n\nFormat:\nFRONT: {term}\nBACK: [one sentence definition]'
                }
            ]
        )
        cards.append(card_msg.content[0].text.strip())

    return "\n\n".join(cards)


# ── Day 2: Q&A ──────────────────────────────────────────────
def generate_qa(text: str) -> str:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system="You are an expert professor who creates exam questions.",
        messages=[
            {
                "role": "user",
                "content": f"""Generate 5 exam-style Q&A pairs. Use exactly this format:

Q1: [question]
A1: [answer]

Content:
{text[:8000]}"""
            }
        ]
    )
    return message.content[0].text


def save_guide(path: str, summary: str, concepts: str, flashcards: str, qa: str):
    with open(path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("STUDY GUIDE\n")
        f.write("=" * 60 + "\n\n")

        f.write("SECTION 1: SUMMARY\n")
        f.write("-" * 40 + "\n")
        f.write(summary + "\n\n")

        f.write("SECTION 2: KEY CONCEPTS\n")
        f.write("-" * 40 + "\n")
        f.write(concepts + "\n\n")

        f.write("SECTION 3: FLASHCARDS\n")
        f.write("-" * 40 + "\n")
        f.write(flashcards + "\n\n")

        f.write("SECTION 4: EXAM Q&A\n")
        f.write("-" * 40 + "\n")
        f.write(qa + "\n")


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    print("Generating summary...")
    summary = generate_summary(text)

    print("Extracting key concepts...")
    concepts = generate_concepts(text)

    print("Creating flashcards...")
    flashcards = generate_flashcards(text)

    print("Generating exam Q&A...")
    qa = generate_qa(text)

    output_path = pdf_path.replace(".pdf", "_study_guide.txt")
    save_guide(output_path, summary, concepts, flashcards, qa)

    print(f"\nStudy guide saved to: {output_path}")
    print("\nPreview:")
    print("=" * 60)
    print(summary[:300] + "...")


if __name__ == "__main__":
    main()
