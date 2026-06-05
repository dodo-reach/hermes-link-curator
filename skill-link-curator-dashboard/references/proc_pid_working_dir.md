# Process PID → working directory check (Linux)

When debugging which process is serving on a given port, use:

```bash
ls -la /proc/<pid>/cwd   # symlink to actual working directory
cat /proc/<pid>/cmdline | tr '\0' ' '  # full command line
```

Example from this session:
- Port 8090 was occupied by PID 1131630
- `/proc/1131630/cwd` → `<profile-dir>/dashboard/` (NOT the official Hermes dashboard dir)
- cmdline: `python3 -m uvicorn main:app --port 8090`
- This revealed the dashboard is a standalone app in the profile's `dashboard/` directory, not part of the official Hermes dashboard process

This is the definitive way to resolve "which binary/config is actually running on this port" ambiguity.