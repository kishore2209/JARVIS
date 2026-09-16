class AIBrain:
    def __init__(self):
        self.name = "J.A.R.V.I.S AI Brain"
        self.status = "READY"

    def understand(self, command):
        original_command = command
        command = command.lower().strip()

        if "hello" in command or "hi" in command:
            return {"intent": "greeting", "confidence": 1.0, "command": original_command}

        if "status" in command:
            return {"intent": "system_status", "confidence": 1.0, "command": original_command}

        if "who are you" in command:
            return {"intent": "identity", "confidence": 1.0, "command": original_command}

        if "market" in command or "stock" in command:
            return {"intent": "market_analysis", "confidence": 0.9, "command": original_command}

        if "exit" in command or "quit" in command:
            return {"intent": "exit", "confidence": 1.0, "command": original_command}

        return {"intent": "unknown", "confidence": 0.0, "command": original_command}
