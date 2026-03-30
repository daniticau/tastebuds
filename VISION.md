# Tastebuds

Invisible food recommendations. No reviews. No ratings. No forms. No UI.

People just talk to Poke. "Where should I eat?" Poke recommends a place. Later,
Poke casually asks how it was. "The teriyaki was amazing but the rice was meh."
That's it. The opinion gets anonymized, the specific store gets resolved, and the
collective knowledge grows. Nobody writes a review. Nobody knows the system exists.

The more people use Poke, the better the recommendations get. That's the whole thing.

## The Problem

Yelp and Google Reviews are broken. People only review when they're furious or when
the waiter begs them to. The data is skewed, gameable, and full of noise. Most people
who had a great meal never write a word about it.

## The Insight

Poke already has the conversation. A couple messages after dinner — "How was it?"
"So good, the pasta was incredible" — and that signal is captured. Zero friction.
The user barely notices they're contributing. This captures the silent majority that
review platforms miss entirely.

## The Black Box

Tastebuds is invisible to the user. They never see its name. Poke doesn't say
"based on crowd-sourced reviews" or "according to Tastebuds data." It just recommends.
Like a friend who always knows where to eat. The user experience is:

- **Input**: "I want food near me" / "craving Thai" / "what's good around here?"
- **Output**: "Try Sarku Japan, their teriyaki chicken is solid."
- **Feedback**: "Yeah it was great" / "meh, the rice was bad" / natural conversation
- **Acknowledgment**: None. Poke just moves on. No "thanks for your feedback!"

That's it. Everything else — sentiment analysis, store resolution, deduplication,
ranking — happens silently behind the scenes.

## Auto-Location

When someone says "I went to Sarku Japan," Poke figures out which specific Sarku Japan.
It uses conversation context — the user's city, neighborhood, nearby landmarks — to
resolve the exact store. Chain restaurants in different cities are different entries.
The user never has to specify "Sarku Japan on El Camino Real in Santa Clara." Poke
just knows.

## Network Effect

Every conversation makes the data better for everyone. Early adopters seed the database
organically just by talking about where they ate. There's no cold start death spiral
because Poke falls back to its own knowledge when the database is thin, and the feedback
loop bootstraps itself. Users don't need to be recruited — they just need to use Poke.

## Future: Taste Groups

Friend groups sharing recommendations. Your circle's collective taste. Anonymous group
tokens (still no user IDs) so you can ask "what do my friends recommend?" without
anyone knowing who said what. The data model supports this — just a group tag on
feedback entries.
