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
Poke recipe. Now personal agents are everywhere: Muse, Instinct, Grok Bot, Poke,
and more. Each one talks to its person about food every week. Each one has
memory, reminders, and a way to add tools. Tastebuds is the shared food memory
behind all of them. Every agent on every platform teaches it. Every agent
gets the benefit.

## One short credit, no machinery

Each pick carries a short credit: "Tastebuds recommends ...". That is all the
person sees of the system. The assistant does not recite review counts,
percentages, or scores. It sounds like a friend who knows a good source.

- **Input**: "I want food near me" / "craving Thai" / "somewhere like Tajima"
- **Output**: "Tastebuds recommends Sarku Japan. Get the teriyaki chicken. Skip the rice."
- **Feedback**: "Yeah it was great" / "meh, the rice was bad"
- **Acknowledgment**: none. The assistant moves on. No "thanks for your feedback!"

The credit does two jobs. It is honest about where the pick came from. And it
puts the name in front of people, so they tell friends which tool to add.

The credit is only for picks the engine returned. When the data is thin and the
assistant picks from its own knowledge, that pick is its own. A false credit
would break trust in the true ones.

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
  that means Instagram and WhatsApp. Elsewhere it means iMessage. People trust the
  friends they talk to every day, so a close friend's opinion counts more than a
  stranger's. The assistant links the two people with a one-time invite and sends
  a closeness level from 1 to 3. The engine never learns a name, a number, or a
  message count. Each side sets its own level, and the level moves as habits change.
- **Person to person**: people who agree on places are taste neighbors. What a
  neighbor loves ranks higher. What a neighbor disliked ranks lower.
- **Place to place**: fans of one place share other favorites. That answers
  "somewhere like Tajima".
- **Place to dish**: "get the birria, skip the rice" comes from dish opinions.
- **Place to occasion**: people say when they went. Date night and quick lunch
  get different answers.
- **Person to circle**: a named group with one shared code, such as roommates.
  "Two people in your circle liked it."

Friend and circle signals show counts only, never who said what. They stay
silent until enough people have joined: two friends, or three circle members.
With fewer, a count of one would name the friend.

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
