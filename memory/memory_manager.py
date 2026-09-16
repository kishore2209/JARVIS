import json
from pathlib import Path


class MemoryManager:
    def __init__(self, file_path="memory/memory.json"):
        self.file_path = Path(file_path)
        self.memory = self._load_memory()

    def _load_memory(self):
        if self.file_path.exists():
            with open(self.file_path, "r", encoding="utf-8") as file:
                return json.load(file)

        return {}

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(self.memory, file, indent=4)

    def remember(self, key, value):
        self.memory[key] = value
        self.save()

    def recall(self, key):
        return self.memory.get(key)

    def forget(self, key):
        if key in self.memory:
            del self.memory[key]
            self.save()
            return True

        return False


if __name__ == "__main__":
    memory = MemoryManager()

    memory.remember("name", "Kishor")

    print("J.A.R.V.I.S MEMORY")
    print("==================")
    print("Stored name:", memory.recall("name"))