import json
import sys
from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, MAX_TOOL_ROUNDS
from tools import lookup_plant, get_seasonal_conditions

# The debug traces below print Unicode arrows/emoji. On a default Windows
# console (cp1252) those raise UnicodeEncodeError, which would crash a tool
# call. Reconfigure stdout to UTF-8 so the traces are always safe to print.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_client = Groq(api_key=GROQ_API_KEY)

# ──────────────────────────────────────────────
# Tool definitions
#
# These are the schemas that tell the LLM what tools are available and how to
# call them. The LLM reads these descriptions and decides when (and how) to use
# each tool. They're already complete — your job is to implement the tool
# functions in tools.py and the agent loop below.
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_plant",
            "description": (
                "Look up care information for a specific houseplant by name. "
                "Returns detailed watering, light, humidity, and temperature requirements. "
                "Use this whenever the user asks about a specific plant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_name": {
                        "type": "string",
                        "description": "The plant name to look up. Can be a common name, scientific name, or nickname (e.g., 'pothos', 'devil's ivy', 'Monstera deliciosa').",
                    }
                },
                "required": ["plant_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_seasonal_conditions",
            "description": (
                "Get seasonal care adjustments for houseplants. "
                "Returns guidance on watering, fertilizing, light, and pests for the current or specified season. "
                "Use this when a user asks a season-specific question, or to complement plant care advice with seasonal context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "season": {
                        "type": "string",
                        "description": "The season to get care conditions for. If omitted, the current season is detected automatically.",
                        "enum": ["spring", "summer", "fall", "winter"],
                    }
                },
                "required": [],
            },
        },
    },
]

# ──────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a knowledgeable and friendly plant care advisor. "
    "Help users care for their houseplants by looking up specific plant information "
    "and current seasonal conditions using your available tools.\n\n"
    "Always use your tools to look up plant-specific information before answering — "
    "don't rely on your general knowledge alone. If a plant isn't in your database, "
    "say so clearly and offer general guidance based on what the user describes.\n\n"
    "Keep your advice practical and specific. Cite the source of your information "
    "when you have it (e.g., 'According to the care data for your monstera...')."
)

# ──────────────────────────────────────────────
# Tool dispatch
#
# This is already complete. It routes tool calls from the LLM to the actual
# Python functions in tools.py, and returns results as JSON strings (which is
# what the Groq API expects for tool results).
# ──────────────────────────────────────────────

def dispatch_tool(tool_name: str, tool_args: dict) -> str:
    """Route a tool call to the correct function and return the result as a JSON string."""
    print(f"  → Tool call: {tool_name}({tool_args})")
    if tool_name == "lookup_plant":
        result = lookup_plant(tool_args["plant_name"])
    elif tool_name == "get_seasonal_conditions":
        result = get_seasonal_conditions(tool_args.get("season"))
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    print(f"  ← Result: {json.dumps(result)[:120]}{'...' if len(json.dumps(result)) > 120 else ''}")
    return json.dumps(result)


# ──────────────────────────────────────────────
# Agent loop
# ──────────────────────────────────────────────

FALLBACK_RESPONSE = (
    "Sorry — I ran into a problem answering that. Please try rephrasing your question."
)


def run_agent(user_message: str, history: list) -> str:
    """
    Run the plant care agent for one user turn and return its response.

    Builds the messages list (system prompt + conversation history + new user
    message), then runs the tool-calling loop: call the LLM, execute any tool
    calls it requests, feed the results back, and repeat until the LLM produces a
    text answer with no further tool calls — or until MAX_TOOL_ROUNDS is hit.

    See specs/agent-loop-spec.md for the design rationale.
    """
    # 1. Build the messages list: system prompt + replayed history + new message.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for user_msg, assistant_msg in history:
        messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": user_message})

    try:
        # 2. Tool-calling loop, capped at MAX_TOOL_ROUNDS iterations.
        for _ in range(MAX_TOOL_ROUNDS):
            response = _client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            assistant_message = response.choices[0].message

            # Termination (a): no tool calls means the LLM has a final answer.
            if not assistant_message.tool_calls:
                return assistant_message.content or FALLBACK_RESPONSE

            # The assistant message (with tool_calls) MUST be appended before
            # the tool results that respond to it.
            messages.append(assistant_message)

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                # The model sometimes sends "null"/""/None for a no-arg call,
                # which json.loads turns into None. Coerce to an empty dict so
                # dispatch_tool always receives a mapping.
                tool_args = json.loads(tool_call.function.arguments or "{}") or {}
                tool_result = dispatch_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

        # Termination (b): hit MAX_TOOL_ROUNDS while still calling tools. Make
        # one final call forcing a text answer so the user always gets a reply.
        final = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tool_choice="none",
        )
        return final.choices[0].message.content or FALLBACK_RESPONSE

    except Exception as e:
        print(f"  [agent error] {e}")
        return FALLBACK_RESPONSE
