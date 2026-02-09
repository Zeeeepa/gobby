# Guiding Principles

Development philosophy for the Gobby project. These aren't suggestions — they're load-bearing walls.

## 1. Agents have a depth limit

Agents can only spawn to a maximum depth of **3**. No recursive agent chains disappearing into the void. If your task can't be solved in 3 levels of delegation, decompose it into smaller tasks instead.

## 2. No monoliths

Keep code files under **1,000 lines**. If a file grows past that, decompose it. Large files are where bugs hide and reviews go to die.

## 3. First write requires a task

The first file write of a session requires a task. No ticket, no laundry. This keeps every change traceable and intentional.

## 4. Claim before you work

You have to claim a task to work a task. No drive-by edits, no "I'll just fix this real quick." Claiming creates accountability and prevents conflicts.

## 5. No commits without validation

If work is done, validation must run. No skipping checks, no "it works on my machine." The validation gate exists for a reason.

## 6. No closing without commits

If your session has diffs, you can't close a task without committing them. Uncommitted work is invisible work, and invisible work is lost work.

## 7. No stopping until done

No stopping until the task is marked closed or needs review. If you hit a wall, escalate — don't abandon. Half-finished tasks are worse than unstarted ones.

## 8. Triage what you find

If you find unrelated errors or issues during your work, you must create tasks for them. Don't ignore problems just because they aren't yours. Leave the codebase better-informed than you found it.
