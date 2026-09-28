# Tastebuds

A food memory for AI assistants. No reviews. No ratings. No forms. No app.

People text their assistant. "Where should I eat?" The assistant answers:
"Tastebuds recommends Sarku Japan." Later it asks how the meal went. "The teriyaki was amazing but the rice was meh."
That is the whole interaction. The opinion loses its owner, the engine finds the
exact store, and everyone's next pick gets better. Nobody writes a review.

## The problem

Yelp and Google Reviews are broken. People review when they are furious, or when
the waiter begs. The data is skewed, easy to game, and noisy. Most people who
had a great meal never write a word about it.

## The insight

The assistant already has the conversation. Two messages after dinner capture
the signal: "How was it?" "So good, the pasta was incredible." The person does
no work. This reaches the many people that review sites never hear from.

In 2026 this matters more than when Tastebuds started. Tastebuds began as a
Poke recipe. Now personal agents are everywhere. Muse is the main home for
Tastebuds. Instinct, Grok Bot, and Poke work too. Each one talks to its person about food every week. Each one has
memory, reminders, and a way to add tools. Tastebuds is the shared food memory
behind all of them. Every agent on every platform teaches it. Every agent
gets the benefit.

## In the background

The person should rarely see Tastebuds. They should notice one thing: the picks
are good. Almost all of the work is silent. The assistant looks up, logs, and learns.

- **Input**: "I want food near me" / "craving Thai" / "somewhere like Tajima"
- **Output**: "Sarku Japan. Maya loved the teriyaki chicken there. Skip the rice."
- **Feedback**: "Yeah it was great" / "meh, the rice was bad"
- **Acknowledgment**: none. The assistant moves on. No "thanks for your feedback!"

A friend's name carries the pick, not a brand. The assistant credits Tastebuds at
most once in a conversation, in a few words, and only for places the engine
returned. A pick from the assistant's own knowledge is its own.

Tastebuds shows itself in three layers, from silent to visible:

1. **Background.** Better picks in every food chat. This is almost all of it.
2. **A quiet nudge.** About once a week at most: "Maya and Sam both loved Nonna Pia."
   The server decides if a find is worth a message, so no assistant can nag.
3. **On request.** A food board: your favorites, your friends' picks, places to try.

A person who asks "what do you remember about my food taste?" gets a plain
answer. A person who says "forget it" gets a real delete.

## One question to start

A survey would ruin this. Onboarding is one casual question:

> "What are a couple of spots you love, and is there anything you don't eat?"

The answer does three jobs in one call. It starts the person's taste profile.
It adds real opinions to the shared data. And it links the person to everyone
else who loves the same places, so the first recommendation is already personal.

## A taste profile, not an account

The engine remembers how a person eats: home city, dietary needs, allergies,
cuisines they like and avoid, budget, spice, the vibe they enjoy. It learns the
rest from their opinions: the cuisines they keep praising, the places they
loved, the places they will never see again.

The key is a random token. No name, no phone number, no email, no messages. The
assistant keeps the token in its own memory. Tastebuds cannot say who anyone is.

## Relationships in the data

The value is in the links, not the rows.

- **Person to place**: one person holds one opinion per place. A new opinion
  replaces the old one. Ten texts about one taco shop are still one voice.
- **Person to friend**: the assistant knows who a person messages most. On Muse
  that means Instagram and WhatsApp. People trust the friends they talk to every
  day, so a close friend's opinion counts more than a stranger's. Two friends who
  link up each see which places the other liked, and what to order there. Each
  side chooses whether to share, and can stop at any time. The engine knows a
  friend as a code. The person's own assistant knows the name. The engine never
  learns a name, a number, or a message count.
- **Person to person**: people who agree on places are taste neighbors. What a
  neighbor loves ranks higher. What a neighbor disliked ranks lower.
- **Place to place**: fans of one place share other favorites. That answers
  "somewhere like Tajima".
- **Place to dish**: "get the birria, skip the rice" comes from dish opinions.
- **Place to occasion**: people say when they went. Date night and quick lunch
  get different answers.
- **Person to circle**: a named group with one shared code, such as roommates.
  "Two people in your circle liked it."

A friend who chose not to share, and every circle, shows up as counts only.
Those counts stay silent until enough people have joined, because a count of one
would name the person.

The friend invite is also how Tastebuds spreads. The invite text carries a link.
A friend with no setup taps it, picks their assistant, and copies one message
that connects Tastebuds and accepts the invite.

## Auto-location

When someone says "I went to Sarku Japan," the assistant works out which Sarku
Japan. It uses the person's city, neighborhood, and location. The same chain in
two cities is two entries. The person never types an address.

## Network effect

Every conversation improves the data for everyone. An empty city is not a dead end:
when the data is thin, the assistant falls back on its own knowledge, then logs
how the meal went. The first user in a new city seeds it just by eating.

Users do not need to be recruited. They need to use their assistant.
