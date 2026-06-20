import json
import os
import time


STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.json")


class Stats:
    def __init__(self):
        self.data = self._load()
        self.session_start = time.strftime("%Y-%m-%d %H:%M:%S")
        self.session_likes = 0
        self.session_videos = 0
        self.session_start_time = time.time()

    def _load(self):
        if not os.path.exists(STATS_FILE):
            return {
                "total_likes": 0,
                "total_videos": 0,
                "total_hours": 0.0,
                "total_sessions": 0,
                "last_used": "",
                "top_authors": {},
                "liked_videos": [],
            }
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("total_likes", 0)
            data.setdefault("total_videos", 0)
            data.setdefault("total_hours", 0.0)
            data.setdefault("total_sessions", 0)
            data.setdefault("last_used", "")
            data.setdefault("top_authors", {})
            data.setdefault("liked_videos", [])
            return data
        except Exception:
            return {
                "total_likes": 0,
                "total_videos": 0,
                "total_hours": 0.0,
                "total_sessions": 0,
                "last_used": "",
                "top_authors": {},
                "liked_videos": [],
            }

    def save(self):
        try:
            self.data["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def record_like(self, author, title):
        self.data["total_likes"] += 1
        self.session_likes += 1
        if author:
            author_key = author
            self.data["top_authors"][author_key] = (
                self.data["top_authors"].get(author_key, 0) + 1
            )

        video_record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "author": author,
            "title": title,
        }
        self.data["liked_videos"].append(video_record)
        if len(self.data["liked_videos"]) > 200:
            self.data["liked_videos"] = self.data["liked_videos"][-200:]
        self.save()

    def record_video(self):
        self.data["total_videos"] += 1
        self.session_videos += 1
        self.save()

    def record_session_start(self):
        self.data["total_sessions"] += 1
        self.save()

    def record_session_end(self):
        hours = (time.time() - self.session_start_time) / 3600.0
        self.data["total_hours"] += hours
        self.save()

    def get_total_likes(self):
        return self.data["total_likes"]

    def get_total_videos(self):
        return self.data["total_videos"]

    def get_total_hours(self):
        return self.data["total_hours"]

    def get_total_sessions(self):
        return self.data["total_sessions"]

    def get_top_authors(self, limit=8):
        authors = sorted(
            self.data["top_authors"].items(), key=lambda x: x[1], reverse=True
        )
        return authors[:limit]

    def get_recent_videos(self, limit=10):
        return list(reversed(self.data["liked_videos"][-limit:]))

    def get_session_duration(self):
        seconds = int(time.time() - self.session_start_time)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"
