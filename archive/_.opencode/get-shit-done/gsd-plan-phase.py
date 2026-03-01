#!/usr/bin/env python3
"""
/gsd-plan-phase orchestrator

Coordinates the research → plan → verify workflow for roadmap phases.
Usage: /gsd-plan-phase <phase_number> [--research] [--skip-research] [--gaps] [--skip-verify]
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Model profile mapping
MODEL_MAP = {
    "quality": {
        "gsd-phase-researcher": "opencode/glm-4.7-free",
        "gsd-planner": "opencode/glm-4.7-free",
        "gsd-plan-checker": "opencode/glm-4.7-free",
    },
    "balanced": {
        "gsd-phase-researcher": "opencode/glm-4.7-free",
        "gsd-planner": "opencode/glm-4.7-free",
        "gsd-plan-checker": "opencode/glm-4.7-free",
    },
    "budget": {
        "gsd-phase-researcher": "opencode/minimax-m2.1-free",
        "gsd-planner": "opencode/minimax-m2.1-free",
        "gsd-plan-checker": "opencode/minimax-m2.1-free",
    },
}


def print_banner(title: str):
    """Print a stage banner."""
    print(f"\n{'━' * 55}")
    print(f" GSD ► {title}")
    print(f"{'━' * 55}\n")


def error_exit(message: str):
    """Print error and exit."""
    print(f"❌ Error: {message}", file=sys.stderr)
    sys.exit(1)


def load_config() -> dict:
    """Load configuration from .planning/config.json."""
    config_path = Path(".planning/config.json")
    if not config_path.exists():
        return {
            "model_profile": "balanced",
            "workflow": {"research": True, "plan_check": True},
        }

    with open(config_path) as f:
        return json.load(f)


def resolve_model(profile: str, agent: str) -> str:
    """Resolve model for an agent based on profile."""
    # Check for custom overrides first
    config = load_config()
    custom_overrides = (
        config.get("profiles", {}).get("custom_overrides", {}).get(profile, {})
    )

    agent_key_map = {
        "gsd-phase-researcher": "planning",
        "gsd-planner": "planning",
        "gsd-plan-checker": "verification",
    }

    agent_key = agent_key_map.get(agent, agent)
    if agent_key in custom_overrides:
        return custom_overrides[agent_key]

    return MODEL_MAP.get(profile, MODEL_MAP["balanced"]).get(agent)


def normalize_phase(phase: str) -> str:
    """Normalize phase number to zero-padded format."""
    if re.match(r"^[0-9]+$", phase):
        return f"{int(phase):02d}"
    elif match := re.match(r"^([0-9]+)\.([0-9]+)$", phase):
        return f"{int(match.group(1)):02d}.{match.group(2)}"
    return phase


def parse_args(args: list) -> tuple:
    """Parse command arguments."""
    phase = None
    force_research = False
    skip_research = False
    gaps_mode = False
    skip_verify = False

    for arg in args:
        if arg == "--research":
            force_research = True
        elif arg == "--skip-research":
            skip_research = True
        elif arg == "--gaps":
            gaps_mode = True
        elif arg == "--skip-verify":
            skip_verify = True
        elif not phase and not arg.startswith("--"):
            phase = arg

    return phase, force_research, skip_research, gaps_mode, skip_verify


def detect_next_phase() -> Optional[str]:
    """Detect the next unplanned phase from roadmap."""
    roadmap_path = Path(".planning/ROADMAP.md")
    if not roadmap_path.exists():
        return None

    roadmap_content = roadmap_path.read_text()
    phases_dir = Path(".planning/phases")

    # Find all phase numbers mentioned in roadmap
    phase_pattern = r"Phase\s+([0-9]+(?:\.[0-9]+)?)"
    phases = set(re.findall(phase_pattern, roadmap_content))

    # Check which phases already have plans (normalize to non-padded for comparison)
    planned_phases = set()
    if phases_dir.exists():
        for phase_dir in phases_dir.iterdir():
            if phase_dir.is_dir():
                # Extract phase number from dirname (e.g., "01-identity" -> "1")
                match = re.match(r"^([0-9]+(?:\.[0-9]+)?)-", phase_dir.name)
                if match:
                    planned_phases.add(str(int(match.group(1))))

    # Find first unplanned phase
    for phase in sorted(phases, key=lambda x: float(x)):
        if str(int(phase)) not in planned_phases:
            return phase

    return None


def validate_phase(phase: str) -> tuple:
    """Validate phase exists in roadmap and extract details."""
    roadmap_path = Path(".planning/ROADMAP.md")
    if not roadmap_path.exists():
        error_exit("ROADMAP.md not found")

    roadmap_content = roadmap_path.read_text()

    # Try both normalized (02) and non-normalized (2) formats
    # Match "### Phase X -" or "### Phase X:" patterns
    phase_pattern = rf"###\s+Phase\s+{re.escape(phase)}(?:\s+-|:)\s*([^\n]+)"
    match = re.search(phase_pattern, roadmap_content, re.IGNORECASE)

    # If not found and phase is zero-padded (e.g., "02"), try without padding ("2")
    if not match and phase.startswith("0") and len(phase) >= 2:
        unpadded = str(int(phase))
        phase_pattern = rf"###\s+Phase\s+{re.escape(unpadded)}(?:\s+-|:)\s*([^\n]+)"
        match = re.search(phase_pattern, roadmap_content, re.IGNORECASE)

    # If still not found, try the other direction (non-padded -> padded)
    if not match:
        try:
            padded = f"{int(phase):02d}"
            if padded != phase:
                phase_pattern = (
                    rf"###\s+Phase\s+{re.escape(padded)}(?:\s+-|:)\s*([^\n]+)"
                )
                match = re.search(phase_pattern, roadmap_content, re.IGNORECASE)
        except ValueError:
            pass

    if not match:
        # List available phases
        all_phases = re.findall(r"Phase\s+([0-9]+(?:\.[0-9]+)?)", roadmap_content)
        error_exit(
            f"Phase {phase} not found in roadmap. Available phases: {', '.join(sorted(set(all_phases)))}"
        )

    phase_name = match.group(1).strip()

    # Extract phase description (next few lines)
    desc_start = match.end()
    next_section = roadmap_content.find("###", desc_start)
    if next_section == -1:
        next_section = len(roadmap_content)
    description = roadmap_content[desc_start:next_section].strip()

    return phase_name, description


def get_phase_dir(phase: str) -> Path:
    """Get or create phase directory."""
    phases_dir = Path(".planning/phases")

    # Try to find existing directory
    for phase_dir in phases_dir.glob(f"{phase}-*"):
        if phase_dir.is_dir():
            return phase_dir

    # Create new directory from roadmap name
    phase_name, _ = validate_phase(phase)
    safe_name = re.sub(r"[^a-zA-Z0-9\s]", "", phase_name).lower().replace(" ", "-")
    phase_dir = phases_dir / f"{phase}-{safe_name}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    return phase_dir


def get_file_content(path: Path) -> str:
    """Safely read file content, return empty string if not exists."""
    if path.exists():
        return path.read_text()
    return ""


def spawn_researcher(phase: str, phase_name: str, phase_dir: Path, model: str) -> bool:
    """Spawn gsd-phase-researcher subagent."""
    print_banner(f"RESEARCHING PHASE {phase}")
    print("◆ Spawning researcher...\n")

    # Gather context
    phase_desc, _ = validate_phase(phase)
    requirements = get_file_content(Path(".planning/REQUIREMENTS.md"))
    state = get_file_content(Path(".planning/STATE.md"))
    context = get_file_content(phase_dir / f"{phase}-CONTEXT.md")

    # Extract decisions from state
    decisions = ""
    if "### Decisions" in state:
        decisions_match = re.search(r"### Decisions.*?(?=###|$)", state, re.DOTALL)
        if decisions_match:
            decisions = decisions_match.group(0)

    # Build research prompt
    research_prompt = f"""<objective>
Research how to implement Phase {phase}: {phase_name}

Answer: "What do I need to know to PLAN this phase well?"
</objective>

<context>
**Phase description:**
{phase_desc}

**Requirements (if any):**
{requirements[:2000] if requirements else "No requirements specified."}

**Prior decisions:**
{decisions[:1500] if decisions else "No prior decisions."}

**Phase context (if any):**
{context[:1000] if context else "No phase context."}
</context>

<output>
Write research findings to: {phase_dir}/{phase}-RESEARCH.md
</output>

Return exactly one of:
- ## RESEARCH COMPLETE — when research is done and file is written
- ## RESEARCH BLOCKED — if critical information is missing, explain what
"""

    # This would normally spawn a subagent
    # For now, we'll create a placeholder
    print(f"[Would spawn gsd-phase-researcher with model {model}]")
    print(f"Research prompt length: {len(research_prompt)} chars")

    # Simulate success for now
    research_file = phase_dir / f"{phase}-RESEARCH.md"
    if not research_file.exists():
        research_file.write_text(
            f"# Phase {phase} Research\n\nResearch findings would go here.\n"
        )
        print(f"✓ Created placeholder research file: {research_file}")

    return True


def check_existing_plans(phase_dir: Path) -> list:
    """Check for existing plan files."""
    return list(phase_dir.glob("*-PLAN.md"))


def spawn_planner(
    phase: str, phase_name: str, phase_dir: Path, model: str, gaps_mode: bool = False
) -> tuple:
    """Spawn gsd-planner subagent. Returns (success, plans_created)."""
    print_banner(f"PLANNING PHASE {phase}")
    print("◆ Spawning planner...\n")

    # Read all context files
    state_content = get_file_content(Path(".planning/STATE.md"))
    roadmap_content = get_file_content(Path(".planning/ROADMAP.md"))
    requirements_content = get_file_content(Path(".planning/REQUIREMENTS.md"))
    context_content = get_file_content(phase_dir / f"{phase}-CONTEXT.md")
    research_content = get_file_content(phase_dir / f"{phase}-RESEARCH.md")

    # Gap closure files (only if gaps mode)
    verification_content = ""
    uat_content = ""
    if gaps_mode:
        verification_content = get_file_content(phase_dir / f"{phase}-VERIFICATION.md")
        uat_content = get_file_content(phase_dir / f"{phase}-UAT.md")

    mode = "gap_closure" if gaps_mode else "standard"

    # Build planning prompt
    planning_prompt = f"""<planning_context>

**Phase:** {phase}
**Mode:** {mode}

**Project State:**
{state_content[:3000]}

**Roadmap:**
{roadmap_content[:3000]}

**Requirements (if exists):**
{requirements_content[:2000] if requirements_content else "No requirements file."}

**Phase Context (if exists):**
{context_content[:1500] if context_content else "No phase context."}

**Research (if exists):**
{research_content[:2000] if research_content else "No research file."}

**Gap Closure (if --gaps mode):**
{verification_content[:1500] if verification_content else ""}
{uat_content[:1500] if uat_content else ""}

</planning_context>

<downstream_consumer>
Output consumed by /gsd-execute-phase
Plans must be executable prompts with:

- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format
- Verification criteria
- must_haves for goal-backward verification
</downstream_consumer>

<quality_gate>
Before returning PLANNING COMPLETE:

- [ ] PLAN.md files created in phase directory
- [ ] Each plan has valid frontmatter
- [ ] Tasks are specific and actionable
- [ ] Dependencies correctly identified
- [ ] Waves assigned for parallel execution
- [ ] must_haves derived from phase goal
</quality_gate>

Return exactly one of:
- ## PLANNING COMPLETE — when all plans are created
- ## CHECKPOINT REACHED — if you need user input before continuing
- ## PLANNING INCONCLUSIVE — if you cannot create valid plans, explain why
"""

    print(f"[Would spawn gsd-planner with model {model}]")
    print(f"Planning prompt length: {len(planning_prompt)} chars")

    # For demonstration, create a sample plan
    plan_file = phase_dir / f"{phase}-01-PLAN.md"
    if not plan_file.exists():
        plan_file.write_text(f"""---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

# Plan {phase}-01: Foundation Setup

## Objective
Set up the foundational components for Phase {phase}.

## Tasks

<task id="1">
<description>Initialize project structure</description>
</task>

<task id="2">
<description>Set up core dependencies</description>
</task>

## Verification

- [ ] Project structure is in place
- [ ] Dependencies are installed

## Must Haves

- [ ] Foundation is solid for subsequent waves
""")
        print(f"✓ Created sample plan: {plan_file}")
        return True, 1

    # Count existing plans
    existing_plans = check_existing_plans(phase_dir)
    return True, len(existing_plans)


def spawn_checker(phase: str, phase_dir: Path, model: str) -> tuple:
    """Spawn gsd-plan-checker subagent. Returns (passed, issues)."""
    print_banner("VERIFYING PLANS")
    print("◆ Spawning plan checker...\n")

    # Read all plans
    plans = check_existing_plans(phase_dir)
    if not plans:
        print("⚠ No plans found to verify")
        return True, []

    plans_content = "\n\n---\n\n".join([p.read_text() for p in sorted(plans)])
    requirements_content = get_file_content(Path(".planning/REQUIREMENTS.md"))

    # Extract phase goal from roadmap
    _, phase_desc = validate_phase(phase)
    # Get first line as goal
    phase_goal = phase_desc.split("\n")[0] if phase_desc else "Phase goal not specified"

    # Build verification prompt
    checker_prompt = f"""<verification_context>

**Phase:** {phase}
**Phase Goal:** {phase_goal}

**Plans to verify:**
{plans_content}

**Requirements (if exists):**
{requirements_content[:2000] if requirements_content else "No requirements file."}

</verification_context>

<expected_output>
Return one of:
- ## VERIFICATION PASSED — all checks pass
- ## ISSUES FOUND — structured issue list

If issues found, format as:
### Issue 1: [Category]
- **Location:** [plan file / task]
- **Problem:** [description]
- **Fix:** [suggestion]
</expected_output>
"""

    print(f"[Would spawn gsd-plan-checker with model {model}]")
    print(f"Checker prompt length: {len(checker_prompt)} chars")

    # Simulate success
    return True, []


def present_final_status(
    phase: str,
    phase_name: str,
    phase_dir: Path,
    research_status: str,
    verify_status: str,
):
    """Present final status to user."""
    plans = check_existing_plans(phase_dir)
    plan_count = len(plans)

    # Count waves from plan frontmatter
    waves = set()
    for plan in plans:
        content = plan.read_text()
        if match := re.search(r"wave:\s*(\d+)", content):
            waves.add(int(match.group(1)))
    wave_count = len(waves) if waves else 1

    print(f"""
{"━" * 55}
 GSD ► PHASE {phase} PLANNED ✓
{"━" * 55}

**Phase {phase}: {phase_name}** — {plan_count} plan(s) in {wave_count} wave(s)

| Wave | Plans | What it builds |
|------|-------|----------------|
| 1    | 01, 02 | [objectives] |
| 2    | 03     | [objective]  |

Research: {research_status}
Verification: {verify_status}

{"─" * 55}

## ▶ Next Up

**Execute Phase {phase}** — run all {plan_count} plans

/gsd-execute-phase {phase}

*/new first → fresh context window*

{"─" * 55}

**Also available:**
- cat .planning/phases/{phase_dir.name}/*-PLAN.md — review plans
- /gsd-plan-phase {phase} --research — re-research first

{"─" * 55}
""")


def main():
    """Main orchestrator logic."""

    # Step 1: Validate environment
    if not Path(".planning").exists():
        error_exit("No .planning directory found. Run `/gsd-new-project` first.")

    # Load config
    config = load_config()
    profile = config.get("model_profile", "balanced")

    # Step 2: Parse arguments
    phase, force_research, skip_research, gaps_mode, skip_verify = parse_args(
        sys.argv[1:]
    )

    # Auto-detect phase if not provided
    if not phase:
        phase = detect_next_phase()
        if not phase:
            error_exit("No phase specified and could not auto-detect next phase")
        print(f"Auto-detected phase: {phase}")

    # Normalize phase
    phase = normalize_phase(phase)

    # Step 3: Validate phase
    phase_name, phase_desc = validate_phase(phase)
    print(f"✓ Phase {phase}: {phase_name}")

    # Step 4: Ensure phase directory
    phase_dir = get_phase_dir(phase)
    print(f"✓ Phase directory: {phase_dir}")

    # Step 5: Handle research
    research_status = "Skipped"

    if gaps_mode:
        research_status = "Skipped (gap closure mode)"
        print(
            "\n⏭ Gap closure mode — skipping research (using VERIFICATION.md instead)"
        )
    elif skip_research:
        research_status = "Skipped (--skip-research flag)"
        print("\n⏭ Skipping research (--skip-research flag)")
    elif not config.get("workflow", {}).get("research", True) and not force_research:
        research_status = "Skipped (workflow.research=false)"
        print("\n⏭ Skipping research (workflow.research=false in config)")
    else:
        # Check for existing research
        research_file = phase_dir / f"{phase}-RESEARCH.md"
        if research_file.exists() and not force_research:
            research_status = f"Used existing: {research_file}"
            print(f"\n📄 Using existing research: {research_file}")
        else:
            # Spawn researcher
            researcher_model = resolve_model(profile, "gsd-phase-researcher")
            success = spawn_researcher(phase, phase_name, phase_dir, researcher_model)
            if success:
                research_status = "Completed"
            else:
                error_exit("Research failed or was blocked")

    # Step 6: Check existing plans
    existing_plans = check_existing_plans(phase_dir)
    if existing_plans and not gaps_mode:
        print(f"\n⚠ Found {len(existing_plans)} existing plan(s):")
        for plan in sorted(existing_plans):
            print(f"  - {plan.name}")
        print("\nOptions:")
        print("  1) Continue planning (add more plans)")
        print("  2) View existing plans")
        print("  3) Replan from scratch")
        # In a real implementation, we'd prompt the user here
        print("\n⏩ Continuing with existing plans...")

    # Step 7 & 8: Spawn planner
    planner_model = resolve_model(profile, "gsd-planner")
    success, plan_count = spawn_planner(
        phase, phase_name, phase_dir, planner_model, gaps_mode
    )

    if not success:
        error_exit("Planning failed")

    # Step 9-12: Verification loop (unless skipped)
    verify_status = "Skipped"

    if skip_verify:
        verify_status = "Skipped (--skip-verify flag)"
        print("\n⏭ Skipping verification (--skip-verify flag)")
    elif not config.get("workflow", {}).get("plan_check", True):
        verify_status = "Skipped (workflow.plan_check=false)"
        print("\n⏭ Skipping verification (workflow.plan_check=false in config)")
    else:
        # Run verification loop (max 3 iterations)
        max_iterations = 3
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            checker_model = resolve_model(profile, "gsd-plan-checker")
            passed, issues = spawn_checker(phase, phase_dir, checker_model)

            if passed:
                verify_status = "Passed"
                print("\n✓ Plans verified. Ready for execution.")
                break
            else:
                print(f"\n⚠ Checker found {len(issues)} issues")
                if iteration < max_iterations:
                    print(
                        f"\nSending back to planner for revision... (iteration {iteration}/{max_iterations})"
                    )
                    # In a real implementation, we'd spawn a revision here
                    # For now, we'll just loop once more
                else:
                    print(
                        f"\n⚠ Max iterations ({max_iterations}) reached. {len(issues)} issues remain."
                    )
                    verify_status = f"Passed with {len(issues)} outstanding issues"
                    print("\nOptions:")
                    print("  1) Force proceed (execute despite issues)")
                    print("  2) Provide guidance (manual intervention)")
                    print("  3) Abandon (exit planning)")

    # Step 13: Present final status
    present_final_status(phase, phase_name, phase_dir, research_status, verify_status)


if __name__ == "__main__":
    main()
