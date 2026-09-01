# QalamStudio

Pakistan's free AI writing studio (Flask) — Urdu writer, freelancer toolkit, subtitles, proofreader, YouTube SEO, resume builder, WhatsApp replies, script timing.

## SEO strategy (ranking-ready)

### On-page (implemented)

- Unique `<title>` + meta description on every public page
- Canonical URLs, `index,follow`, Open Graph + Twitter cards
- Organization + WebSite JSON-LD site-wide; SoftwareApplication on tools; FAQPage on FAQ blocks; Article on blog posts; WebApplication on home
- Rich intro copy + internal links under each tool (not thin "tool-only" pages)
- FAQ accordion with schema on tools, home, about, contact
- Related tools grid for interlinking (writer ↔ subtitles ↔ SEO ↔ timing, etc.)
- Footer link columns to all tools + company pages
- Dynamic `sitemap.xml` (static routes + published posts) and `robots.txt`
- Seed blog posts with tool deep-links when `blogs.json` is empty

### Content pillars (publish monthly)

1. **Urdu / Roman Urdu writing** — scripts, captions, product copy
2. **YouTube growth** — SEO, subtitles, timing
3. **Freelancing** — proposals, invoices, resumes
4. **WhatsApp commerce** — auto-replies for PK shops

Each post should: answer one search intent, link 2–4 tools, use one clear H1, short sections, and a CTA to a tool.

### Technical checklist

- [ ] Set `GOOGLE_SITE_VERIFICATION` env for Search Console
- [ ] Submit `https://yourdomain/sitemap.xml` in GSC
- [ ] Confirm HTTPS and preferred domain
- [ ] Monitor Core Web Vitals (keep images compressed)
- [ ] Replace seed posts via Admin → Blog with fresher long-form when ready
- [ ] Optional: `hreflang` later if you split full Urdu UI routes

### Keyword themes (examples)

- urdu ai writer / roman urdu generator
- youtube subtitles urdu srt
- fiverr proposal generator
- whatsapp business auto reply urdu
- urdu resume maker
- urdu grammar checker online

Target **Pakistan + Urdu intent** first; avoid competing only on generic global "AI writer" terms.

### Internal linking rules

- Every tool page → 3–4 related tools + blog when relevant
- Every blog post → `related_tool_keys` in JSON (resolved to URLs in the view)
- Home FAQ + intro → primary tools + blog
- Footer always lists all tools

### Off-page (ongoing)

- Share workflow posts in Pakistani creator / freelancer communities
- Embed tool URLs in YouTube video descriptions you produce
- Collect genuine reviews mentioning "Urdu" and "Pakistan"

## Local run

```bash
export FLASK_ENV=development QALAM_ALLOW_DEV_SECRET=1
export GROQ_API_KEY=...
pip install -r requirements.txt
flask --app app run
```
