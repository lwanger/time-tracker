# MIT license, held by Leonard Wanger personally

> **Amended for 1.0.0 (2026-08-13):** the `LPC` branding this record preserved is
> retired. The GUI is now `Time Tracker Timer`, the icon is `timer.ico`, the PNG
> assets are `timer-*.png` and `APP_USER_MODEL_ID` is `TimeTracker.Timer`. The
> reasoning below is unchanged and still correct — branding and copyright are
> separate questions, and MIT never granted the name in the first place. What
> changed is only that a public release should not be named after a private
> consultancy that its readers have no relationship with. Every occurrence of
> `LPC` in user-visible text is now gone; only this note records that it existed.

The project shipped for eleven years with no license at all, which under default
copyright means nobody may legally copy or use it — the opposite of what an
open-sourced tool needs. We chose MIT: every runtime dependency is already
permissive (MIT, BSD-3-Clause, PSF), so no license family was closed off to us,
and the tool is small enough that copyleft or source-available terms would cost
more in adoption friction than they could plausibly protect.

## The copyright holder is a person, not the consultancy

Every source header said `Copyright 2015, 2026, LPC Consulting`, but the LICENSE
names **Leonard Wanger**. This is deliberate, and it is the part a future reader
is most likely to mistake for an error and "fix".

Two reasons. First, an MIT notice is immutable: it must be reproduced in every
copy and every fork, forever. A consultancy can be renamed, wound down, or sold;
a person is the stable referent. Second, unless LP Consulting is an incorporated
entity, it is not a separate legal person and copyright vests in the author
regardless of what the header claims — naming it would have been decorative.

The change removed the string `LPC Consulting` from the repository entirely,
which incidentally settled a long-standing inconsistency: the business was
written `LP Consulting` in `CONTEXT.md` and `pyproject.toml` but `LPC
Consulting` in every copyright line, where `LPC` already abbreviates `LP
Consulting`. The bylines moved from `Len Wanger` to the full legal name at the
same time, so the repository states one name in one form.

`LPC` survives as product branding — `LPC Timer`, `lpc_timer.ico`,
`APP_USER_MODEL_ID`. Branding and copyright ownership are separate questions,
and MIT conveys copyright only; it never grants trademark.

## Considered options

**BSD-3-Clause** was the real alternative, and the trade-off was about the name
rather than the code. Its third clause forbids using the copyright holder's name
to endorse or promote derivative works; MIT has no such clause, so a fork must
keep the notice while remaining free to imply what it likes about the
association. That gap matters more than usual when the holder is tied to a
consulting business. It was rejected because MIT's ubiquity is worth more for a
tool of this size — most readers recognise MIT without reading it — and the
endorsement risk for a personal CLI is theoretical.

**Apache-2.0** was rejected because its distinguishing feature is an express
patent grant, and nothing in time tracking or Excel export is patentable. It
would have bought ~10,000 words and NOTICE-file obligations for no benefit.

## Consequences

The grant is irrevocable for any version published under it. Relicensing later
binds only future releases; anything already released stays MIT forever.

The license is declared with PEP 639 metadata (`license = "MIT"` plus
`license-files`) rather than the deprecated `License ::` classifier. setuptools
rejects the two spellings together from 77.0.0, so `build-system.requires` moved
from `setuptools>=61` to `setuptools>=77` — the floor now states what the
metadata actually needs.

Nothing in the tree required a scope carve-out. `lpc_timer.ico` is a generic
stopwatch with no wordmark, and the shipped invoice template and the sample
invoices under `docs/` were verified to contain only placeholder text with no
embedded letterhead graphics.
