# Harvest Commit Rules

Use one atomic commit per bean after that bean's work is complete and before any tagging or archive-oriented follow-up.

## Core Rules

- Commit after the bean deliverable is finished.
- Keep the commit scoped to one bean.
- Include code, docs, and bean file updates together.
- Use conventional commit formatting.
- Add a `Refs: <bean-id>` footer.

## Reference

- See `docs/COMMIT_GUIDELINES.md` in the target project for the full conventional commit policy.

## Command-Specific Formats

- Planning: `{{WINDMILL_ROOT}}/commit/plan-commits.md`
- Implementation: `{{WINDMILL_ROOT}}/commit/implementation-commits.md`
- Verification: `{{WINDMILL_ROOT}}/commit/verification-commits.md`
