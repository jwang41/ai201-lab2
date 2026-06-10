# Spec: `run_agent()`

**File:** `agent.py`
**Status:** Partially pre-filled — complete the two blank fields before implementing

---

## Purpose

Orchestrate a single conversational turn for the Plant Advisor agent. Given a user message and the conversation history, call the LLM with available tools, execute any tool calls the LLM requests, and return the final text response.

This is the core of what makes Plant Advisor an *agent* rather than a simple chatbot: the ability to decide which tools to call, use their results to inform its response, and loop until it has everything it needs.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_message` | `str` | The user's current message |
| `history` | `list` | Gradio conversation history — list of `[user_msg, assistant_msg]` pairs |

**Output:** `str`

The agent's final text response for this turn. Should never be empty — if something goes wrong, return a user-readable fallback message.

---

## Design Decisions

*Read `specs/system-design.md` (especially the "How the Groq Tool Calling API Works" section) before reviewing these. Complete the two blank fields before writing any code.*

---

### Messages list structure

The messages list must start with the system prompt, then replay the conversation
history, then add the new user message. Gradio history is a list of `[user, assistant]`
pairs — convert each pair to two API-format dicts:

```python
messages = [{"role": "system", "content": SYSTEM_PROMPT}]

for user_msg, assistant_msg in history:
    messages.append({"role": "user", "content": user_msg})
    if assistant_msg:
        messages.append({"role": "assistant", "content": assistant_msg})

messages.append({"role": "user", "content": user_message})
```

---

### Initial LLM call

Pass the model, the messages list, the tool definitions, and `tool_choice="auto"`
so the LLM can decide whether to call a tool or respond directly:

```python
response = client.chat.completions.create(
    model=LLM_MODEL,
    messages=messages,
    tools=TOOL_DEFINITIONS,
    tool_choice="auto",
)
```

---

### Detecting tool calls in the response

The response object has a `choices` list. Index 0 gives the assistant message.
Check its `tool_calls` attribute — if it's truthy, the LLM wants to call tools:

```python
assistant_message = response.choices[0].message

if not assistant_message.tool_calls:
    # No tool calls — LLM has a final answer
    ...
```

---

### Appending the assistant message

When there are tool calls, append the full assistant message object to `messages`
**before** appending any tool results. The API requires this ordering — a tool
result message must immediately follow the assistant message that requested it:

```python
messages.append(assistant_message)  # must come first
```

---

### Executing and appending tool results

For each tool call, extract the name and arguments, call `dispatch_tool()`, and
append the result as a `"tool"` role message. The `tool_call_id` links this result
back to the specific tool call that requested it:

```python
for tool_call in assistant_message.tool_calls:
    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)
    tool_result = dispatch_tool(tool_name, tool_args)

    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": tool_result,
    })
```

---

### Loop termination conditions

*The loop should stop when: (a) the LLM returns a response with no tool calls, OR (b) the MAX_TOOL_ROUNDS limit is reached. Describe how you will detect each condition and what you will return in each case.*

```
The loop is a `for _ in range(MAX_TOOL_ROUNDS)` so it can run at most
MAX_TOOL_ROUNDS iterations.

(a) No-more-tools: after each LLM call, check `assistant_message.tool_calls`.
    If it is falsy (None or empty), the LLM has produced its final answer —
    return `assistant_message.content` immediately (falling back to a
    user-readable message if content is somehow empty).

(b) Round limit: if the loop completes all MAX_TOOL_ROUNDS iterations and the
    LLM was still requesting tools, control falls past the loop. We then make
    one final LLM call with `tool_choice="none"` to force a plain text answer
    using everything gathered so far, and return that content. This guarantees
    the user always gets a reply instead of a dangling tool request.

Any exception during the loop is caught and converted to a fixed fallback
string, so run_agent() never returns empty or raises into the UI.
```

---

### Extracting the final text response

*Once the loop exits because there are no more tool calls, how do you extract the text content from the response object? What field holds the string you should return?*

```
response.choices[0].message.content

The response has a `choices` list; index 0 is the relevant completion. Its
`.message` is the assistant message object, and `.content` holds the final
text string. (When the message instead carries tool_calls, `.content` is
typically None — which is exactly why we only read `.content` once tool_calls
is empty.)
```

---

## Implementation Notes

*Fill this in after implementing and testing.*

**Trace of a working agent turn (what tools were called and in what order):**

```
Query: "How often should I water my snake plant in winter?"
Round 1 tool call: lookup_plant({"plant_name": "snake plant"})  -> found, returns Snake Plant care dict
Round 1 tool call: get_seasonal_conditions({"season": "winter"}) -> Winter dict
  (the model requested both tools in the same round, in parallel)
Round 2: no tool calls — LLM produces final text
Final response: Grounded answer combining the plant's watering range with winter
                guidance ("once a month or less," reduce watering, no fertilizer).
```

**What happens when you ask about a plant that isn't in the database?**

```
lookup_plant returns {"found": False, ...} with an instruction message. The agent
acknowledges the plant isn't in its database and offers general guidance without
inventing specific care figures — e.g. asking about "string of pearls" yields a
graceful "that's not in my database, but here's general advice" response.
```

**One thing about the tool call API that surprised you:**

```
Two things: (1) the model can request multiple tool calls in a single assistant
message (parallel tool calls), so the loop must iterate over ALL of
assistant_message.tool_calls, not just the first. (2) For a no-argument call the
model may send function.arguments as the string "null" (not "{}"), which
json.loads turns into None — so the arguments must be coerced to {} before use.
```
