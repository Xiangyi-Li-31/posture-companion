import traceback
import sys
from pathlib import Path

from posture_companion.app import main
from posture_companion.config import default_data_dir


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        try:
            log_path = default_data_dir() / "fatal.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            (Path.cwd() / "posture-companion-fatal.log").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
        if not getattr(sys, "frozen", False):
            raise
        raise SystemExit(1)
