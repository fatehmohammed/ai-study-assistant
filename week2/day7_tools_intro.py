import os
import json
import base64
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n\n".join(page.get_text() for page in doc)


def pdf_to_images(pdf_path: str, start_page: int = 0, max_pages: int = 5) -> list[bytes]:
    doc = pymupdf.open(pdf_path)
    images = []
    for i, page in enumerate(doc):
        if i < start_page:
            continue
        if i >= start_page + max_pages:
            break
        pix = page.get_pixmap(dpi=150)
        images.append(pix.tobytes("png"))
    return images


def is_scanned(text: str) -> bool:
    return len(text.strip()) < 100


# ── The actual functions Claude can call ─────────────────────
saved_flashcards = []
saved_questions = []


def save_flashcard(front: str, back: str, topic: str) -> str:
    card = {"front": front, "back": back, "topic": topic}
    saved_flashcards.append(card)
    return f"Saved flashcard for: {front}"


def save_question(question: str, answer: str, difficulty: str) -> str:
    qa = {"question": question, "answer": answer, "difficulty": difficulty}
    saved_questions.append(qa)
    return f"Saved question: {question[:50]}..."


# ── Tool definitions — what Claude sees ──────────────────────
tools = [
    {
        "name": "save_flashcard",
        "description": "Save a flashcard with a term on the front and definition on the back.",
        "input_schema": {
            "type": "object",
            "properties": {
                "front": {"type": "string", "description": "The term or concept"},
                "back": {"type": "string", "description": "The definition or explanation"},
                "topic": {"type": "string", "description": "The subject area this belongs to"}
            },
            "required": ["front", "back", "topic"]
        }
    },
    {
        "name": "save_question",
        "description": "Save an exam-style question and answer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The exam question"},
                "answer": {"type": "string", "description": "The correct answer"},
                "difficulty": {"type": "string", "description": "easy, medium, or hard"}
            },
            "required": ["question", "answer", "difficulty"]
        }
    }
]


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    if tool_name == "save_flashcard":
        return save_flashcard(**tool_input)
    elif tool_name == "save_question":
        return save_question(**tool_input)
    return "Unknown tool"


def build_content(text: str = None, images: list[bytes] = None):
    if images:
        print(f"Scanned PDF — sending {len(images)} page(s) to Claude Vision...\n")
        content = []
        for img in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(img).decode("utf-8")
                }
            })
        content.append({
            "type": "text",
            "text": "Analyze these lecture pages and use your tools to save 3 flashcards and 2 exam questions."
        })
        return content
    return f"Analyze this content and use your tools to save 3 flashcards and 2 exam questions:\n\n{text[:5000]}"


def run_with_tools(content):
    print("Sending to Claude with tools available...\n")

    messages = [{"role": "user", "content": content}]

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        tools=tools,
        system="You are a study assistant. Analyze the content and save 3 flashcards and 2 exam questions using the tools provided.",
        messages=messages
    )

    while response.stop_reason == "tool_use":
        tool_calls = [block for block in response.content if block.type == "tool_use"]

        print(f"Claude wants to call {len(tool_calls)} tool(s):")
        for call in tool_calls:
            print(f"  → {call.name}({json.dumps(call.input, indent=4)})")

        tool_results = []
        for call in tool_calls:
            result = process_tool_call(call.name, call.input)
            print(f"  ✓ Result: {result}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            tools=tools,
            system="You are a study assistant. Analyze the content and save 3 flashcards and 2 exam questions using the tools provided.",
            messages=messages
        )

    return response


def main():
    pdf_path = input("Enter path to your PDF: ").strip()

    if not os.path.exists(pdf_path):
        print("File not found.")
        return

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    if is_scanned(text):
        print("Scanned PDF detected — switching to Vision mode...")
        total_pages = pymupdf.open(pdf_path).page_count
        print(f"PDF has {total_pages} pages.")
        pages_input = input(f"How many pages to process? (max recommended: 10, enter range like 1-5 or just a number): ").strip()

        if "-" in pages_input:
            start, end = pages_input.split("-")
            start, end = int(start) - 1, int(end)
        else:
            start, end = 0, int(pages_input) if pages_input.isdigit() else 5

        images = pdf_to_images(pdf_path, start_page=start, max_pages=end - start)
        content = build_content(images=images)
    else:
        content = build_content(text=text)

    response = run_with_tools(content)

    print(f"\n{'=' * 60}")
    print("CLAUDE'S FINAL RESPONSE")
    print("=" * 60)
    for block in response.content:
        if hasattr(block, "text"):
            print(block.text)

    print(f"\n{'=' * 60}")
    print(f"SAVED: {len(saved_flashcards)} flashcards, {len(saved_questions)} questions")
    print("=" * 60)
    for card in saved_flashcards:
        print(f"\nFLASHCARD [{card['topic']}]")
        print(f"  FRONT: {card['front']}")
        print(f"  BACK:  {card['back']}")
    for qa in saved_questions:
        print(f"\nQUESTION [{qa['difficulty'].upper()}]")
        print(f"  Q: {qa['question']}")
        print(f"  A: {qa['answer']}")


if __name__ == "__main__":
    main()
