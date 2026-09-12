import os
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


def extract_concepts(text: str, style: str = "precise") -> list[dict]:
    system_prompt = (
        "You are a professor explaining concepts to a student who needs to pass an exam. Be clear, precise and factual."
        if style == "precise"
        else "You are a creative tutor. Explain concepts using vivid analogies and real-world examples to make them memorable."
    )
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"""From this content, identify the 5 most important concepts a student must understand.

Use EXACTLY this format, no markdown, no numbering:

CONCEPT: React
EXPLANATION: A JavaScript library for building UIs.
WHY IT MATTERS: It is the most used frontend framework today.

CONCEPT: TypeScript
EXPLANATION: A typed superset of JavaScript.
WHY IT MATTERS: It catches bugs before runtime.

Now do the same for 5 concepts from the content below:

Content:
{text[:8000]}"""
            }
        ]
    )
    raw = message.content[0].text
    print("\n--- RAW OUTPUT (first 300 chars) ---")
    print(raw[:300])
    print("--- END RAW ---\n")
    return parse_concepts(raw)


def parse_concepts(raw: str) -> list[dict]:
    concepts = []
    current = {}
    for line in raw.strip().split("\n"):
        line = line.replace("**", "").strip()
        if "CONCEPT:" in line:
            if current:
                concepts.append(current)
            current = {"concept": line.split("CONCEPT:")[-1].strip()}
        elif "EXPLANATION:" in line:
            current["explanation"] = line.split("EXPLANATION:")[-1].strip()
        elif "WHY IT MATTERS:" in line:
            current["why"] = line.split("WHY IT MATTERS:")[-1].strip()
    if current:
        concepts.append(current)
    return concepts


def print_concepts(concepts: list[dict], label: str):
    print(f"\n{'=' * 60}")
    print(f"CONCEPTS — {label}")
    print("=" * 60)
    for i, c in enumerate(concepts, 1):
        print(f"\n{i}. {c.get('concept', '')}")
        print(f"   {c.get('explanation', '')}")
        print(f"   → {c.get('why', '')}")


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    print("\nRunning precise style (factual, exam-ready)...")
    concepts_precise = extract_concepts(text, style="precise")
    print_concepts(concepts_precise, "Precise (Exam Ready)")

    print("\nRunning creative style (analogies, memorable)...")
    concepts_creative = extract_concepts(text, style="creative")
    print_concepts(concepts_creative, "Creative (Memorable)")

    print("\n\nNOTICE the difference between the two outputs.")
    print("Precise = factual, consistent, exam-safe")
    print("Creative = analogies, memorable, easier to retain")


if __name__ == "__main__":
    main()
