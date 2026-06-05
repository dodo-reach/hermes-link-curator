# Validate — Quick Reference

## Dashboard validate.py locations

The `validate.py` script lives inside the **dashboard directory** of the link-curator profile, not at the profile root:

```bash
cd <profile-dir>/dashboard && python3 validate.py
```

The vault for the profile lives at `<profile-dir>/vault/` — completely separate from the dashboard directory.

## Finding validate.py if lost

```bash
find <profile-dir> -name "validate.py"
```

Expected: exactly one match, at `<profile-dir>/dashboard/validate.py`.

## validate.py exit codes

| `errors` | `warnings` | Meaning |
|----------|------------|---------|
| 0 | 0 | Clean — done |
| 0 | >0 | OK but titles use em-dash instead of hyphen-minus |
| >0 | any | Must fix — entry will be broken on dashboard |

## Common wrong paths

```bash
# WRONG — profile root may have a validate.py for a different purpose
cd <profile-dir>/ && python3 validate.py

# RIGHT for the dashboard
cd <profile-dir>/dashboard && python3 validate.py
```

If you have multiple link-curator profiles on the same machine, each has its own dashboard directory and its own `validate.py`. Always `cd` to the dashboard you want to validate before running.
