import { readdir, stat, access } from "fs/promises";
import { constants } from "fs";
import { homedir } from "os";
import { join } from "path";

const CODE_DIRS = ["Projects", "code", "dev", "src", "repos", "Developer"];

async function isDir(p: string): Promise<boolean> {
  try {
    return (await stat(p)).isDirectory();
  } catch {
    return false;
  }
}

async function exists(p: string): Promise<boolean> {
  try {
    await access(p, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function sorted(items: string[]): string[] {
  return [...items].sort();
}

/** Scan common code directories 2 levels deep for uninitialized git repos. */
export async function findRepos(): Promise<string[]> {
  const home = homedir();
  const repos: string[] = [];

  for (const dirname of CODE_DIRS) {
    const codeDir = join(home, dirname);
    if (!(await isDir(codeDir))) continue;

    try {
      for (const child of sorted(await readdir(codeDir))) {
        if (child.startsWith(".")) continue;
        const childPath = join(codeDir, child);
        if (!(await isDir(childPath))) continue;

        if (await isDir(join(childPath, ".git"))) {
          if (!(await exists(join(childPath, ".gobby", "project.json")))) {
            repos.push(childPath);
          }
        } else {
          // Level 2 (org-grouped repos like ~/Projects/myorg/repo)
          try {
            for (const grandchild of sorted(await readdir(childPath))) {
              if (grandchild.startsWith(".")) continue;
              const gcPath = join(childPath, grandchild);
              if (
                (await isDir(gcPath)) &&
                (await isDir(join(gcPath, ".git"))) &&
                !(await exists(join(gcPath, ".gobby", "project.json")))
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
