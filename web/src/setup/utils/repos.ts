import { readdirSync, statSync, existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

const CODE_DIRS = ["Projects", "code", "dev", "src", "repos", "Developer"];

function isDir(p: string): boolean {
  try {
    return statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function sorted(items: string[]): string[] {
  return [...items].sort();
}

/** Scan common code directories 2 levels deep for uninitialized git repos. */
export function findRepos(): string[] {
  const home = homedir();
  const repos: string[] = [];

  for (const dirname of CODE_DIRS) {
    const codeDir = join(home, dirname);
    if (!isDir(codeDir)) continue;

    try {
      for (const child of sorted(readdirSync(codeDir))) {
        if (child.startsWith(".")) continue;
        const childPath = join(codeDir, child);
        if (!isDir(childPath)) continue;

        if (isDir(join(childPath, ".git"))) {
          if (!existsSync(join(childPath, ".gobby", "project.json"))) {
            repos.push(childPath);
          }
        } else {
          // Level 2 (org-grouped repos like ~/Projects/myorg/repo)
          try {
            for (const grandchild of sorted(readdirSync(childPath))) {
              if (grandchild.startsWith(".")) continue;
              const gcPath = join(childPath, grandchild);
              if (
                isDir(gcPath) &&
                isDir(join(gcPath, ".git")) &&
                !existsSync(join(gcPath, ".gobby", "project.json"))
              ) {
                repos.push(gcPath);
              }
            }
          } catch {
            /* permission error */
          }
        }
      }
    } catch {
      /* permission error */
    }
  }

  return repos;
}

/** Display a path relative to home as ~/... for readability. */
export function displayPath(fullPath: string): string {
  const home = homedir();
  if (fullPath.startsWith(home)) {
    return "~" + fullPath.slice(home.length);
  }
  return fullPath;
}
