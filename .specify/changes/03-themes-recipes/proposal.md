# 03-themes-recipes - Proposal

## Problem

Every style decision is hardcoded in main.py: monochrome crush, neon accents, hard cuts, single font, single text style. The prompt is equally single-purpose. improve.md section 2 demands pluggable theme profiles, LUT color grading, and parameterized transitions.

## User Stories

- As a user, I want to point config.json at a theme such as clean_editorial or documentary and get a different look without editing Python.
- As a user, I want to drop a .cube LUT into a project and have it applied in the grade.
- As a user, I want cross-dissolves, dips, and eased pans instead of only hard cuts.

## Risks

- The brutalist theme must reproduce current behavior exactly, so existing cutlists do not regress. The fixture render is the parity check.
- Transitions change segment boundaries because xfade consumes overlap. That interacts with Spec A's no-gap rule. The transition model must be defined before implementation.
- filter-effect-matrix.json must stay the single source of truth. New filters and effects register there or fail validation.
- Theme validation must be strict. Unknown fields fail loudly so typos do not silently change the render.
