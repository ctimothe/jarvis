"""Action constants for Jarvis."""

# Filesystem actions
ACTION_CREATE_FOLDER = "create_folder"
ACTION_CREATE_FILE = "create_file"
ACTION_LIST_PATH = "list_path"
ACTION_FIND_NAME = "find_name"
ACTION_MOVE_PATH = "move_path"
ACTION_COPY_PATH = "copy_path"
ACTION_RENAME_PATH = "rename_path"
ACTION_DELETE_PATH = "delete_path"
ACTION_DISK_USAGE = "disk_usage"

# Git actions
ACTION_GIT_STATUS = "git_status"
ACTION_GIT_DIFF_STAT = "git_diff_stat"
ACTION_GIT_LOG_RECENT = "git_log_recent"
ACTION_GIT_BRANCHES = "git_branches"
ACTION_GIT_RECENT_CHANGES = "git_recent_changes"
ACTION_PROJECT_SEARCH = "project_search"

# System status actions
ACTION_BATTERY_STATUS = "battery_status"
ACTION_VOLUME_STATUS = "volume_status"
ACTION_SET_VOLUME_LEVEL = "set_volume_level"
ACTION_TOGGLE_MUTE = "toggle_mute"
ACTION_NOW_PLAYING = "now_playing"
ACTION_WIFI_STATUS = "wifi_status"
ACTION_TIME_STATUS = "time_status"
ACTION_ACTIVE_APP = "active_app"
ACTION_TRANSLATE_TEXT = "translate_text"

# App control actions
ACTION_QUIT_APP = "quit_app"
ACTION_FOCUS_APP = "focus_app"
ACTION_OPEN_APP = "open_app"
ACTION_OPEN_URL = "open_url"

# All supported actions
SUPPORTED_ACTIONS = {
    ACTION_CREATE_FOLDER,
    ACTION_CREATE_FILE,
    ACTION_LIST_PATH,
    ACTION_FIND_NAME,
    ACTION_MOVE_PATH,
    ACTION_COPY_PATH,
    ACTION_RENAME_PATH,
    ACTION_DELETE_PATH,
    ACTION_DISK_USAGE,
    ACTION_GIT_STATUS,
    ACTION_GIT_DIFF_STAT,
    ACTION_GIT_LOG_RECENT,
    ACTION_GIT_BRANCHES,
    ACTION_GIT_RECENT_CHANGES,
    ACTION_PROJECT_SEARCH,
    ACTION_BATTERY_STATUS,
    ACTION_VOLUME_STATUS,
    ACTION_SET_VOLUME_LEVEL,
    ACTION_TOGGLE_MUTE,
    ACTION_NOW_PLAYING,
    ACTION_WIFI_STATUS,
    ACTION_TIME_STATUS,
    ACTION_ACTIVE_APP,
    ACTION_TRANSLATE_TEXT,
    ACTION_QUIT_APP,
    ACTION_FOCUS_APP,
    ACTION_OPEN_APP,
    ACTION_OPEN_URL,
}

# Write actions (require home directory restriction)
WRITE_ACTIONS = {
    ACTION_CREATE_FOLDER,
    ACTION_CREATE_FILE,
    ACTION_MOVE_PATH,
    ACTION_COPY_PATH,
    ACTION_RENAME_PATH,
    ACTION_DELETE_PATH,
}

# Destructive actions (require approval)
DESTRUCTIVE_ACTIONS = {ACTION_DELETE_PATH}

# Action categories
ACTION_CATEGORIES: dict[str, set[str]] = {
    "fs": {
        ACTION_CREATE_FOLDER,
        ACTION_CREATE_FILE,
        ACTION_LIST_PATH,
        ACTION_FIND_NAME,
        ACTION_MOVE_PATH,
        ACTION_COPY_PATH,
        ACTION_RENAME_PATH,
        ACTION_DELETE_PATH,
    },
    "status": {
        ACTION_DISK_USAGE,
        ACTION_BATTERY_STATUS,
        ACTION_VOLUME_STATUS,
        ACTION_NOW_PLAYING,
        ACTION_WIFI_STATUS,
        ACTION_TIME_STATUS,
        ACTION_ACTIVE_APP,
    },
    "dev": {
        ACTION_GIT_STATUS,
        ACTION_GIT_DIFF_STAT,
        ACTION_GIT_LOG_RECENT,
        ACTION_GIT_BRANCHES,
        ACTION_GIT_RECENT_CHANGES,
        ACTION_PROJECT_SEARCH,
    },
    "language": {
        ACTION_TRANSLATE_TEXT,
    },
    "macos": {
        ACTION_SET_VOLUME_LEVEL,
        ACTION_TOGGLE_MUTE,
        ACTION_QUIT_APP,
        ACTION_FOCUS_APP,
        ACTION_OPEN_APP,
        ACTION_OPEN_URL,
    },
}

# Protected paths (blocked from all operations)
PROTECTED_PATHS = [
    "/System",
    "/bin",
    "/sbin",
    "/usr",
    "/private/etc",
    "/Library/Apple",
    "/dev",
]

# Rate limiting
RATE_LIMIT_PER_MINUTE = 20
ALERT_FAILURE_THRESHOLD = 5

# Timeouts
ACTION_TIMEOUT_SECONDS = 20
ACTION_MAX_RETRIES = 2

# VAD settings
VAD_SAMPLE_RATE = 16000
VAD_FRAME_MS = 30
VAD_FRAME_SAMPLES = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000)
PRE_ROLL_FRAMES = 10
MIN_SPEECH_FRAMES = 3
MAX_RECORD_SECONDS = 30
STARTUP_TIMEOUT_S = 8
SILENCE_END_FRAMES = 6

# Latency budgets (ms)
LATENCY_BUDGET_MS = {
    "cue_to_speech_start": 250,
    "speech_duration": 4500,
    "speech_end_to_transcript": 700,
    "transcript_to_response": 500,
    "post_speech_to_response": 1200,
}