import os
import json
import html
import re
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SITE_DIR = Path("site")
SITE_DIR.mkdir(exist_ok=True)

PROMPT = """
Create a Sunday through Friday healthy meal plan for 6 people.

Rules:
- Toddler-friendly for a 1-year-old.
- Organic Whole Foods ingredients.
- Under 40 minutes per meal.
- Prefer oven and pressure cooker over stovetop.
- No fried foods.
- No pork.
- Limit meat meals to 3–4 of 6.
- Minimize turkey.
- Avoid processed foods.
- Reuse ingredients to reduce waste.
- Create one recipe per day.
- Also create a Whole Foods aisle-ordered grocery list.

Output must follow the provided JSON schema exactly.
"""

MEAL_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["week_title", "meals", "grocery_list"],
    "properties": {
        "week_title": {"type": "string"},
        "meals": {
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "day",
                    "title",
                    "cook_time",
                    "method",
                    "image_prompt",
                    "ingredients",
                    "instructions",
                    "toddler_notes",
                    "tags",
                ],
                "properties": {
                    "day": {"type": "string"},
                    "title": {"type": "string"},
                    "cook_time": {"type": "string"},
                    "method": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "ingredients": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "instructions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "toddler_notes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "grocery_list": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["section", "items"],
                "properties": {
                    "section": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


def page_template(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 860px;
      margin: 0 auto;
      padding: 24px;
      line-height: 1.55;
      background: #faf8f4;
      color: #222;
    }}
    .card {{
      background: white;
      border-radius: 18px;
      padding: 22px;
      margin: 18px 0;
      box-shadow: 0 4px 18px rgba(0,0,0,0.08);
    }}
    h1, h2 {{
      margin-bottom: 8px;
    }}
    a {{
      color: #236b4e;
      font-weight: 600;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    ul, ol {{
      padding-left: 22px;
    }}
    li {{
      margin: 6px 0;
    }}
    .tag {{
      display: inline-block;
      background: #eef5ef;
      padding: 4px 9px;
      border-radius: 999px;
      margin: 3px;
      font-size: 14px;
    }}
    .placeholder {{
      background: #eef0e8;
      border: 1px dashed #bbc2b4;
      border-radius: 16px;
      padding: 18px;
      margin: 14px 0;
      color: #555;
    }}
    .small {{
      color: #666;
      font-size: 14px;
    }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def generate_meal_plan() -> dict:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=PROMPT,
        text={
            "format": {
                "type": "json_schema",
                "name": "weekly_meal_plan",
                "strict": True,
                "schema": MEAL_PLAN_SCHEMA,
            }
        },
    )

    text = response.output_text

    if not text:
        raise ValueError("OpenAI returned an empty response.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print("MODEL OUTPUT START")
        print(repr(text[:2000]))
        print("MODEL OUTPUT END")
        raise exc


def write_site(data: dict) -> None:
    # Clean old generated HTML files, but keep any static assets if you add them later.
    for file in SITE_DIR.glob("*.html"):
        file.unlink()

    home_sections = [
        f"<h1>{html.escape(data['week_title'])}</h1>",
        '<p class="small">Generated automatically for Cozyla recipe import.</p>',
        '<div class="card"><h2>Weekly Meals</h2><ul>',
    ]

    for meal in data["meals"]:
        slug = slugify(f"{meal['day']} {meal['title']}")
        meal["slug"] = slug
        home_sections.append(
            f'<li><a href="{slug}.html">{html.escape(meal["day"])} — {html.escape(meal["title"])}</a></li>'
        )

    home_sections.extend(
        [
            "</ul></div>",
            '<div class="card"><h2>Shopping List</h2><p><a href="grocery-list.html">Open Whole Foods Organic Grocery List</a></p></div>',
        ]
    )

    (SITE_DIR / "index.html").write_text(
        page_template(data["week_title"], "\n".join(home_sections)),
        encoding="utf-8",
    )

    for meal in data["meals"]:
        body = f"""
<h1>{html.escape(meal["day"])} — {html.escape(meal["title"])}</h1>

<div class="card">
  <p><strong>Cook Time:</strong> {html.escape(meal["cook_time"])}</p>
  <p><strong>Method:</strong> {html.escape(meal["method"])}</p>
  <p>{''.join(f'<span class="tag">{html.escape(tag)}</span>' for tag in meal["tags"])}</p>
</div>

<div class="placeholder">
  <strong>Photo prompt:</strong> {html.escape(meal["image_prompt"])}
</div>

<div class="card">
  <h2>Ingredients for 6</h2>
  <ul>
    {''.join(f'<li>{html.escape(item)}</li>' for item in meal["ingredients"])}
  </ul>
</div>

<div class="card">
  <h2>Instructions</h2>
  <ol>
    {''.join(f'<li>{html.escape(step)}</li>' for step in meal["instructions"])}
  </ol>
</div>

<div class="card">
  <h2>Toddler Notes</h2>
  <ul>
    {''.join(f'<li>{html.escape(note)}</li>' for note in meal["toddler_notes"])}
  </ul>
</div>

<p><a href="index.html">← Back to weekly plan</a></p>
"""
        (SITE_DIR / f"{meal['slug']}.html").write_text(
            page_template(meal["title"], body),
            encoding="utf-8",
        )

    grocery_body = """
<h1>Whole Foods Organic Grocery List</h1>
<p class="small">Grouped in a practical Whole Foods aisle-walking order.</p>
"""

    for section in data["grocery_list"]:
        grocery_body += f"""
<div class="card">
  <h2>{html.escape(section["section"])}</h2>
  <ul>
    {''.join(f'<li>{html.escape(item)}</li>' for item in section["items"])}
  </ul>
</div>
"""

    grocery_body += '<p><a href="index.html">← Back to weekly plan</a></p>'

    (SITE_DIR / "grocery-list.html").write_text(
        page_template("Whole Foods Organic Grocery List", grocery_body),
        encoding="utf-8",
    )


if __name__ == "__main__":
    meal_plan = generate_meal_plan()
    write_site(meal_plan)
    print("Generated weekly meal plan site successfully.")
