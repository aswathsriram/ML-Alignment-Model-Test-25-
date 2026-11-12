# Rules for the French (fr_FR) transcript batches

Each batch file is plain UTF-8 text, exactly 100 lines, one clip per line, no header, no blank lines:

    <id>|<F or M>|<tts_text>

- `<id>`: given in your task (e.g. b03-001 ... b03-100), in order.
- `<F or M>`: the speaker's gender. Use exactly 50 F and 50 M per batch, mixed (not all F first).
- `<tts_text>`: what a native speaker from France says, as the text-to-speech engine should read it.

The text (this is what gets read aloud and transcribed word by word):
1. Natural spoken French from France, like a real person talking: a voice message, a chat with a friend, a phone call,
   someone explaining or telling a short anecdote, a short reading. Vary the register: about 40 % relaxed
   conversation (fillers allowed), 30 % calm explanation or story, 30 % message / call / everyday request.
2. Length: 12 to 35 spoken words (about 5 to 12 seconds). Mix short, medium and long lines.
3. Gender agreement must match the speaker: a F speaker says "je suis allée", "je suis contente";
   a M speaker says "je suis allé", "je suis content".
4. Numbers ONLY in words, standard spelling, hyphens allowed: "vingt-deux", "trois cents", "deux mille vingt-quatre",
   "dix-huit heures trente". NEVER digits, never %, €, $, &, @, +, /, °, h (for heures). Write "euros", "pour cent".
5. No abbreviations or acronyms at all (no SNCF, TGV, RER, M., Mme, etc., km, kg, etc.). Write words in full:
   "monsieur", "madame", "kilomètres", "le train", "le métro".
6. No letters spelled one by one, no URLs, no emails, no hashtags, no emoji.
7. Elisions with a straight apostrophe ': l'appartement, j'ai, c'est, qu'il, d'accord, aujourd'hui.
8. Fillers / backchannels, only in the relaxed lines, spelled exactly like this: euh, ben, bah, hein, bof, ouais, ah, hmm.
   At most two per line. Do not use "mm hm", "chépa", "t'sé" or other slang spellings. "y'a" is allowed.
9. Punctuation is allowed for natural reading (, . ? ! : ;) — it is removed from the transcript later.
   No ellipsis "...", no quotes « », no parentheses, no dashes as punctuation.
10. Optional at the very start of a line, at most one audio tag in square brackets, on about half of the lines:
    [breathes] or [sighs] or [inhales] or [exhales]. Nothing else in square brackets, never in the middle of a line.
11. Common French first names and French place names are fine. Avoid English words except very common ones
    (week-end, email, parking, sandwich, ok is NOT allowed: write "d'accord").
12. Every line must be different from every other line (different situation, not the same sentence with one word
    changed). Spread the situations widely inside your topics. Use many different verbs, nouns and sentence shapes.
13. Plain everyday content only: nothing offensive, political, medical-advice or sensitive.

Example lines (do not copy them):
    b00-001|F|[breathes] Alors, euh, je voulais juste te dire que je serai un peu en retard ce soir, le métro est encore en panne.
    b00-002|M|Bonjour madame, j'appelle au sujet de la facture de mars, il y a un montant de quarante-deux euros que je ne comprends pas.
    b00-003|F|[sighs] Ben franchement, j'ai pas trop envie de sortir ce week-end, je suis vraiment fatiguée.
    b00-004|M|Le petit village se trouve à vingt kilomètres de la côte, et chaque été les touristes viennent y goûter le fromage local.
