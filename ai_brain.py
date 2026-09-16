class AIBrain:
    def __init__(self):
        self.name = "J.A.R.V.I.S AI Brain"
        self.status = "READY"

    def understand(self, command):
        command = command.lower().strip()

        if "hello" in command or "hi" in command:
            return "greeting"

        if "status" in command:
            return "system_status"

        if "who are you" in command:
            return "identity"

        if "market" in command or "stock" in command:
            return "market_analysis"

        if "exit" in command or "quit" in command:
            return "exit"

        return "unknown"


if __name__ == "__main__":
    brain = AIBrain()

    print("================================")
    print("       J.A.R.V.I.S AI BRAIN")
    print("================================")
    print("Status:", brain.status)

    while True:
        command = input("\nYou: ")

        intent = brain.understand(command)

        print("Detected Intent:", intent)

        if intent == "exit":
            print("AI Brain shutting down.")
            break
            