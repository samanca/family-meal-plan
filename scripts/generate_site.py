import os
import json
import html
from datetime import datetime, timedelta
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

Output JSON only with:
{
  "week_title": "...",
  "meals": [
    {
      "day": "Sunday",
      "title": "...",
      "cook_time": "...",
      "method": "...",
      "image_prompt": "...",
      "ingredients": ["..."],
      "instructions": ["..."],
      "toddler_notes": ["..."],
      "tags": ["..."]
    }
  ],
  "grocery_list": [
    {
      "section": "Produce",
      "items": ["..."]
    }
  ]
}
"""

response = client.responses.create(
    model="gpt-4.1-mini",
    input=PROMPT,
)

text = response.output_text
data = json.loads(text)

def slugify(s):
    return (
        s.lower()
        .replace("&", "and")
        .replace(",", "")
        .replace("—", "-")
        .replace(" ", "-")
    )

def page_template(title, body):
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 820px;
      margin: 0 auto;
      padding: 24px;
      line-height: 1.5;
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
    h1, h2 {{ margin-bottom: 8px; }}
    a {{ color: #236b4e; font-weight: 600; }}
    .tag {{
      display: inline-block;
      background: #eef5ef;
      padding: 4px 8px;
      border-radius: 999px;
      margin: 3px;
      font-size: 14px;
    }}
    img {{
      width: 100%;
      border-radius: 16px;
      margin: 12px 0;
    }}
  </style>
</head>
<body>
{body}
</body>
</html>"""

# Homepage
home_sections = [f"<h1>{html.escape(data['week_title'])}</h1>"]
home_sections.append('<div class="card"><h2>Weekly Meals</h2><ul>')

for meal in data["meals"]:
    slug = slugify(meal["day"] + "-" + meal["title"])
    meal["slug"] = slug
    home_sections.append(
        f'<li><a href="{slug}.html">{html.escape(meal["day"])} — {html.escape(meal["title"])}</a></li>'
    )

home_sections.append('</ul></div>')
home_sections.append('<div class="card"><h2>Shopping List</h2><p><a href="grocery-list.html">Open Whole Foods Grocery List</a></p></div>')

(SITE_DIR / "index.html").write_text(
    page_template(data["week_title"], "\n".join(home_sections)),
    encoding="utf-8",
)

# Recipe pages
for meal in data["meals"]:
    body = f"""
<h1>{html.escape(meal["day"])} — {html.escape(meal["title"])}</h1>

<div class="card">
  <p><strong>Cook Time:</strong> {html.escape(meal["cook_time"])}</p>
  <p><strong>Method:</strong> {html.escape(meal["method"])}</p>
  <p>{''.join(f'<span class="tag">{html.escape(tag)}</span>' for tag in meal["tags"])}</p>
</div>

<div class="card">
  <h2>Ingredients for 6</h2>
  <ul>
    {''.join(f'<li>{html.escape(i)}</li>' for i in meal["ingredients"])}
  </ul>
</div>

<div class="card">
  <h2>Instructions</h2>
  <ol>
    {''.join(f'<li>{html.escape(i)}</li>' for i in meal["instructions"])}
  </ol>
</div>

<div class="card">
  <h2>Toddler Notes</h2>
  <ul>
    {''.join(f'<li>{html.escape(i)}</li>' for i in meal["toddler_notes"])}
  </ul>
</div>

<p><a href="index.html">Back to weekly plan</a></p>
"""
    (SITE_DIR / f"{meal['slug']}.html").write_text(
        page_template(meal["title"], body),
        encoding="utf-8",
    )

# Grocery page
grocery_body = "<h1>Whole Foods Organic Grocery List</h1>"
for section in data["grocery_list"]:
    grocery_body += f"""
<div class="card">
  <h2>{html.escape(section["section"])}</h2>
  <ul>
    {''.join(f'<li>{html.escape(item)}</li>' for item in section["items"])}
  </ul>
</div>
"""

grocery_body += '<p><a href="index.html">Back to weekly plan</a></p>'

(SITE_DIR / "grocery-list.html").write_text(
    page_template("Whole Foods Grocery List", grocery_body),
    encoding="utf-8",
)
