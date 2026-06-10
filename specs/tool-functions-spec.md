# Spec: Tool Functions

**File:** `tools.py`
**Status:** `get_seasonal_conditions` — Pre-implemented, read through. `lookup_plant` — complete spec fields before implementing.

---

## Purpose

These two functions are the tools the agent can call. They retrieve structured data from the local plant database and seasonal data files and return it to the agent loop, which passes it to the LLM as context for generating a response.

---

## Function 1: `lookup_plant()`

### Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `plant_name` | `str` | The plant name as entered by the user or chosen by the LLM — may be any casing, common name, scientific name, or alias |

**Output:** `dict`

When the plant is **found**, return:
```python
{"found": True, "plant": <the full plant dict from _plant_db>}
```

When the plant is **not found**, return:
```python
{"found": False, "name": <normalized input>, "message": <helpful string>}
```

---

### Design Decisions

*Complete the two blank fields below before writing code. The others are pre-filled for you.*

---

#### Input normalization

Strip leading/trailing whitespace and convert to lowercase before any comparison.

```python
normalized = plant_name.strip().lower()
```

---

#### Search order

Search in this order: direct key → display name → aliases. Keys are the fastest
lookup (O(1) dict access), so check those first. Display names are the next most
likely match for clean user input. Aliases are the broadest net, so they go last.

```
1. Direct key match: normalized in _plant_db
2. Display name match: plant["display_name"].lower() == normalized
3. Alias match: normalized in [alias.lower() for alias in plant["aliases"]]
```

---

#### Alias matching approach

*Aliases are stored as a list of strings. How will you check if the normalized input matches any alias in the list? Write your approach in pseudocode or plain English.*

```
Lowercase (and strip) every alias in the plant's "aliases" list, then test
membership:

    normalized in [alias.strip().lower() for alias in plant["aliases"]]

The aliases in the data are already lowercase, but normalizing both sides makes
the match casing/whitespace-insensitive and robust to future data edits. Using
`in` on the list is a clean exact-match test (no partial/substring matching, so
"ivy" will not accidentally match "devil's ivy").
```

---

#### Not-found message

*When a plant isn't found, the agent will read your message and use it to decide what to tell the user. Write the exact string you'll return — make it useful to the agent, not just to a human reading logs.*

```
"No plant matching '<normalized>' is in the care database. Tell the user this
specific plant isn't in your database, then offer general houseplant guidance
based on what they describe. Do not invent specific care figures (watering
frequency, temperature ranges, etc.)."

This is an instruction to the agent, not a human-facing log line: it both
states the fact (not in DB) and prescribes the desired behavior (acknowledge +
degrade gracefully + don't hallucinate numbers), which directly supports the
Milestone 3 graceful-degradation goal.
```

---

#### Implementation Notes

*Fill this in after implementing and running the app.*

**Test: does `"devil's ivy"` return the pothos entry?**
```
Yes — matched via the alias list, returns "Pothos".
```

**Test: does `"SNAKE PLANT"` return the snake plant entry?**
```
Yes — display-name match is case-insensitive, returns "Snake Plant".
"  ZZ Plant  " (extra whitespace) and "mother-in-law's tongue" (alias) also
resolve correctly.
```

**One edge case you discovered while implementing:**
```
The tool definition in agent.py advertises scientific-name lookups
(e.g. "Monstera deliciosa"), but scientific_name is NOT in the spec's 3-step
search order and is not duplicated into the aliases list. Relying only on
key/display_name/aliases would silently fail that advertised case, so I added
an explicit scientific_name comparison in the scan loop.
```

---

## Function 2: `get_seasonal_conditions()`

### Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `season` | `str \| None` | One of `"spring"`, `"summer"`, `"fall"`, `"winter"`, or `None` to auto-detect |

**Output:** `dict`

The full season dict from `_season_data`, plus one additional field:

| Added field | Type | Value |
|-------------|------|-------|
| `"detected_season"` | `bool` | `True` if auto-detected from the month; `False` if season was passed as an argument |

---

### Design Decisions

*This function is pre-implemented — read through these fields and the code before working on `lookup_plant`.*

---

#### Auto-detection logic

When `season` is `None`, get the current calendar month with `datetime.now().month`
and look it up in the `_MONTH_TO_SEASON` dict, which maps month numbers to season strings.

```python
current_month = datetime.now().month
season_key = _MONTH_TO_SEASON[current_month]
```

---

#### Season validation

If the caller passes an invalid season string (e.g., `"monsoon"`), the function
falls back to auto-detection — same as if `None` were passed. The `VALID_SEASONS`
set acts as the gate:

```python
VALID_SEASONS = {"spring", "summer", "fall", "winter"}
if season and season.lower() in VALID_SEASONS:
    ...  # use provided season
else:
    ...  # auto-detect
```

---

#### Return structure

The full season dict from `_season_data`, plus a `detected_season` boolean. Example for spring:

```python
{
    "season": "spring",
    "watering": "Increase watering frequency as plants break dormancy ...",
    "fertilizing": "Resume feeding with a balanced fertilizer ...",
    "light": "Days are lengthening — move plants closer to windows ...",
    "pests": "Watch for spider mites and aphids as temperatures rise ...",
    "detected_season": True   # True = auto-detected; False = caller specified
}
```

---

#### Implementation Notes

*Fill this in after testing.*

**Test: does calling with `season=None` return the correct season for the current month?**
```
Current month: June
Expected season: summer
Returned season: summer (detected_season=True)
```

**Test: does calling with `season="winter"` return winter data regardless of the current month?**
```
Yes — passing season="winter" returns the Winter dict with detected_season=False,
even though the current month (June) auto-detects to summer.
```
