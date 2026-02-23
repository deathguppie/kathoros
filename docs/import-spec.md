# Kathoros Import Format Specification

**Version:** 1.1
**For:** AI systems generating import-ready research objects
**Target platform:** Kathoros v0.1.0+

---

## Overview

Kathoros imports research content as a **JSON array of typed objects**.
Each object represents one atomic research unit: a concept, derivation,
prediction, etc.

You may output this directly (raw JSON array) or wrapped in a fenced code block.
Both are accepted:

```json
[{ ... }, { ... }]
```

or

````
```json
[{ ... }, { ... }]
```
````

**Rule:** Respond with the JSON array only — no preamble, no explanation,
no prose before or after. Any non-JSON text surrounding the array will be
stripped by the parser, but pure JSON is preferred.

---

## Object Schema

```json
{
  "name":              "string, required — short unique label (≤ 255 chars)",
  "type":              "string, required — see Type Reference below",
  "description":       "string, required — 1-3 sentence plain-text summary (≤ 1000 chars)",
  "tags":              ["string", ...],
  "math_expression":   "LaTeX string or empty string (≤ 500 chars)",
  "latex":             "full LaTeX block for extended derivations (≤ 2000 chars)",
  "researcher_notes":  "string — caveats, open issues, confidence notes (≤ 2000 chars)",
  "depends_on":        ["Name of another object in this batch", ...],
  "source_file":       "filename or citation the object came from (≤ 255 chars)"
}
```

### Required fields
| Field | Rule |
|---|---|
| `name` | Unique within the batch. Used to resolve `depends_on` references. |
| `type` | Must be one of the 7 valid types (see below). |
| `description` | Plain text. No LaTeX here — use `math_expression` for formulas. |

### Optional fields
| Field | Notes |
|---|---|
| `tags` | Up to 20 strings. Lower-case, no spaces preferred. |
| `math_expression` | Inline LaTeX for the key formula of this object. |
| `latex` | Full display-math block for multi-line derivations. |
| `researcher_notes` | Personal caveats, confidence level, known limitations. |
| `depends_on` | List of `name` values from **this same batch**. Resolved after insert. Leave `[]` if none. |
| `source_file` | Filename, DOI, arXiv ID, or short citation. |

---

## Type Reference

| Type | Use for |
|---|---|
| `concept` | Named ideas, physical quantities, abstract structures |
| `definition` | Formal mathematical or physical definitions |
| `derivation` | Step-by-step derivations; result follows from premises |
| `prediction` | Testable claims about observable outcomes |
| `evidence` | Experimental results, observational data, citations |
| `open_question` | Unresolved problems, gaps, inconsistencies |
| `data` | Numerical values, datasets, measurement results |

> If a type does not match, the importer defaults to `concept`.

---

## `depends_on` — referencing within a batch

Use the exact `name` value of another object in the **same JSON array**.
The importer resolves names to database IDs after all objects are inserted.

```json
[
  {
    "name": "Bekenstein-Hawking entropy",
    "type": "derivation",
    "description": "Entropy of a black hole is proportional to horizon area.",
    "math_expression": "S = \\frac{k_B c^3 A}{4 G \\hbar}",
    "depends_on": []
  },
  {
    "name": "Information paradox",
    "type": "open_question",
    "description": "Hawking radiation is thermal; unitarity requires information recovery.",
    "depends_on": ["Bekenstein-Hawking entropy"]
  }
]
```

**Rules:**
- Only reference objects in the same batch by name.
- Do not create circular dependencies (A depends on B depends on A).
- Unresolvable names are silently dropped — not an error.

---

## Examples by type

### `concept`
```json
{
  "name": "Holographic principle",
  "type": "concept",
  "description": "All information contained in a volume can be encoded on its boundary surface.",
  "tags": ["holography", "entropy", "boundary"],
  "math_expression": "",
  "source_file": "Susskind1995.pdf"
}
```

### `definition`
```json
{
  "name": "Penrose diagram",
  "type": "definition",
  "description": "A conformal diagram representing the causal structure of spacetime, compressing infinite regions into finite boundaries.",
  "tags": ["causal-structure", "conformal", "spacetime"],
  "math_expression": "",
  "researcher_notes": "Assumes asymptotic flatness; not applicable to de Sitter."
}
```

### `derivation`
```json
{
  "name": "Hawking temperature",
  "type": "derivation",
  "description": "A black hole radiates as a black body with temperature inversely proportional to its mass.",
  "math_expression": "T_H = \\frac{\\hbar c^3}{8 \\pi G M k_B}",
  "latex": "T_H = \\frac{\\hbar c^3}{8 \\pi G M k_B}",
  "tags": ["hawking", "temperature", "black-body"],
  "depends_on": ["Bekenstein-Hawking entropy"],
  "source_file": "Hawking1975"
}
```

### `prediction`
```json
{
  "name": "Page curve recovery",
  "type": "prediction",
  "description": "Entanglement entropy of Hawking radiation follows the Page curve, recovering unitarity at the Page time.",
  "tags": ["page-curve", "unitarity", "entanglement"],
  "researcher_notes": "Supported by island formula calculations; experimental verification not yet possible.",
  "depends_on": ["Information paradox"]
}
```

### `evidence`
```json
{
  "name": "EHT black hole shadow",
  "type": "evidence",
  "description": "Event Horizon Telescope imaging of M87* confirms predicted shadow size to within 10%.",
  "tags": ["EHT", "M87", "observation"],
  "source_file": "EHT_Collaboration_2019"
}
```

### `open_question`
```json
{
  "name": "Firewall paradox",
  "type": "open_question",
  "description": "Does an infalling observer encounter a firewall at the horizon, violating the equivalence principle?",
  "tags": ["firewall", "AMPS", "equivalence-principle"],
  "researcher_notes": "AMPS argument (2012) vs. Maldacena-Susskind ER=EPR resolution unresolved.",
  "depends_on": ["Information paradox", "Hawking temperature"]
}
```

### `data`
```json
{
  "name": "Cygnus X-1 mass measurement",
  "type": "data",
  "description": "Stellar-mass black hole in Cygnus X-1 measured at 21.2 ± 2.2 solar masses.",
  "math_expression": "M = 21.2 \\pm 2.2 \\, M_\\odot",
  "tags": ["cygnus-x1", "mass", "measurement"],
  "source_file": "Miller-Jones_2021"
}
```

---

## System prompt (paste into your AI session)

Use this when asking an external AI to generate an import-ready file:

```
You are generating research objects for import into Kathoros, a physics research platform.

Output a single JSON array. No prose before or after it.

Each element must have:
- "name": short unique label
- "type": one of concept | definition | derivation | prediction | evidence | open_question | data
- "description": 1-3 sentence plain-text summary
- "tags": list of lowercase strings
- "math_expression": key formula in LaTeX, or ""
- "latex": full LaTeX derivation block (multi-line), or ""
- "researcher_notes": caveats, confidence, known issues, or ""
- "depends_on": list of names of other objects in this batch that this one builds on
- "source_file": filename, DOI, or arXiv ID, or ""

Rules:
- depends_on must reference names of other objects in the same array only.
- No circular dependencies.
- description must be plain text — no LaTeX.
- math_expression and latex use LaTeX syntax.
- If type is unclear, default to concept.
- Respond with the JSON array only.
```

---

## Validation rules (enforced by Kathoros on import)

| Field | Limit | On violation |
|---|---|---|
| `name` | ≤ 255 chars | Truncated |
| `description` | ≤ 1000 chars | Truncated |
| `math_expression` | ≤ 500 chars | Truncated |
| `latex` | ≤ 2000 chars | Truncated |
| `researcher_notes` | ≤ 2000 chars | Truncated |
| `tags` | ≤ 20 items | Truncated |
| `depends_on` | ≤ 50 items | Truncated |
| `type` | Must be valid | Defaults to `concept` |
| `name` missing | — | Object skipped |
| `type` missing | — | Object skipped |
| Circular `depends_on` | — | Dependency silently dropped |

---

## Minimal valid object

```json
[
  {
    "name": "My concept",
    "type": "concept",
    "description": "A short description of the concept."
  }
]
```

All other fields are optional and default to empty.

---

*All file references relative to `kathoros_main/`.*
