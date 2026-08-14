# The public repository starts from a fresh commit

This project was written and used privately for eleven years before it was
published. Its public history therefore begins at 1.0.0, with a single initial
commit of the released tree. The development history is retained privately and
is not published.

## Why

The tool's whole purpose is to hold real billing information, and it was used
for exactly that throughout its private life. Commits from that period contain
working data — third parties' details and the commercial terms agreed with them
— which is not the author's to publish and cannot be withdrawn once it has been
cloned, forked or indexed.

The obvious alternative, rewriting history to remove the offending content, was
rejected on two grounds.

**It requires proving a negative.** Removing named paths is easy; being confident
that nothing else in a decade of commits carries working data is not. An audit of
the full history found more than the paths that had been noted as needing removal,
and each additional one was found only by going looking for it. A fresh commit
inverts the problem: what is published is a file list that can be reviewed
exhaustively in an afternoon, and reviewed again before the push.

**The rewrite itself carries risk.** The repository's only backup is
file-level version history on a sync service. Rewriting every object and then
letting that service replicate the result is a poor way to discover a mistake.

## What is given up

Real things, and they are worth naming rather than glossing over:

- `git blame` and `git log` on the public repository start at 1.0.0, so the
  reasoning behind older code is not reachable from the code itself.
- Contributors cannot see how the project evolved, which is part of what makes a
  small project readable.

Two things soften this. The architecture decisions worth carrying forward were
already written down as the records in this directory, which *are* published —
that is much of why they exist. And `CHANGELOG.md` documents every release back
to 0.2.0, so the shape of the project's development survives even though the
commits behind it do not.

## Consequences

The private history is preserved as a git bundle held outside the published
repository, alongside the scripts used to audit it, so it remains inspectable if
a question about the pre-1.0 past ever needs answering.

Republishing with full history stays possible, but it is a deliberate future
project rather than a loose end: it would need the removal work *and* an
exhaustive re-audit, and nothing about it gets easier by being deferred.

Releases 0.2.0 and 0.3.0 are described in `CHANGELOG.md` but have no tags in this
repository, because the commits they named are not here. Only `v1.0.0` and later
tags exist publicly.
