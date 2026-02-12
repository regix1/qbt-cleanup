
import os

# === Update app_state.py ===
path = os.path.join(r'H:\_git\qbt-cleanup\src\qbt_cleanup\api', 'app_state.py')
with open(path, 'r') as f:
    c = f.read()

old = 'def __init__(self, config: Config, scan_event: threading.Event) -> None:\n        self.config = config\n        self.scan_event = scan_event'
new = 'def __init__(\n        self,\n        config: Config,\n        scan_event: threading.Event,\n        orphaned_scan_event: threading.Event,\n    ) -> None:\n        self.config = config\n        self.scan_event = scan_event\n        self.orphaned_scan_event = orphaned_scan_event'
c = c.replace(old, new, 1)

with open(path, 'w', newline='\n') as f:
    f.write(c)
print('Updated: ' + path)
