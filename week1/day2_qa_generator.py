import os
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


def generate_qa(text: str, num_questions: int = 10) -> str:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system="You are an expert professor who creates exam questions. Generate clear, specific questions that test deep understanding — not just memorization.",
        messages=[
            {
                "role": "user",
                "content": f"""Generate {num_questions} exam-style Q&A pairs from this content.

Use exactly this format for each one:

Q1: [question here]
A1: [detailed answer here]

Q2: [question here]
A2: [detailed answer here]

Content:
{text[:8000]}"""
            }
        ]
    )
    return message.content[0].text


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    num = input("How many questions? (default 10): ").strip()
    num_questions = int(num) if num.isdigit() else 10

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    print(f"Generating {num_questions} questions...\n")
    qa = generate_qa(text, num_questions)

    print("=" * 60)
    print("EXAM Q&A")
    print("=" * 60)
    print(qa)
    print("=" * 60)

    save = input("\nSave to file? (y/n): ").strip().lower()
    if save == "y":
        output_path = pdf_path.replace(".pdf", "_qa.txt")
        with open(output_path, "w") as f:
            f.write(qa)
        print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
