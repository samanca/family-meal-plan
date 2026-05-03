import os
import json
import html
import re
import shutil
import base64
from pathlib import Path
from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SITE_DIR = Path("site")
SITE_DIR.mkdir(exist_ok=True)

IMAGE_DIR = SITE_DIR / "images"
IMAGE_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = """
You generate practical weekly family meal-plan websites.
Return JSON only. Follow the schema exactly.
"""

USER_PROMPT = """
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
- Create exactly one recipe for each day: Sunday, Monday, Tuesday, Wednesday, Thursday, Friday.
- Also create a Whole Foods aisle-ordered grocery list.
- Grocery quantities must be specific for 6 people.
- Keep instructions concise and realistic.
- Include toddler serving notes for choking-risk reduction and texture.
"""

MEAL_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["week_title", "meals", "grocery_list"],
    "properties": {
        "week_title": {"type": "string"},
        "meals": {
            "type": "array",
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
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "instructions": {"type": "array", "items": {"type": "string"}},
                    "toddler_notes": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
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
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def slugify(value: str) -> str:
    value = value.lower().strip().replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or "recipe"


def page_template(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 900px;
      margin: 0 auto;
      padding: 24px;
      line-height: 1.55;
      background: #faf8f4;
      color: #222;
    }}
    .card {{
      background: #fff;
      border-radius: 18px;
      padding: 22px;
      margin: 18px 0;
      box-shadow: 0 4px 18px rgba(0,0,0,0.08);
    }}
    h1, h2 {{ margin-bottom: 8px; }}
    a {{
      color: #236b4e;
      font-weight: 700;
      text-decoration: none;
    }}
    a:hover {{ text-decoration: underline; }}
    ul, ol {{ padding-left: 22px; }}
    li {{ margin: 6px 0; }}
    .tag {{
      display: inline-block;
      background: #eef5ef;
      padding: 4px 9px;
      border-radius: 999px;
      margin: 3px;
      font-size: 14px;
    }}
    .meal-photo {{
      width: 100%;
      border-radius: 18px;
      margin: 14px 0;
      box-shadow: 0 4px 18px rgba(0,0,0,0.08);
      background: #eef0e8;
    }}
    .photo {{
      background: #eef0e8;
      border: 1px dashed #bbc2b4;
      border-radius: 16px;
      padding: 18px;
      margin: 14px 0;
      color: #555;
    }}
    .small {{ color: #666; font-size: 14px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def extract_json_from_response(response) -> str:
    text = getattr(response, "output_text", None)
    if text and text.strip():
        return text.strip()

    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            content_text = getattr(content, "text", None)
            if content_text:
                chunks.append(content_text)

    joined = "\n".join(chunks).strip()
    if joined:
        return joined

    raise ValueError(f"OpenAI returned no text output. Raw response: {response}")


def generate_meal_plan() -> dict:
    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "weekly_meal_plan",
                "strict": True,
                "schema": MEAL_PLAN_SCHEMA,
            }
        },
    )

    text = extract_json_from_response(response)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print("MODEL OUTPUT WAS NOT VALID JSON. FIRST 2000 CHARS:")
        print(repr(text[:2000]))
        raise

    validate_meal_plan(data)
    return data


def validate_meal_plan(data: dict) -> None:
    required_days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    meals = data.get("meals", [])
    days = [m.get("day") for m in meals]

    if len(meals) != 6:
        raise ValueError(f"Expected 6 meals, got {len(meals)}.")

    missing = [day for day in required_days if day not in days]
    if missing:
        raise ValueError(f"Missing required meal days: {missing}. Got days: {days}")

    if not data.get("grocery_list"):
        raise ValueError("Missing grocery_list.")


def generate_meal_image(meal: dict) -> str | None:
    slug = meal["slug"]
    image_path = IMAGE_DIR / f"{slug}.png"

    prompt = (
        "Create a realistic, appetizing overhead food photo for a family recipe. "
        "The meal should look healthy, homemade, organic, and toddler-friendly. "
        "Make it simple and achievable, not fancy restaurant plating. "
        "No text, no labels, no people, no branded packaging, no logos. "
        "Use natural light and a clean kitchen-table look. "
        f"Meal title: {meal['title']}. "
        f"Visual details: {meal.get('image_prompt', '')}"
    )

    try:
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="low",
            n=1,
        )

        image_base64 = result.data[0].b64_json
        image_path.write_bytes(base64.b64decode(image_base64))
        print(f"Generated image for {meal['title']}: {image_path}")
        return f"images/{slug}.png"

    except Exception as exc:
        print(f"Image generation failed for {meal['title']}: {exc}")
        return None


def write_site(data: dict) -> None:
    # Remove old generated pages and old generated images.
    if SITE_DIR.exists():
        for child in SITE_DIR.iterdir():
            if child.is_file() and child.suffix == ".html":
                child.unlink()
            elif child.is_dir() and child.name != "images" and child.name != "assets":
                shutil.rmtree(child)

    if IMAGE_DIR.exists():
        for image_file in IMAGE_DIR.glob("*.png"):
            image_file.unlink()
    else:
        IMAGE_DIR.mkdir(exist_ok=True)

    home_sections = [
        f"<h1>{html.escape(data['week_title'])}</h1>",
        '<p class="small">Generated automatically for Cozyla recipe import.</p>',
        '<div class="card"><h2>Weekly Meals</h2><ul>',
    ]

    used_slugs = set()
    for meal in data["meals"]:
        base_slug = slugify(f"{meal['day']} {meal['title']}")
        slug = base_slug
        count = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{count}"
            count += 1

        used_slugs.add(slug)
        meal["slug"] = slug

        # Generate image after slug is assigned.
        meal["image_file"] = generate_meal_image(meal)

        home_sections.append(
            f'<li><a href="{slug}.html">{html.escape(meal["day"])} — {html.escape(meal["title"])}</a></li>'
        )

    home_sections.extend([
        "</ul></div>",
        '<div class="card"><h2>Shopping List</h2><p><a href="grocery-list.html">Open Whole Foods Organic Grocery List</a></p></div>',
    ])

    (SITE_DIR / "index.html").write_text(
        page_template(data["week_title"], "\n".join(home_sections)),
        encoding="utf-8",
    )

    for meal in data["meals"]:
        tags_html = "".join(
            f'<span class="tag">{html.escape(str(tag))}</span>'
            for tag in meal.get("tags", [])
        )

        ingredients_html = "".join(
            f"<li>{html.escape(str(item))}</li>"
            for item in meal.get("ingredients", [])
        )

        instructions_html = "".join(
            f"<li>{html.escape(str(step))}</li>"
            for step in meal.get("instructions", [])
        )

        toddler_html = "".join(
            f"<li>{html.escape(str(note))}</li>"
            for note in meal.get("toddler_notes", [])
        )

        if meal.get("image_file"):
            image_html = (
                f'<img class="meal-photo" '
                f'src="{html.escape(meal["image_file"])}" '
                f'alt="{html.escape(meal["title"])}">'
            )
        else:
            image_html = (
                '<div class="photo">'
                f'<strong>Suggested photo/search prompt:</strong> {html.escape(meal.get("image_prompt", ""))}'
                '</div>'
            )

        body = f"""
<h1>{html.escape(meal["day"])} — {html.escape(meal["title"])}</h1>

{image_html}

<div class="card">
  <p><strong>Cook Time:</strong> {html.escape(meal["cook_time"])}</p>
  <p><strong>Method:</strong> {html.escape(meal["method"])}</p>
  <p>{tags_html}</p>
</div>

<div class="card">
  <h2>Ingredients for 6</h2>
  <ul>{ingredients_html}</ul>
</div>

<div class="card">
  <h2>Instructions</h2>
  <ol>{instructions_html}</ol>
</div>

<div class="card">
  <h2>Toddler Notes</h2>
  <ul>{toddler_html}</ul>
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
        items_html = "".join(
            f"<li>{html.escape(str(item))}</li>"
            for item in section.get("items", [])
        )
        grocery_body += f"""
<div class="card">
  <h2>{html.escape(section["section"])}</h2>
  <ul>{items_html}</ul>
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
