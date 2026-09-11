import os
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


# PROMPT 1 — Extract key terms
def extract_terms(text: str) -> list[str]:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system="You are a study assistant. Extract the most important terms and concepts from the content.",
        messages=[
            {
                "role": "user",
                "content": f"""Extract the 10 most important terms or concepts from this content.
Return ONLY a numbered list, one term per line. No descriptions.

Content:
{text[:8000]}"""
            }
        ]
    )
    raw = message.content[0].text
    # Parse the numbered list into a Python list
    terms = [line.split(". ", 1)[-1].strip() for line in raw.strip().split("\n") if line.strip()]
    return terms


# PROMPT 2 — Generate a flashcard for each term
def generate_flashcard(term: str, context: str) -> dict:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        system="You are a study assistant that creates clear, concise flashcards.",
        messages=[
            {
                "role": "user",
                "content": f"""Create a flashcard for this term: "{term}"

Use this context to write the definition:
{context[:3000]}

Format:
FRONT: {term}
BACK: [one clear sentence definition a student can memorize]"""
            }
        ]
    )
    raw = message.content[0].text
    front = term
    back = ""
    for line in raw.strip().split("\n"):
        if line.startswith("FRONT:"):
            front = line.replace("FRONT:", "").strip()
        elif line.startswith("BACK:"):
            back = line.replace("BACK:", "").strip()
    return {"front": front, "back": back}


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    # CHAIN STEP 1
    print("Extracting key terms...\n")
    terms = extract_terms(text)
    print(f"Found {len(terms)} terms: {', '.join(terms)}\n")

    # CHAIN STEP 2
    print("Generating flashcards...\n")
    flashcards = []
    for i, term in enumerate(terms, 1):
        print(f"  Generating card {i}/{len(terms)}: {term}")
        card = generate_flashcard(term, text)
        flashcards.append(card)

    print("\n" + "=" * 60)
    print("FLASHCARDS")
    print("=" * 60)
    for i, card in enumerate(flashcards, 1):
        print(f"\nCard {i}")
        print(f"  FRONT: {card['front']}")
        print(f"  BACK:  {card['back']}")

    save = input("\nSave to file? (y/n): ").strip().lower()
    if save == "y":
        output_path = pdf_path.replace(".pdf", "_flashcards.txt")
        with open(output_path, "w") as f:
            for i, card in enumerate(flashcards, 1):
                f.write(f"Card {i}\n")
                f.write(f"FRONT: {card['front']}\n")
                f.write(f"BACK:  {card['back']}\n\n")
        print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
