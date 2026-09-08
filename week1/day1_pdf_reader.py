import os
import pymupdf as fitz
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


def summarize(text: str) -> str:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        # system="You are a study assistant. When given lecture content, produce a clear and concise summary a student can use to review before an exam.",
        system="You are a recruiter. Evaluate this document and give it a score out of 10.",
        messages=[
            {
                "role": "user",
                "content": f"Summarize this lecture:\n\n{text[:8000]}"  # first 8000 chars to stay within limits
            }
        ]
    )
    return message.content[0].text


def main():
    pdf_path = input("Enter path to your lecture PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)
    print(f"Extracted {len(text)} characters from {len(text.split())} words.\n")

    print("Sending to Claude...\n")
    summary = summarize(text)

    print("=" * 60)
    print("LECTURE SUMMARY")
    print("=" * 60)
    print(summary)
    print("=" * 60)


if __name__ == "__main__":
    main()
