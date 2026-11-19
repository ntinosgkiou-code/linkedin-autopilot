# Routine: post (unattended)

Goal: publish one original, high-quality post in the user's voice.

1. Read `config.yaml`. If `posts.enabled` is false, end the run. Run `uv run tools/guard.py check post`. If it returns not ok, end the run.
2. Read the last 10 files in `data/posts/` so you never repeat a topic, hook or story.
3. Pick the `posts.topics` entry that has been used least recently. Optionally use `get_feed` or `search_posts`
   (max 3 calls) to find a timely angle in the user's niche. Never copy anyone's text.
4. Write the post following `posts.style` and `profile.language`, and grounded in `profile.about_me` and `offer`:
   - Line 1: a hook under 12 words, either specific or contrarian.
   - Body: one idea, a concrete example or number from config. Never invent results or clients.
   - End: a question or a soft CTA. Do not sell in every post. Mention the offer directly in at most 1 of 3 posts.
   - Max 3 hashtags on the last line. Under 2,800 characters.
5. Save it as `data/posts/<YYYY-MM-DD>-<short-slug>.md` (only the post text).
6. If `posts.approval` is `auto` AND `outreach.mode` is `live`: run
   `uv run tools/linkedin_post.py publish data/posts/<file>.md`. If it returns an error about the token,
   write the error at the top of `data/hot_leads.md` under "ACTION NEEDED" and end the run.
   Otherwise (draft mode or dry_run): leave the file for the user to review.
7. `uv run tools/guard.py log post <file> --detail "<first line>"`, then follow "End of every run" in AGENTS.md.
