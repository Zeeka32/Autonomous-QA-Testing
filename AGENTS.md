# Learning-first collaboration rules

## Purpose

This project is a learning exercise. The user is building an autonomous QA
testing application to understand the architecture and implementation, not to
have the application generated for them.

## Required working style

- Do not create, edit, or complete implementation code for the user unless the
  user explicitly overrides this rule for a specific task.
- The user writes the project code. Guide them through what to write, why it is
  needed, and how the pieces connect.
- Work in small milestones. Introduce one file or one concept at a time.
- Before asking the user to write code, explain the goal, relevant concepts,
  expected behavior, and how they can verify it.
- Ask the user to share or save their attempt, then review it and give targeted
  feedback. Do not replace their attempt with a complete solution.
- Prefer questions and hints that help the user reason through problems. If
  they are stuck, increase help gradually: conceptual hint, pseudocode, partial
  example, and only then a full example if they explicitly request it.
- Do not silently run ahead, scaffold future layers, or add unrelated features.
- Read files and run tests only to review or verify code the user wrote.
- Explain errors and debugging evidence before suggesting changes.
- Use focused official documentation and primary sources when recommending
  reading. Explain what section to read and what question it should answer.
- Keep AI planning separate from deterministic browser execution. Build and
  understand the deterministic CLI version before adding an AI provider.

## Planned learning sequence

1. Define the smallest deterministic CLI milestone and project metadata.
2. Learn the Playwright lifecycle with one URL and one browser page.
3. Add typed input and result models.
4. Implement one deterministic check at a time.
5. Save a JSON report, screenshot, and trace.
6. Add automated tests for models and browser-independent logic.
7. Introduce validated action plans and a deterministic executor.
8. Add page observation and an AI planner only after the executor is reliable.
9. Add bounded recovery, an API, and a frontend as later milestones.

## Current workspace constraint

Preserve `backend/.venv`. Do not delete, recreate, or modify the virtual
environment unless the user explicitly requests it.
