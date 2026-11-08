#!/usr/bin/env python3
"""Generate the website's HTML pages from _editor/content.json.

    python3 _editor/build.py

Used by the editor app (editor.py), but can also be run on its own after
editing content.json by hand. Standard library only.
"""
from __future__ import annotations

import json
import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

EDITOR_DIR = Path(__file__).resolve().parent
ROOT = EDITOR_DIR.parent
CONTENT_FILE = EDITOR_DIR / "content.json"


# ---------------------------------------------------------------------------
# Rich-text sanitizing
# ---------------------------------------------------------------------------
_SAFE_URL = re.compile(r"^(https?:|mailto:|tel:|#|/|\.|[^:]*$)", re.I)


def is_external(href: str) -> bool:
    return href.startswith(("http://", "https://"))


def link_attrs(href: str) -> str:
    """href plus target/rel for links that leave the site."""
    attrs = f'href="{escape(href)}"'
    if is_external(href):
        attrs += ' target="_blank" rel="noopener"'
    return attrs


class _Sanitizer(HTMLParser):
    """Keeps only <p> (block mode), <br>, <strong>, <em> and <a href>.

    The editor's rich-text boxes produce browser-flavoured HTML (<div>, <b>,
    &nbsp;, styles…). This normalises it to the small subset the site uses.
    """

    INLINE = {"strong": "strong", "b": "strong", "em": "em", "i": "em", "a": "a"}
    BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}

    def __init__(self, block: bool):
        super().__init__(convert_charrefs=True)
        self.block = block
        self.out: list[str] = []
        self.stack: list[str] = []  # open inline tags
        self.in_p = False
        self.skip = 0  # inside <script>/<style>

    # helpers
    def _open_p(self):
        if self.block and not self.in_p:
            self.out.append("<p>")
            self.in_p = True
            for tag in self.stack:  # reopen inline formatting
                self.out.append(f"<{tag}>")

    def _close_p(self):
        if self.block and self.in_p:
            for tag in reversed(self.stack):
                self.out.append(f"</{tag}>")
            self.out.append("</p>")
            self.in_p = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif self.skip:
            return
        elif tag in self.BLOCKS:
            if self.block:
                self._close_p()
            elif self.out:
                self.out.append("<br>")
        elif tag == "br":
            self._open_p()
            self.out.append("<br>")
        elif tag in self.INLINE:
            name = self.INLINE[tag]
            self._open_p()
            if name == "a":
                href = (dict(attrs).get("href") or "").strip()
                if not href or not _SAFE_URL.match(href):
                    self.stack.append("")  # placeholder so the end tag pairs up
                    return
                self.out.append(f"<a {link_attrs(href)}>")
            else:
                self.out.append(f"<{name}>")
            self.stack.append(name)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif self.skip:
            return
        elif tag in self.BLOCKS:
            self._close_p()
        elif tag in self.INLINE and self.stack:
            name = self.stack.pop()
            if name:
                self.out.append(f"</{name}>")

    def handle_data(self, data):
        if self.skip:
            return
        data = data.replace("\xa0", " ")
        if not data.strip() and (not self.block or not self.in_p):
            if not self.out or self.out[-1] in ("<br>", "<p>"):
                return
        self._open_p()
        self.out.append(escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            name = self.stack.pop()
            if name:
                self.out.append(f"</{name}>")
        self._close_p()
        html = "".join(self.out)
        html = re.sub(r"[ \t\r\n]+", " ", html)
        html = re.sub(r"\s*<br>\s*", "<br>", html)
        html = re.sub(r"<p>\s*(<br>\s*)*</p>", "", html)
        html = re.sub(r"<p>\s*(<br>)+", "<p>", html)
        html = re.sub(r"(<br>)+\s*</p>", "</p>", html)
        html = re.sub(r"^(<br>)+|(<br>)+$", "", html.strip())
        html = re.sub(r"<(strong|em)>\s*</\1>", "", html)
        return html.strip()


def sanitize(html: str, block: bool = False) -> str:
    parser = _Sanitizer(block)
    parser.feed(html or "")
    parser.close()
    return parser.result()


def sanitize_content(content: dict) -> dict:
    """Clean every rich-text field in place and return the content."""
    for item in content["news"]["items"]:
        item["text"] = sanitize(item.get("text", ""))
    content["about"]["body"] = sanitize(content["about"].get("body", ""), block=True)
    for page in content["pages"]:
        if "intro" in page:
            page["intro"] = sanitize(page["intro"], block=True)
        for sec in page.get("sections", []):
            sec["body"] = sanitize(sec.get("body", ""), block=True)
    return content


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
ICONS = {
    "home": '<path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>',
    "x": '<path d="M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z"/>',
    "linkedin": '<path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.125 2.062 2.062 0 0 1 0 4.125zM7.119 20.452H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>',
    "youtube": '<path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>',
    "mail": '<path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z"/>',
    "pin": '<path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z"/>',
    "chevron": '<path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z"/>',
    "prev": '<path d="M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>',
    "next": '<path d="M8.59 16.59 10 18l6-6-6-6-1.41 1.41L13.17 12z"/>',
    "up": '<path d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"/>',
}
SOCIAL_ICONS = ["x", "linkedin", "youtube", "mail"]


def icon(name: str, cls: str = "icon") -> str:
    return f'<svg class="{cls}" aria-hidden="true"><use href="#i-{name}"/></svg>'


def sprite() -> str:
    symbols = "\n".join(
        f'    <symbol id="i-{name}" viewBox="0 0 24 24">{path}</symbol>' for name, path in ICONS.items()
    )
    return f'  <svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true">\n{symbols}\n  </svg>\n'


# Colors the editor can change, with the site's defaults (see :root in site.css).
THEME_DEFAULTS = {
    "accent": "#40b0bf",
    "nav-bg": "#ffffff",
    "nav-link": "#232323",
    "nav-link-hover": "#40b0bf",
    "social-color": "#232323",
    "social-hover": "#40b0bf",
    "hero-name": "#fafafa",
    "hero-tagline": "#fafafa",
    "hero-line": "#fafafa",
    "hero-credit": "#fafafa",
    "news-title": "#fafafa",
    "about-title": "#232323",
    "about-text": "#232323",
    "contact-title": "#fafafa",
    "footer-text": "#bdbdbd",
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def valid_color(value) -> str | None:
    return value.lower() if isinstance(value, str) and _HEX.match(value) else None


def theme_style(c: dict) -> str:
    theme = c.get("theme") or {}
    decls = [f"--{k}: {valid_color(theme.get(k))};" for k in THEME_DEFAULTS if valid_color(theme.get(k))]
    if not decls:
        return ""
    return '  <style id="theme">:root { ' + " ".join(decls) + " }</style>\n"


def a_attrs(href: str, new_tab: bool | None = None) -> str:
    attrs = f'href="{escape(href)}"'
    if new_tab if new_tab is not None else is_external(href):
        attrs += ' target="_blank" rel="noopener"'
    return attrs


GA_ID_RE = re.compile(r"G-[A-Z0-9]{4,20}")


def analytics(s: dict) -> str:
    """Google Analytics 4 tag. Only reports when served from the live site's host,
    so the editor preview and local copies are not counted."""
    ga_id = (s.get("gaMeasurementId") or "").strip().upper()
    if not GA_ID_RE.fullmatch(ga_id):
        return ""
    host = urlparse(s["url"]).hostname or ""
    return f"""  <script>
    if (location.hostname === {json.dumps(host)}) {{
      var ga = document.createElement("script");
      ga.async = true;
      ga.src = "https://www.googletagmanager.com/gtag/js?id={ga_id}";
      document.head.appendChild(ga);
      window.dataLayer = window.dataLayer || [];
      window.gtag = function () {{ dataLayer.push(arguments); }};
      gtag("js", new Date());
      gtag("config", "{ga_id}");
    }}
  </script>
"""


def head(c: dict, title: str, description: str, path: str) -> str:
    s = c["site"]
    url = s["url"].rstrip("/") + "/"
    og_image = s.get("ogImage") or c["hero"]["image"]
    return f"""<!DOCTYPE html>
<!-- Generated from _editor/content.json — edit with `python3 _editor/editor.py`, not by hand. -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="author" content="{escape(s['author'])}">
  <link rel="canonical" href="{url}{path}">
  <link rel="icon" href="{escape(s['favicon'])}" type="image/png">
  <link rel="apple-touch-icon" href="{escape(s['favicon'])}">
  <meta name="theme-color" content="#232323">

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{escape(s['author'])}">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{url}{path}">
  <meta property="og:image" content="{url}{escape(og_image)}">
  <meta name="twitter:card" content="summary_large_image">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Oswald:wght@300;400;500;600;700&display=swap">
  <link rel="stylesheet" href="assets/css/site.css">
{theme_style(c)}{analytics(s)}  <script src="assets/js/site.js" defer></script>
</head>
<body>
"""


def nav(c: dict, current_file: str) -> str:
    n = c["nav"]
    cur = lambda href: ' aria-current="page"' if href == current_file else ""

    links = [
        f'          <li><a class="nav__link" href="index.html"{cur("index.html")}>{icon("home")}'
        f'<span class="visually-hidden">Home</span></a></li>'
    ]
    for link in n["links"]:
        links.append(
            f'          <li><a class="nav__link" {a_attrs(link["href"], link.get("newTab"))}{cur(link["href"])}>'
            f'{escape(link["label"])}</a></li>'
        )
    if n.get("dropdown"):
        items = "\n".join(
            f'              <li><a {a_attrs(d["href"], d.get("newTab"))}>'
            f'{icon(d["icon"]) + " " if d.get("icon") else ""}{escape(d["label"])}</a></li>'
            for d in n["dropdown"]
        )
        links.append(f"""          <li class="nav__dropdown">
            <button class="nav__link" type="button" aria-expanded="false" aria-controls="links-menu">
              {escape(n.get("dropdownLabel") or "Links")} {icon("chevron", "icon chevron")}
            </button>
            <ul class="nav__submenu" id="links-menu" hidden>
{items}
            </ul>
          </li>""")

    social = "\n".join(
        f'          <a {a_attrs(sc["href"])} aria-label="{escape(sc["label"])}"'
        + (f' style="--icon-color: {valid_color(sc.get("color"))}"' if valid_color(sc.get("color")) else "")
        + f'>{icon(sc["icon"])}</a>'
        for sc in c["social"]
    )

    return sprite() + f"""
  <a class="skip-link" href="#main">Skip to content</a>

  <header class="site-header">
    <nav class="nav container" aria-label="Main">
      <a class="nav__brand" href="index.html">
        <img src="{escape(c['site']['logo'])}" alt="{escape(c['site']['author'])} — home" width="50" height="48">
      </a>

      <button class="nav__toggle" type="button" aria-controls="nav-menu" aria-expanded="false" aria-label="Toggle navigation">
        <span></span><span></span><span></span>
      </button>

      <div class="nav__menu" id="nav-menu">
        <ul class="nav__links">
{chr(10).join(links)}
        </ul>

        <div class="nav__social">
{social}
        </div>
      </div>
    </nav>
  </header>
"""


def footer(c: dict) -> str:
    return f"""
  <footer class="site-footer">
    <p>© <span data-year>2026</span> {escape(c['site']['author'])} — All Rights Reserved</p>
  </footer>

  <button class="to-top" type="button" aria-label="Back to top">{icon("up")}</button>
</body>
</html>
"""


def news_card(item: dict) -> str:
    date = item.get("date", "")
    button = ""
    if item.get("link"):
        button = (
            f'\n              <a class="btn" {a_attrs(item["link"], True)}>'
            f'Learn more <span aria-hidden="true">›</span></a>'
        )
    img = ""
    if item.get("image"):
        img = f'\n            <img class="news-card__img" src="{escape(item["image"])}" alt="" loading="lazy" decoding="async">'
    return f"""          <li class="news-card">{img}
            <div class="news-card__body">
              <h3 class="news-card__title">{escape(item.get("title", ""))}</h3>
              <time class="news-card__date" datetime="{escape(date.replace("/", "-"))}">{escape(date)}</time>
              <p class="news-card__text">{sanitize(item.get("text", ""))}</p>{button}
            </div>
          </li>"""


def autoplay_seconds(news: dict) -> float:
    try:
        return max(0.0, float(news.get("autoplaySeconds") or 0))
    except (TypeError, ValueError):
        return 0.0


HERO_OBJECTS = ("name", "tagline", "credit")
ALIGNMENTS = ("left", "center", "right")


def hero_positions(hero: dict) -> dict:
    """Validated custom positions for the hero text, or {} for the automatic layout.

    Each entry is {"x": %, "y": %, "align": left|center|right}: x is where the
    text's left edge / centre / right edge sits across the banner, y is where
    its vertical centre sits down the banner.
    """
    out = {}
    for key, p in (hero.get("positions") or {}).items():
        if key not in HERO_OBJECTS or not isinstance(p, dict):
            continue
        try:
            x = min(100.0, max(0.0, float(p.get("x", 0))))
            y = min(100.0, max(0.0, float(p.get("y", 50))))
        except (TypeError, ValueError):
            continue
        align = p.get("align") if p.get("align") in ALIGNMENTS else "left"
        out[key] = {"x": round(x, 2), "y": round(y, 2), "align": align}
    return out


def hero_obj_attrs(key: str, positions: dict) -> str:
    p = positions.get(key)
    if not p:
        return f' data-obj="{key}"'
    return f' data-obj="{key}" style="--x: {p["x"]:g}%; --y: {p["y"]:g}%" data-align="{p["align"]}"'


def render_index(c: dict) -> str:
    s, hero, news, about, contact = c["site"], c["hero"], c["news"], c["about"], c["contact"]
    cards = "\n".join(news_card(i) for i in news["items"] if not i.get("hidden"))
    body = sanitize(about["body"], block=True).replace("</p><p>", "</p>\n          <p>")
    office = "<br>".join(escape(line) for line in contact["office"].splitlines() if line.strip())
    hero_bg = (
        "background-image: linear-gradient(90deg, rgb(0 0 0 / .55), rgb(0 0 0 / .1) 70%), "
        f"url('{escape(hero['image'])}')"
    )
    positions = hero_positions(hero)
    place = lambda key: hero_obj_attrs(key, positions)
    credit = (
        f'\n      <p class="hero__credit hero__obj"{place("credit")}>{escape(hero["credit"])}</p>'
        if hero.get("credit") else ""
    )

    return head(c, s["title"], s["description"], "") + nav(c, "index.html") + f"""
  <main id="main">
    <section class="hero{" hero--free" if positions else ""}" style="{hero_bg}">
      <div class="container hero__content">
        <h1 class="hero__title hero__obj"{place("name")}>{escape(hero["name"])}</h1>
        <p class="hero__tagline hero__obj"{place("tagline")}>{escape(hero["tagline"])}</p>
      </div>{credit}
    </section>

    <section class="news" aria-labelledby="news-title">
      <div class="container">
        <h2 class="section-title" id="news-title">{escape(news["title"])}</h2>
        <div class="carousel" data-carousel data-autoplay="{autoplay_seconds(news)}">
          <ul class="carousel__track" id="news-track" tabindex="0" aria-label="News items, scroll horizontally">
{cards}
          </ul>
          <div class="carousel__controls">
            <button class="carousel__btn carousel__btn--prev" type="button" aria-label="Previous" aria-controls="news-track">{icon("prev")}</button>
            <button class="carousel__btn carousel__btn--next" type="button" aria-label="Next" aria-controls="news-track">{icon("next")}</button>
          </div>
        </div>
      </div>
    </section>

    <section class="about" id="about" aria-labelledby="about-title">
      <div class="container about__grid">
        <div class="about__text">
          <h2 class="section-title" id="about-title">{escape(about["title"])}</h2>
          {body}
        </div>
        <div class="about__photo">
          <img src="{escape(about["photo"])}" alt="{escape(about.get("photoAlt", ""))}" loading="lazy" decoding="async">
        </div>
      </div>
    </section>

    <section class="contact" id="contact" aria-labelledby="contact-title">
      <div class="container">
        <h2 class="section-title" id="contact-title">{escape(contact["title"])}</h2>
        <div class="contact__grid">
          <div class="contact-card">
            {icon("mail")}
            <h3>Email</h3>
            <p><a href="mailto:{escape(contact["email"])}">{escape(contact["email"])}</a></p>
          </div>
          <div class="contact-card">
            {icon("pin")}
            <h3>Office</h3>
            <address>{office}</address>
          </div>
        </div>
      </div>
    </section>
  </main>
""" + footer(c)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def research_section(sec: dict, slug: str) -> str:
    meta = " · ".join(escape(x) for x in (sec.get("period"), sec.get("place")) if x)
    meta = f'\n            <p class="research-item__meta">{meta}</p>' if meta else ""
    body = sanitize(sec.get("body", ""), block=True).replace("</p><p>", "</p>\n            <p>")
    papers = [p for p in sec.get("papers", []) if p.get("label")]
    paper_list = ""
    if papers:
        items = "\n".join(
            f'              <li><a {link_attrs(p["href"])}>{escape(p["label"])}</a></li>' if p.get("href")
            else f'              <li>{escape(p["label"])}</li>'
            for p in papers
        )
        paper_list = f"""
            <div class="research-item__papers">
              <h3>Key papers</h3>
              <ul>
{items}
              </ul>
            </div>"""
    figure = ""
    if sec.get("image"):
        src = escape(sec["image"])
        caption = escape(sec.get("caption", ""))
        if sec.get("source"):
            label = escape(sec["source"])
            source = f'<a {link_attrs(sec["sourceHref"])}>{label}</a>' if sec.get("sourceHref") else label
            caption += f'{" " if caption else ""}<span class="research-item__source">Figure: {source}</span>'
        figure = f"""
          <figure class="research-item__figure">
            <a href="{src}" target="_blank" rel="noopener" aria-label="Open figure at full size">
              <img src="{src}" alt="{escape(sec.get("imageAlt") or sec.get("caption", ""))}" loading="lazy" decoding="async">
            </a>{f"{chr(10)}            <figcaption>{caption}</figcaption>" if caption else ""}
          </figure>"""
    return f"""
    <section class="research-item{"" if figure else " research-item--text"}" id="{slug}" aria-labelledby="{slug}-title">
      <div class="container research-item__grid">
        <div class="research-item__text">{meta}
          <h2 id="{slug}-title">{escape(sec.get("title", ""))}</h2>
          <div class="research-item__body">
            {body}
          </div>{paper_list}
        </div>{figure}
      </div>
    </section>
"""


def page_header_bg(page: dict) -> str:
    """Inline background style for a sub page's header, or "" when no image is set."""
    img = (page.get("headerImage") or "").strip()
    if not img:
        return ""
    return (
        ' style="background-image: linear-gradient(90deg, rgb(0 0 0 / .7), rgb(0 0 0 / .3) 75%), '
        f"url('{escape(img)}')\""
    )


def render_research(c: dict, page: dict) -> str:
    title = f'{page["title"]} — {c["site"]["author"]}'
    sections = [s for s in page["sections"] if not s.get("hidden")]
    slugs, seen = [], set()
    for sec in sections:
        slug = base = slugify(sec.get("title", ""))
        n = 2
        while slug in seen:
            slug, n = f"{base}-{n}", n + 1
        seen.add(slug)
        slugs.append(slug)
    intro = sanitize(page.get("intro", ""), block=True)
    toc = "\n".join(
        f'          <li><a href="#{slug}">{escape(sec.get("title", ""))}</a></li>'
        for sec, slug in zip(sections, slugs)
    )
    return head(c, title, page.get("description") or title, page["file"]) + nav(c, page["file"]) + f"""
  <main id="main">
    <section class="page-hero{" page-hero--image" if page_header_bg(page) else ""}"{page_header_bg(page)}>
      <div class="container">
        <h1 class="page-hero__title">{escape(page["heading"])}</h1>
        <div class="page-hero__intro">{intro}</div>
        <ul class="research-toc" aria-label="Research topics">
{toc}
        </ul>
      </div>
    </section>
{"".join(research_section(sec, slug) for sec, slug in zip(sections, slugs))}  </main>
""" + footer(c)


def render_subpage(c: dict, page: dict) -> str:
    if any(not s.get("hidden") for s in page.get("sections", [])):
        return render_research(c, page)
    title = f'{page["title"]} — {c["site"]["author"]}'
    message = f'\n        <p>{escape(page["message"])}</p>' if page.get("message") else ""
    return head(c, title, page.get("description") or title, page["file"]) + nav(c, page["file"]) + f"""
  <main id="main">
    <section class="coming-soon{" coming-soon--image" if page_header_bg(page) else ""}"{page_header_bg(page)}>
      <div>
        <h1>{escape(page["heading"])}</h1>{message}
        <a class="btn btn--light" href="index.html">Back to Home</a>
      </div>
    </section>
  </main>
""" + footer(c)


def render(c: dict, file: str) -> str:
    if file == "index.html":
        return render_index(c)
    for page in c["pages"]:
        if page["file"] == file:
            return render_subpage(c, page)
    raise KeyError(file)


def page_files(c: dict) -> list[str]:
    return ["index.html"] + [p["file"] for p in c["pages"]]


# ---------------------------------------------------------------------------
def load_content() -> dict:
    return json.loads(CONTENT_FILE.read_text(encoding="utf-8"))


def save_content(c: dict) -> None:
    CONTENT_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(c: dict | None = None) -> list[str]:
    c = c if c is not None else load_content()
    written = []
    for file in page_files(c):
        if "/" in file or not file.endswith(".html"):
            raise ValueError(f"Invalid page file name: {file}")
        (ROOT / file).write_text(render(c, file), encoding="utf-8")
        written.append(file)
    return written


if __name__ == "__main__":
    for f in build():
        print("wrote", f)
