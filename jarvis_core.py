from core.ai_brain import AIBrain


class JarvisCore:
    def __init__(self):
        self.name = "J.A.R.V.I.S"
        self.status = "ONLINE"
        self.brain = AIBrain()

    def process_command(self, command):
        result = self.brain.understand(command)

        intent = result["intent"]

        if intent == "greeting":
            return "Hello. J.A.R.V.I.S is online."

        if intent == "system_status":
            return f"{self.name} is {self.status}."

        if intent == "identity":
            return "I am J.A.R.V.I.S, your personal AI assistant."

        if intent == "market_analysis":
            return "Market analysis capability is connected to the AI Brain."

        if intent == "exit":
            return "Goodbye."

        return "I understand your command, but this capability is not implemented yet."


if __name__ == "__main__":
    jarvis = JarvisCore()

    print("================================")
    print("       J.A.R.V.I.S CORE")
    print("================================")
    print("Status: ONLINE")
    print("AI Brain: CONNECTED")
    print("Type 'exit' to stop.\n")

    while True:
        command = input("You: ")

        response = jarvis.process_command(command)

        print(f"JARVIS: {response}")

        if command.lower().strip() in ["exit", "quit"]:
            break