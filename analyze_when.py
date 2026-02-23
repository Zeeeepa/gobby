import yaml
import os
import glob
import ast


def get_names(expr):
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception as e:
        return set()

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


rule_files = glob.glob("src/gobby/install/shared/rules/**/*.yaml", recursive=True)
all_naked = set()
file_vars = {}

for f in rule_files:
    if "deprecated" in f:
        continue
    with open(f) as fp:
        try:
            data = yaml.safe_load(fp)
        except:
            continue
    if not isinstance(data, dict):
        continue
    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        continue
    for rname, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        if "when" in rule:
            when_expr = rule["when"]
            if isinstance(when_expr, str):
                names = get_names(when_expr)
                safe_names = {
                    "event",
                    "variables",
                    "tool_input",
                    "source",
                    "is_plan_file",
                    "task_tree_complete",
                    "len",
                    "not",
                    "and",
                    "or",
                    "in",
                    "is",
                    "None",
                    "True",
                    "False",
                    "dict",
                }
                naked = names - safe_names
                if naked:
                    all_naked.update(naked)
                    if f not in file_vars:
                        file_vars[f] = set()
                    file_vars[f].update(naked)

print("All naked names found:", all_naked)
for f, vars in file_vars.items():
    print(f"- {f}: {vars}")
