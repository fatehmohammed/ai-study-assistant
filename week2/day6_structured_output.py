import os
import json
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


def generate_qa_json(text: str, num_questions: int = 5) -> list[dict]:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system="You are a study assistant. Always respond with valid JSON only. No markdown, no explanation, just JSON.",
        messages=[
            {
                "role": "user",
                "content": f"""Generate {num_questions} exam Q&A pairs from this content.

Return a JSON array in exactly this format:
[
  {{
    "question": "What is React?",
    "answer": "A JavaScript library for building user interfaces.",
    "difficulty": "easy"
  }},
  {{
    "question": "What is the virtual DOM?",
    "answer": "A lightweight copy of the real DOM that React uses to optimize updates.",
    "difficulty": "medium"
  }}
]

Difficulty must be one of: easy, medium, hard

Content:
{text[:8000]}"""
            }
        ]
    )

    raw = message.content[0].text.strip()

    # Strip markdown code blocks if Claude adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)


def print_qa(qa_list: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"STRUCTURED Q&A ({len(qa_list)} questions)")
    print("=" * 60)
    for i, item in enumerate(qa_list, 1):
        difficulty = item.get("difficulty", "").upper()
        print(f"\nQ{i} [{difficulty}]: {item['question']}")
        print(f"A{i}: {item['answer']}")


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    print("Generating structured Q&A...\n")
    qa_list = generate_qa_json(text)

    # Print formatted
    print_qa(qa_list)

    # Show raw JSON — this is the point of Day 6
    print(f"\n{'=' * 60}")
    print("RAW JSON OUTPUT")
    print("=" * 60)
    print(json.dumps(qa_list, indent=2))

    # Save JSON file — now it's usable by any system
    output_path = pdf_path.replace(".pdf", "_qa.json")
    with open(output_path, "w") as f:
        json.dump(qa_list, f, indent=2)
    print(f"\nSaved to: {output_path}")
    print("This JSON can now be loaded into a database, UI, or any other system.")


if __name__ == "__main__":
    main()
