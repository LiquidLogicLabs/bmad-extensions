# v7 fixture

A real BMad v7 project, built from a pinned upstream commit. It is used to check the v7
layer design's claims against an install rather than against source reading.

```bash
tests/fixtures/v7/make-fixture.sh e435a22574fe55722841086e5566420178b98df3 /tmp/v7fixture
```

The fixture is built on demand, not committed: it is an install, and v7 rewrites `_bmad/` on
every setup. Rebuild it from the v7 GA tag when GA ships (plan Task 7.2).

What was observed on it is recorded in
`docs/superpowers/specs/2026-10-16-bmad-v7-layer-design.md` §13.5.
