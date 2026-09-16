import os
import json
import base64
import glob
import pymupdf
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MAX_STEPS = 10  # prevent infinite loops


# ── PDF helpers ──────────────────────────────────────────────
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


# ── PDF selector ─────────────────────────────────────────────
def select_pdf() -> str:
    pdf_files = glob.glob("data/pdfs/*.pdf")

    if not pdf_files:
        print("No PDFs found in data/pdfs/")
        return None

    print("\nAvailable PDFs:")
    for i, f in enumerate(pdf_files):
        name = os.path.basename(f)
        size = os.path.getsize(f) // 1024
        print(f"  {i + 1}. {name} ({size} KB)")

    choice = int(input("\nPick a number: ")) - 1
    selected = pdf_files[choice]

    print(f"\nYou selected: {os.path.basename(selected)}")
    confirm = input("Confirm? (y/n): ").strip().lower()

    return selected if confirm == "y" else None


# ── Storage ──────────────────────────────────────────────────
memory = {
    "summary": None,
    "flashcards": [],
    "questions": [],
    "hard_topics": [],
    "study_plan": None
}


# ── Tools Claude can call ────────────────────────────────────
def save_summary(summary: str, key_points: list) -> str:
    memory["summary"] = {"summary": summary, "key_points": key_points}
    return f"Summary saved with {len(key_points)} key points."


def save_flashcard(front: str, back: str, topic: str) -> str:
    memory["flashcards"].append({"front": front, "back": back, "topic": topic})
    return f"Flashcard saved: {front}"


def save_question(question: str, answer: str, difficulty: str) -> str:
    memory["questions"].append({"question": question, "answer": answer, "difficulty": difficulty})
    return f"Question saved ({difficulty}): {question[:50]}..."


def flag_hard_topic(topic: str, reason: str, suggested_action: str) -> str:
    memory["hard_topics"].append({"topic": topic, "reason": reason, "action": suggested_action})
    return f"Flagged: {topic}"


def create_study_plan(plan: str, priority_topics: list, estimated_time: str) -> str:
    memory["study_plan"] = {
        "plan": plan,
        "priority_topics": priority_topics,
        "estimated_time": estimated_time
    }
    return f"Study plan created. Estimated time: {estimated_time}"


def get_progress() -> str:
    return json.dumps({
        "summary": "saved" if memory["summary"] else "missing",
        "flashcards": len(memory["flashcards"]),
        "questions": len(memory["questions"]),
        "hard_topics": len(memory["hard_topics"]),
        "study_plan": "saved" if memory["study_plan"] else "missing"
    })


# ── Tool definitions ─────────────────────────────────────────
tools = [
    {
        "name": "save_summary",
        "description": "Save a summary of the lecture content with key points.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["summary", "key_points"]
        }
    },
    {
        "name": "save_flashcard",
        "description": "Save a flashcard. Call this multiple times for multiple cards.",
        "input_schema": {
            "type": "object",
            "properties": {
                "front": {"type": "string"},
                "back": {"type": "string"},
                "topic": {"type": "string"}
            },
            "required": ["front", "back", "topic"]
        }
    },
    {
        "name": "save_question",
        "description": "Save an exam question. Call this multiple times for multiple questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "answer": {"type": "string"},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]}
            },
            "required": ["question", "answer", "difficulty"]
        }
    },
    {
        "name": "flag_hard_topic",
        "description": "Flag a topic students typically find difficult with study advice.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "reason": {"type": "string"},
                "suggested_action": {"type": "string"}
            },
            "required": ["topic", "reason", "suggested_action"]
        }
    },
    {
        "name": "create_study_plan",
        "description": "Create a personalized study plan based on the content analyzed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {"type": "string"},
                "priority_topics": {"type": "array", "items": {"type": "string"}},
                "estimated_time": {"type": "string"}
            },
            "required": ["plan", "priority_topics", "estimated_time"]
        }
    },
    {
        "name": "get_progress",
        "description": "Check what study materials have been saved so far.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    actions = {
        "save_summary": save_summary,
        "save_flashcard": save_flashcard,
        "save_question": save_question,
        "flag_hard_topic": flag_hard_topic,
        "create_study_plan": create_study_plan,
        "get_progress": get_progress
    }
    fn = actions.get(tool_name)
    return fn(**tool_input) if fn else "Unknown tool"


def build_content(text: str = None, images: list = None, goal: str = ""):
    instruction = f"""
Your goal: {goal}

Use your tools autonomously to complete this goal:
1. Save a summary with key points
2. Save at least 5 flashcards
3. Save at least 5 exam questions (mix of difficulty)
4. Flag at least 2 hard topics
5. Check your progress with get_progress
6. Create a study plan based on everything you've analyzed

Do not stop until all 6 steps are complete.
"""
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
        content.append({"type": "text", "text": instruction})
        return content
    return f"{instruction}\n\nContent:\n{text[:6000]}"


def run_agent(content, goal: str):
    print(f"\nAgent starting — Goal: {goal}\n")
    messages = [{"role": "user", "content": content}]

    step = 0
    while step < MAX_STEPS:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            tools=tools,
            system="""You are Jawar — an autonomous AI study assistant.
You have tools to create comprehensive study materials.
Work through tasks step by step. Use get_progress to check what's done.
Do not stop until your goal is fully complete.""",
            messages=messages
        )

        if response.stop_reason != "tool_use":
            print(f"\nAgent completed in {step} steps.")
            return response

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        step += len(tool_calls)

        print(f"Step {step} — Claude calls {len(tool_calls)} tool(s):")
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

    print(f"\nAgent stopped after {MAX_STEPS} steps (safety limit).")
    return None


def print_results():
    print(f"\n{'=' * 60}")
    print("JAWAR — STUDY MATERIALS")
    print("=" * 60)

    if memory["summary"]:
        print("\nSUMMARY")
        print("-" * 40)
        print(memory["summary"]["summary"])
        print("\nKey Points:")
        for p in memory["summary"]["key_points"]:
            print(f"  • {p}")

    if memory["flashcards"]:
        print(f"\nFLASHCARDS ({len(memory['flashcards'])})")
        print("-" * 40)
        for card in memory["flashcards"]:
            print(f"\n  [{card['topic']}]")
            print(f"  FRONT: {card['front']}")
            print(f"  BACK:  {card['back']}")

    if memory["questions"]:
        print(f"\nEXAM QUESTIONS ({len(memory['questions'])})")
        print("-" * 40)
        for qa in memory["questions"]:
            print(f"\n  [{qa['difficulty'].upper()}] {qa['question']}")
            print(f"  → {qa['answer']}")

    if memory["hard_topics"]:
        print(f"\nHARD TOPICS ({len(memory['hard_topics'])})")
        print("-" * 40)
        for t in memory["hard_topics"]:
            print(f"\n  ⚠ {t['topic']}")
            print(f"  Why hard: {t['reason']}")
            print(f"  Study tip: {t['action']}")

    if memory["study_plan"]:
        print(f"\nSTUDY PLAN")
        print("-" * 40)
        print(memory["study_plan"]["plan"])
        print(f"\nPriority topics:")
        for t in memory["study_plan"]["priority_topics"]:
            print(f"  → {t}")
        print(f"Estimated study time: {memory['study_plan']['estimated_time']}")

    print(f"\n{'=' * 60}")
    print(f"Total: {len(memory['flashcards'])} flashcards | {len(memory['questions'])} questions | {len(memory['hard_topics'])} hard topics | study plan: {'✅' if memory['study_plan'] else '❌'}")


def main():
    pdf_path = select_pdf()
    if not pdf_path:
        return

    goal = input("\nWhat is your study goal? (e.g. 'prepare me for my cell biology exam'): ").strip()
    if not goal:
        goal = "Create comprehensive study materials from this content"

    print("\nReading PDF...")
    text = extract_text(pdf_path)

    if is_scanned(text):
        print("Scanned PDF detected — switching to Vision mode...")
        total_pages = pymupdf.open(pdf_path).page_count
        print(f"PDF has {total_pages} pages.")
        pages_input = input("Page range (e.g. 1-5): ").strip()
        if "-" in pages_input:
            start, end = pages_input.split("-")
            start, end = int(start) - 1, int(end)
        else:
            start, end = 0, int(pages_input) if pages_input.isdigit() else 5
        images = pdf_to_images(pdf_path, start_page=start, max_pages=end - start)
        content = build_content(images=images, goal=goal)
    else:
        content = build_content(text=text, goal=goal)

    response = run_agent(content, goal)

    print_results()

    if response:
        print("\nJawar's message:")
        for block in response.content:
            if hasattr(block, "text"):
                print(block.text)


if __name__ == "__main__":
    main()
