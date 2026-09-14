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


# ── Storage ──────────────────────────────────────────────────
results = {
    "summary": None,
    "flashcards": [],
    "questions": [],
    "hard_topics": []
}


# ── Functions Claude can call ────────────────────────────────
def save_summary(summary: str, key_points: list) -> str:
    results["summary"] = {"summary": summary, "key_points": key_points}
    return f"Summary saved with {len(key_points)} key points."


def save_flashcard(front: str, back: str, topic: str) -> str:
    results["flashcards"].append({"front": front, "back": back, "topic": topic})
    return f"Flashcard saved: {front}"


def save_question(question: str, answer: str, difficulty: str) -> str:
    results["questions"].append({"question": question, "answer": answer, "difficulty": difficulty})
    return f"Question saved: {question[:50]}..."


def flag_hard_topic(topic: str, reason: str, suggested_action: str) -> str:
    results["hard_topics"].append({"topic": topic, "reason": reason, "action": suggested_action})
    return f"Flagged hard topic: {topic}"


# ── Tool definitions ─────────────────────────────────────────
tools = [
    {
        "name": "save_summary",
        "description": "Save a summary of the lecture content with key points.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "A concise summary of the content"},
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of the most important points"
                }
            },
            "required": ["summary", "key_points"]
        }
    },
    {
        "name": "save_flashcard",
        "description": "Save a flashcard for a key term or concept.",
        "input_schema": {
            "type": "object",
            "properties": {
                "front": {"type": "string", "description": "The term or concept"},
                "back": {"type": "string", "description": "The definition or explanation"},
                "topic": {"type": "string", "description": "Subject area"}
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
    },
    {
        "name": "flag_hard_topic",
        "description": "Flag a topic that students typically find difficult and suggest how to study it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The difficult topic"},
                "reason": {"type": "string", "description": "Why students find this hard"},
                "suggested_action": {"type": "string", "description": "How to study this topic effectively"}
            },
            "required": ["topic", "reason", "suggested_action"]
        }
    }
]


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    actions = {
        "save_summary": save_summary,
        "save_flashcard": save_flashcard,
        "save_question": save_question,
        "flag_hard_topic": flag_hard_topic
    }
    fn = actions.get(tool_name)
    return fn(**tool_input) if fn else "Unknown tool"


def build_content(text: str = None, images: list = None):
    if images:
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
            "text": "Analyze these lecture pages. Use your tools to: save a summary, create flashcards for key terms, generate exam questions, and flag any topics students typically find difficult."
        })
        return content
    return f"""Analyze this content. Use your tools to:
1. Save a summary with key points
2. Create flashcards for important terms
3. Generate exam questions (mix of difficulty)
4. Flag topics students typically find difficult

Content:
{text[:5000]}"""


def run_agent(content):
    print("Claude is analyzing content and choosing tools...\n")
    messages = [{"role": "user", "content": content}]

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        tools=tools,
        system="You are an expert study assistant. You MUST use ALL four tools: save_summary, save_flashcard (at least 3 times), save_question (at least 3 times), and flag_hard_topic (at least 1 time). Do not stop until all four tools have been called.",
        messages=messages
    )

    round_num = 1
    while response.stop_reason == "tool_use":
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        print(f"Round {round_num} — Claude calls {len(tool_calls)} tool(s):")
        for call in tool_calls:
            print(f"  → {call.name}")

        tool_results = []
        for call in tool_calls:
            result = process_tool_call(call.name, call.input)
            print(f"  ✓ {result}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            tools=tools,
            system="You are an expert study assistant. You MUST use ALL four tools: save_summary, save_flashcard (at least 3 times), save_question (at least 3 times), and flag_hard_topic (at least 1 time). Do not stop until all four tools have been called.",
            messages=messages
        )
        round_num += 1

    return response


def print_results():
    print(f"\n{'=' * 60}")
    print("STUDY MATERIALS GENERATED")
    print("=" * 60)

    if results["summary"]:
        print("\nSUMMARY")
        print("-" * 40)
        print(results["summary"]["summary"])
        print("\nKey Points:")
        for point in results["summary"]["key_points"]:
            print(f"  • {point}")

    if results["flashcards"]:
        print(f"\nFLASHCARDS ({len(results['flashcards'])})")
        print("-" * 40)
        for card in results["flashcards"]:
            print(f"\n  [{card['topic']}]")
            print(f"  FRONT: {card['front']}")
            print(f"  BACK:  {card['back']}")

    if results["questions"]:
        print(f"\nEXAM QUESTIONS ({len(results['questions'])})")
        print("-" * 40)
        for qa in results["questions"]:
            print(f"\n  [{qa['difficulty'].upper()}] {qa['question']}")
            print(f"  → {qa['answer']}")

    if results["hard_topics"]:
        print(f"\nHARD TOPICS TO WATCH ({len(results['hard_topics'])})")
        print("-" * 40)
        for topic in results["hard_topics"]:
            print(f"\n  ⚠ {topic['topic']}")
            print(f"  Why hard: {topic['reason']}")
            print(f"  Study tip: {topic['action']}")

    print(f"\n{'=' * 60}")
    print(f"Total: {len(results['flashcards'])} flashcards | {len(results['questions'])} questions | {len(results['hard_topics'])} hard topics flagged")


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
        pages_input = input("Page range (e.g. 1-5 or just 5): ").strip()
        if "-" in pages_input:
            start, end = pages_input.split("-")
            start, end = int(start) - 1, int(end)
        else:
            start, end = 0, int(pages_input) if pages_input.isdigit() else 5
        images = pdf_to_images(pdf_path, start_page=start, max_pages=end - start)
        content = build_content(images=images)
    else:
        content = build_content(text=text)

    response = run_agent(content)

    print_results()

    print("\nClaude's final message:")
    for block in response.content:
        if hasattr(block, "text"):
            print(block.text)


if __name__ == "__main__":
    main()
