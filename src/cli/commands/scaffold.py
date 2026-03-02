"""minerva scaffold - Generate a starter agent pack."""

import argparse
import sys
from pathlib import Path

from src.services.agent_scaffold_service import (
    AgentScaffoldService,
    ScaffoldError,
    PathTraversalError,
    ScaffoldEntryType,
)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the scaffold subcommand parser."""
    parser = subparsers.add_parser(
        "scaffold",
        help="Generate a starter agent pack",
        description="Create a minimal agent pack with AGENT.md, SOUL.md, IDENTITY.md, and skills/",
    )
    parser.add_argument(
        "--out",
        default="./agent-pack",
        help="Output directory for generated pack (default: ./agent-pack)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in output directory",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the scaffold command.

    Generates a minimal agent pack on disk with:
    - AGENT.md
    - SOUL.md
    - IDENTITY.md
    - skills/README.md

    Idempotent by default (doesn't overwrite existing files).
    """
    output_path = args.out

    # Check if output directory exists and is non-empty
    output_dir = Path(output_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.force:
            print(
                f"Error: Output directory '{output_path}' exists and is non-empty.\n"
                f"Use --force to overwrite existing files.",
                file=sys.stderr,
            )
            return 1

    try:
        # Use the existing scaffold service
        service = AgentScaffoldService()
        results = service.generate(output_path, overwrite=args.force)

        # Add skills/README.md (not in default template)
        skills_readme_path = Path(output_path) / "skills" / "README.md"
        skills_readme_content = """# Agent Skills

This directory contains optional skill modules that extend the agent's capabilities.

## What are Skills?

Skills are modular extensions that provide specialized capabilities to your agent:
- Tool integrations (APIs, databases, services)
- Domain knowledge (industry-specific, technical)
- Workflow patterns (multi-step processes, decision trees)

## How to Add Skills

1. Create a new file or directory in this folder
2. Define the skill's purpose, inputs, and outputs
3. Document any required configuration or environment variables

## Skill Format

Skills can be structured as:

### Simple Skill (single file)
```
skills/
  my_skill.md      # Documentation and implementation guidance
```

### Complex Skill (directory)
```
skills/
  my_complex_skill/
    SKILL.md       # Skill definition
    rules.md       # Operational rules
    examples/      # Usage examples
```

## Mount Point

In the Picoclaw runtime, this `skills/` directory is mounted into the sandbox
at `/app/skills/` when the agent is initialized.

## Examples

- `api_integration.md` - REST/GraphQL API interaction patterns
- `database_queries.md` - Database query templates and best practices
- `data_analysis.md` - Data processing and analysis workflows
- `customer_service.md` - Customer interaction patterns and responses

## Notes

- Keep skills focused and single-purpose
- Document dependencies clearly
- Avoid secrets or credentials in skill files
- Use environment variables for sensitive configuration
"""

        skills_readme_path.parent.mkdir(parents=True, exist_ok=True)
        if not skills_readme_path.exists() or args.force:
            skills_readme_path.write_text(skills_readme_content, encoding="utf-8")
            print(f"Created: {skills_readme_path}")
        else:
            print(f"Skipped: {skills_readme_path} (already exists)")

        # Print summary
        created_count = sum(1 for r in results if r.created and r.entry_type == ScaffoldEntryType.FILE)
        skipped_count = sum(1 for r in results if r.already_existed and r.entry_type == ScaffoldEntryType.FILE)

        print(f"\n✅ Scaffold generated at: {output_path}")
        print(f"   Files created: {created_count + 1}")  # +1 for skills/README.md
        if skipped_count > 0:
            print(f"   Files skipped: {skipped_count} (use --force to overwrite)")

        return 0

    except PathTraversalError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ScaffoldError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1
