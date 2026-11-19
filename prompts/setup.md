# Routine: setup (interactive, a human is present)

Interview the user and fill `config.yaml`. Speak their language. Ask in **4 short rounds**, a few questions per round, and propose a good default for anything they skip.

1. **You and your offer.** Name, language for posts and DMs, a short bio with one proof point, what they sell,
   who it is for, the outcome (push for a number), the call to action they want, the price (or whether it may be discussed), and answers to the 3 questions prospects ask most (into `offer.faq`).
2. **Ideal customer.** Job titles, industries, locations, company size, who to exclude, and a plain-words description of the perfect lead.
   Turn the answers into `targeting.keywords` (3–6 search phrases a recruiter would type).
3. **Posts.** On or off, how many days a week and which days, the time, 3–6 topics, the tone (show them a 3-line sample in that tone and ask "like this?"),
   and auto-publish or draft. If they want auto-publish, explain that step 4 of the README needs a free LinkedIn developer app (it takes 5 minutes).
4. **Outreach.** Connection notes on or off, follow-ups (0–2). Keep the default safety limits unless the user is
   experienced and insists. Never set dms_per_day above 40 or invites_per_week above 100. Explain why: account restriction.

Then:
- Write `config.yaml`. Keep its exact structure and comments, keep every list on one line, and keep `outreach.mode: "dry_run"`.
- Write 2 sample DMs for imaginary leads that match their ideal customer, plus 1 sample post, so they can approve the voice.
  Adjust `outreach.message_style` / `posts.style` until they are happy.
- Tell them the next step: run the setup script (README step 4).
